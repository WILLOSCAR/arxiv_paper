"""Personalized ranking and recommendation (预留接口)."""

import hashlib
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

from .models import Paper

logger = logging.getLogger(__name__)


class PersonalizedRanker:
    """
    个性化论文排序器.

    功能:
    - 基于向量相似度重排序
    - 结合关键词分数和历史偏好
    - 生成个性化推荐分数

    状态: ✅ 基础可用（哈希向量相似度）；可选 sentence-transformers 提升质量
    可选依赖: sentence-transformers（用于更高质量 embedding）
    """

    def __init__(self, model_name: str = "allenai/specter", enabled: bool = False):
        """
        Initialize personalized ranker.

        Args:
            model_name: Embedding model name
            enabled: Whether personalization is enabled
        """
        self.enabled = enabled
        self.model_name = model_name
        self.model = None
        self.embedding_dim = 768  # matches the original docstring default

        if enabled:
            # Best-effort: use sentence-transformers if present, otherwise fall back to
            # a deterministic hashing-based embedding (no extra deps).
            try:
                # In sandboxed environments, the default HF cache (~/.cache) may be unwritable.
                # Redirect to /tmp unless the user already configured HF_HOME.
                os.environ.setdefault("HF_HOME", "/tmp/hf_home")

                from sentence_transformers import SentenceTransformer  # type: ignore

                self.model = SentenceTransformer(model_name)
                try:
                    dim = int(getattr(self.model, "get_sentence_embedding_dimension")())
                    if dim > 0:
                        self.embedding_dim = dim
                except Exception:
                    pass
                logger.info("PersonalizedRanker: using sentence-transformers model=%s", model_name)
            except Exception:
                self.model = None
                logger.warning(
                    "PersonalizedRanker: sentence-transformers not available; "
                    "using hashing-based embeddings (lower quality)."
                )

    def compute_embedding(self, paper: Paper) -> Optional[np.ndarray]:
        """
        Compute embedding vector for a paper.

        Args:
            paper: Paper object

        Returns:
            768-dim embedding vector or None if not enabled

        """
        if not self.enabled:
            return None

        text = f"{paper.title} {paper.abstract}".strip()
        if not text:
            return np.zeros(self.embedding_dim, dtype=np.float32)

        if self.model is not None:
            try:
                vec = self.model.encode(text, normalize_embeddings=True)
                return np.asarray(vec, dtype=np.float32)
            except Exception:
                logger.debug("SentenceTransformer encode failed; falling back to hashing", exc_info=True)

        return _hash_embed(text, dim=self.embedding_dim)

    def rank_by_similarity(
        self,
        papers: List[Paper],
        liked_papers: List[Paper],
        weight: float = 0.4,
    ) -> List[Paper]:
        """
        Re-rank papers by similarity to liked papers.

        Args:
            papers: List of papers to rank
            liked_papers: User's liked papers
            weight: Weight for similarity score (0.4) vs keyword score (0.6)

        Returns:
            Re-ranked list of papers

        """
        if not self.enabled or not liked_papers:
            logger.debug("Personalization disabled or no liked papers, skipping")
            return papers

        weight = float(weight)
        weight = max(0.0, min(1.0, weight))

        # Build user profile embedding (mean of liked embeddings).
        liked_vecs = []
        for lp in liked_papers:
            v = self.compute_embedding(lp)
            if v is not None:
                liked_vecs.append(v)

        if not liked_vecs:
            logger.debug("No liked embeddings, skipping")
            return papers

        profile_vec = np.mean(np.stack(liked_vecs, axis=0), axis=0)
        profile_vec = _l2_normalize(profile_vec)

        # Normalize keyword score scale so similarity can be mixed in reasonably.
        keyword_scores = [float(p.score or 0.0) for p in papers] if papers else [0.0]
        score_scale = max(keyword_scores) if keyword_scores else 1.0
        if score_scale <= 0:
            score_scale = 1.0

        ranked = []
        for p in papers:
            emb = self.compute_embedding(p)
            if emb is None:
                sim = 0.0
            else:
                emb = _l2_normalize(emb)
                sim = float(np.dot(emb, profile_vec))
                # Similarity can be negative; treat negative as 0 signal.
                sim = max(0.0, min(1.0, sim))

            base = float(p.score or 0.0)
            personalized = (1.0 - weight) * base + weight * (sim * score_scale)

            p.similarity_score = sim
            p.personalized_score = personalized
            ranked.append(p)

        ranked.sort(
            key=lambda x: float(
                x.personalized_score
                if x.personalized_score is not None
                else (x.score if x.score is not None else 0.0)
            ),
            reverse=True,
        )
        logger.info(
            "PersonalizedRanker re-ranked %s papers using %s liked papers",
            len(ranked),
            len(liked_papers),
        )
        return ranked

    def update_paper_scores(
        self, papers: List[Paper], liked_papers: List[Paper]
    ) -> List[Paper]:
        """
        Update papers with personalized scores.

        Args:
            papers: List of papers
            liked_papers: User's liked papers

        Returns:
            Papers with updated personalized_score field

        """
        if not self.enabled:
            return papers

        # Keep ordering; only annotate scores.
        ranked = self.rank_by_similarity(papers, liked_papers, weight=0.4)
        # rank_by_similarity returns a list, but also mutates Paper objects in place.
        # Preserve original order by returning the input list.
        _ = ranked
        return papers


class IntentAgent:
    """
    LLM-powered intent recognition agent (预留接口).

    功能:
    - 分析用户阅读模式
    - 动态生成关键词
    - 生成推荐解释

    状态: ✅ 基础可用（启发式）；可选接入 LLM 输出更结构化画像
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize intent agent.

        Args:
            config: LLM configuration (provider, model, api_key, etc.)
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)
        self._llm = None

        if self.enabled:
            self._llm = _build_intent_llm(self.config)
            if self._llm is None:
                logger.warning("IntentAgent enabled but LLM not configured; using heuristic mode")

    def analyze_reading_pattern(
        self, liked_papers: List[Paper], recent_searches: List[str] = None
    ) -> dict:
        """
        Analyze user's reading pattern using LLM.

        Args:
            liked_papers: User's liked papers
            recent_searches: Recent search queries

        Returns:
            Analysis result:
            {
                "main_interests": ["multimodal learning", "transformers"],
                "emerging_interests": ["diffusion models"],
                "suggested_keywords": ["CLIP", "vision-language"],
                "confidence": 0.85
            }

        """
        if not self.enabled:
            return {}

        recent_searches = recent_searches or []

        # Prefer LLM if configured, but always keep a deterministic fallback.
        if self._llm is not None:
            try:
                from langchain_core.prompts import ChatPromptTemplate

                prompt = ChatPromptTemplate.from_messages(
                    [
                        (
                            "system",
                            "Return valid JSON only. No Markdown, no extra text.",
                        ),
                        (
                            "user",
                            "Analyze the user's preferred topics from liked papers.\n"
                            "Return JSON with keys: main_interests (list[str]), emerging_interests (list[str]), "
                            "suggested_keywords (list[str]), confidence (0-1).\n"
                            "Liked papers:\n{liked}\n\nRecent searches:\n{searches}\n",
                        ),
                    ]
                )

                liked_lines = []
                for p in liked_papers[:20]:
                    liked_lines.append(f"- {p.title}")
                chain = prompt | self._llm
                msg = chain.invoke({"liked": "\n".join(liked_lines), "searches": "\n".join(recent_searches[:10])})
                content = getattr(msg, "content", "") or ""
                return _safe_json_loads(content) or _heuristic_intent(liked_papers, recent_searches)
            except Exception:
                logger.debug("IntentAgent LLM analysis failed; falling back", exc_info=True)

        return _heuristic_intent(liked_papers, recent_searches)

    def generate_search_query(self, user_profile: dict) -> str:
        """
        Dynamically generate arXiv search query based on user profile.

        Args:
            user_profile: User interest profile

        Returns:
            arXiv query string

        """
        if not self.enabled:
            return ""

        # Prefer explicit user_profile keywords if present (FeedbackCollector stores this as a dict).
        preferred = user_profile.get("preferred_keywords") if isinstance(user_profile, dict) else None
        terms: list[str] = []
        if isinstance(preferred, dict):
            # Top-N by frequency
            for k, _v in sorted(preferred.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                if k:
                    terms.append(str(k))

        if not terms:
            # Fallback: accept already-structured "main_interests" if present.
            mi = user_profile.get("main_interests") if isinstance(user_profile, dict) else None
            if isinstance(mi, list):
                terms = [str(t) for t in mi if t]

        if not terms:
            return ""

        quoted = []
        for t in terms:
            tt = t.strip()
            if not tt:
                continue
            if " " in tt:
                quoted.append(f'"{tt}"')
            else:
                quoted.append(tt)
        return " OR ".join(quoted)

    def explain_recommendation(self, paper: Paper, user_profile: dict) -> str:
        """
        Generate explanation for why a paper is recommended.

        Args:
            paper: Recommended paper
            user_profile: User interest profile

        Returns:
            Explanation string

        """
        if not self.enabled:
            return ""

        # Heuristic explanation (no secrets, no network).
        preferred = user_profile.get("preferred_keywords") if isinstance(user_profile, dict) else {}
        preferred_terms = set()
        if isinstance(preferred, dict):
            preferred_terms = {str(k).lower() for k in list(preferred.keys())[:20] if k}

        matched = [kw for kw in (paper.matched_keywords or []) if str(kw).lower() in preferred_terms]
        if matched:
            return f"推荐原因：命中你的偏好关键词 {', '.join(matched[:3])}。"

        # Fallback: mention score and high-level topic signals.
        return "推荐原因：与近期偏好主题相似，且关键词匹配得分较高。"


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    return re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text)


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "we", "with", "without", "you", "your",
}


def _hash_token(token: str, dim: int) -> int:
    h = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "little") % dim


def _hash_embed(text: str, *, dim: int) -> np.ndarray:
    """Deterministic, dependency-free embedding based on token hashing + tf scaling."""
    vec = np.zeros(dim, dtype=np.float32)
    toks = [t for t in _tokenize(text) if len(t) >= 2 and t not in _STOPWORDS]
    if not toks:
        return vec

    for t in toks:
        vec[_hash_token(t, dim)] += 1.0
    # Light sublinear TF scaling.
    vec = np.log1p(vec)
    return _l2_normalize(vec)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec
    return vec / norm


def _build_intent_llm(config: dict):
    """Build a ChatOpenAI client for IntentAgent; returns None if not configured."""
    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    provider = (config.get("provider") or "").lower()
    base_url = config.get("base_url") or None
    model = config.get("model") or "gpt-4o-mini"

    # Resolve secrets without logging them.
    try:
        from .secrets import resolve_secret

        api_key = resolve_secret(
            value=config.get("api_key"),
            env=config.get("api_key_env") or "OPENAI_API_KEY",
            file_path=config.get("api_key_file"),
            required=False,
            name="API key",
        )
    except Exception:
        api_key = None

    if not api_key:
        return None

    headers = None
    if provider == "openrouter":
        headers = {
            "HTTP-Referer": "https://github.com/arxiv-paper-bot",
            "X-Title": "arXiv Paper Bot",
        }

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(config.get("temperature", 0.2)),
        timeout=config.get("timeout"),
        default_headers=headers,
    )


def _safe_json_loads(text: str) -> dict | None:
    """Parse JSON from a model response; strips common Markdown fences."""
    import json

    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1]
            if t.lstrip().startswith("json"):
                t = t.lstrip()[4:]
    t = t.strip()
    try:
        obj = json.loads(t)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _heuristic_intent(liked_papers: list[Paper], recent_searches: list[str]) -> dict:
    """Deterministic intent extraction based on keyword frequencies."""
    tokens: list[str] = []
    matched_keywords: list[str] = []

    for p in liked_papers:
        tokens.extend(_tokenize(p.title))
        tokens.extend(_tokenize(p.abstract))
        matched_keywords.extend([str(k).lower() for k in (p.matched_keywords or []) if k])

    tokens = [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]
    kw_counts = Counter(matched_keywords)
    tok_counts = Counter(tokens)

    main = [k for k, _ in kw_counts.most_common(8)]
    if len(main) < 5:
        main.extend([t for t, _ in tok_counts.most_common(10) if t not in main][: 8 - len(main)])

    emerging = [t for t in recent_searches if t and t.lower() not in main][:5]
    suggested = list(dict.fromkeys(main + emerging))[:12]

    conf = min(0.9, 0.3 + 0.05 * len(liked_papers))
    if not liked_papers:
        conf = 0.0

    return {
        "main_interests": main,
        "emerging_interests": emerging,
        "suggested_keywords": suggested,
        "confidence": conf,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
