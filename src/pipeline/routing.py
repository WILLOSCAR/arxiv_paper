"""Rule-based recall + topic routing utilities (cheap stage before LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .topics import TopicId


def _normalize_text(text: str) -> str:
    # Keep it simple: lowercase and collapse whitespace.
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_paper_fulltext(paper: dict) -> str:
    """Build a single text blob from all fields we have from arXiv."""
    parts: List[str] = []
    for key in [
        "title",
        "abstract",
        "comment",
        "primary_category",
        "journal_ref",
        "doi",
    ]:
        v = paper.get(key)
        if v:
            parts.append(str(v))

    cats = paper.get("categories") or []
    if isinstance(cats, list) and cats:
        parts.append(" ".join([str(c) for c in cats if c]))

    # Authors are usually not a relevance signal, but harmless for recall.
    authors = paper.get("authors") or []
    if isinstance(authors, list) and authors:
        parts.append(" ".join([str(a) for a in authors if a]))

    # Some pipelines may attach derived fields; include them if present.
    meta = paper.get("meta") or {}
    if isinstance(meta, dict):
        for k in ["tasks", "methods", "datasets", "tags"]:
            vv = meta.get(k)
            if isinstance(vv, list) and vv:
                parts.append(" ".join([str(x) for x in vv if x]))
            elif isinstance(vv, str) and vv:
                parts.append(vv)

    return _normalize_text("\n".join(parts))


def build_recall_terms() -> List[str]:
    """Expanded recall terms (synonyms) for the first-stage retrieval."""
    terms = [
        # LLM core
        "llm",
        "llms",
        "large language model",
        "large language models",
        "large multimodal model",
        "large multimodal models",
        "language model",
        "language models",
        "foundation model",
        "foundation models",
        "prompt engineering",
        "instruction tuning",
        "instruction-tuning",
        "in-context",
        "in context",
        "prompting",
        "alignment",
        "rlhf",
        "rlaif",
        "dpo",
        # MLLM / multimodal
        "mllm",
        "mllms",
        "multimodal",
        "multi-modal",
        "vision-language",
        "vision language",
        "vision language model",
        "vision-language model",
        "vlm",
        "vlms",
        "multimodal large language model",
        "multimodal large language models",
        "vision-language model",
        "image-text",
        "image text",
        "text-to-image",
        "video-language",
        "audio-language",
        "vision-language-action",
        "unified model",
        "unified models",
        # Agent / tool use
        "agent",
        "agents",
        "agentic",
        "autonomous agent",
        "multi-agent",
        "multi agent",
        "agent framework",
        "tool use",
        "tool-use",
        "tool calling",
        "function calling",
        "toolformer",
        "react",
        "re-act",
        "planner",
        "planning",
        # RL
        "reinforcement learning",
        "rl",
        "policy",
        "actor-critic",
        "ppo",
        # Memory & personalization
        "memory",
        "long-term memory",
        "episodic memory",
        "semantic memory",
        "context compression",
        "context window",
        "external memory",
        "memory bank",
        "persona",
        "personality",
        "personalization",
        "personalised",
        "personalized",
        "user modeling",
        "user modelling",
        "preference learning",
        "user profile",
        # Reasoning
        "reasoning",
        "chain-of-thought",
        "chain of thought",
        "cot",
        "tree-of-thought",
        "tree of thought",
        "tot",
        "verification",
        "self-correction",
        # Search / IR / deep research
        "search",
        "retrieval",
        "rag",
        "retrieval-augmented",
        "retrieval augmented",
        "information retrieval",
        "web search",
        "search engine",
        "query rewriting",
        "query reformulation",
        "query",
        "rerank",
        "re-ranking",
        "ranking",
        "deep research",
        "research agent",
        # Reports / surveys
        "technical report",
        "systematization",
        "systematisation",
        "systematization of knowledge",
        "sok",
        "systematic review",
        "survey",
        "taxonomy",
        "benchmark",
        "review",
        # HCI + LLM
        "hci",
        "human-computer interaction",
        "human-ai",
        "human ai",
        "human-in-the-loop",
        "human in the loop",
        "user study",
        "user studies",
        "ux",
        "user experience",
        "interface",
        "interaction",
        "collaboration",
        "co-writing",
        "cowriting",
        "co-planning",
        "coplanning",
        "mixed-initiative",
        "copilot",
    ]

    # De-duplicate while preserving order.
    seen = set()
    out: List[str] = []
    for t in terms:
        tt = _normalize_text(t)
        if not tt or tt in seen:
            continue
        seen.add(tt)
        out.append(tt)
    return out


def _match_term(text: str, term: str) -> bool:
    """Heuristic match: word-boundary for single tokens; substring for phrases."""
    if not term:
        return False
    if " " in term or "-" in term or "+" in term:
        return term in text
    # Allow plural 's' for many short tokens (e.g., llm/llms), but keep strict for very short.
    if len(term) >= 3:
        pattern = r"\b" + re.escape(term) + r"s?\b"
    else:
        pattern = r"\b" + re.escape(term) + r"\b"
    return bool(re.search(pattern, text))


def recall_filter(
    papers: List[dict],
    recall_terms: Sequence[str],
    *,
    min_hits: int = 1,
) -> Tuple[List[dict], List[dict]]:
    """
    Filter papers by recall terms.

    Returns (kept, dropped). Each kept paper is annotated with:
      - recall_hits: list[str]
      - recall_hit_count: int
    """
    kept: List[dict] = []
    dropped: List[dict] = []

    for p in papers:
        text = build_paper_fulltext(p)
        hits: List[str] = []
        for term in recall_terms:
            if _match_term(text, term):
                hits.append(term)
        p2 = dict(p)
        p2["recall_hits"] = hits
        p2["recall_hit_count"] = len(hits)
        if len(hits) >= min_hits:
            kept.append(p2)
        else:
            dropped.append(p2)

    # More hits first (rough proxy), tie-break by published time if present.
    kept.sort(key=lambda x: (x.get("recall_hit_count", 0), x.get("published", "")), reverse=True)
    return kept, dropped


@dataclass(frozen=True)
class RouteResult:
    topic_id: TopicId
    subtopic: str
    score: float
    ambiguous: bool
    candidates: List[Tuple[TopicId, float]]


_TOPIC_KEYWORDS: Dict[TopicId, List[Tuple[str, float, str]]] = {
    1: [
        ("llm", 2.0, "LLM Fundamentals & Alignment"),
        ("large language model", 2.0, "LLM Fundamentals & Alignment"),
        ("instruction tuning", 1.5, "LLM Fundamentals & Alignment"),
        ("alignment", 1.5, "LLM Fundamentals & Alignment"),
        ("dpo", 1.0, "LLM Fundamentals & Alignment"),
        ("mllm", 2.0, "MLLM / Multimodal (VLM)"),
        ("vision-language", 2.0, "MLLM / Multimodal (VLM)"),
        ("multimodal", 1.5, "MLLM / Multimodal (VLM)"),
        ("vision-language-action", 1.0, "MLLM / Multimodal (VLM)"),
        ("unified model", 1.5, "Unified Multimodal Understanding & Generation"),
    ],
    2: [
        ("reasoning", 2.0, "Reasoning (Math/Logic/Code)"),
        ("chain-of-thought", 1.5, "Reasoning (Math/Logic/Code)"),
        ("tree-of-thought", 1.5, "Reasoning (Math/Logic/Code)"),
        ("planning", 1.5, "Tool Use & Planning (tool-use/planner)"),
        ("tool use", 1.5, "Tool Use & Planning (tool-use/planner)"),
        ("tool calling", 1.5, "Tool Use & Planning (tool-use/planner)"),
        ("function calling", 1.5, "Tool Use & Planning (tool-use/planner)"),
        ("react", 1.0, "Tool Use & Planning (tool-use/planner)"),
        ("verification", 1.0, "Reliability & Evaluation (reasoning eval)"),
        ("evaluation", 1.0, "Reliability & Evaluation (reasoning eval)"),
    ],
    3: [
        ("agent", 2.0, "Agent Architectures (single/multi-agent, collaboration)"),
        ("agentic", 2.0, "Agent Architectures (single/multi-agent, collaboration)"),
        ("multi-agent", 2.0, "Agent Architectures (single/multi-agent, collaboration)"),
        ("agent framework", 1.5, "Agent Architectures (single/multi-agent, collaboration)"),
        ("reinforcement learning", 2.0, "RL for Agents (RLHF/online/long-horizon)"),
        ("rlhf", 1.5, "RL for Agents (RLHF/online/long-horizon)"),
        ("policy", 1.0, "RL for Agents (RLHF/online/long-horizon)"),
    ],
    4: [
        ("memory", 2.0, "Long-term Memory (episodic/semantic)"),
        ("long-term memory", 2.0, "Long-term Memory (episodic/semantic)"),
        ("context compression", 1.5, "Memory Retrieval / Compression / Forgetting"),
        ("context window", 1.0, "Memory Retrieval / Compression / Forgetting"),
        ("external memory", 1.0, "Long-term Memory (episodic/semantic)"),
        ("personalization", 1.5, "Personalization / User Modeling (personalization as memory)"),
        ("persona", 1.0, "Personalization / User Modeling (personalization as memory)"),
        ("user modeling", 1.0, "Personalization / User Modeling (personalization as memory)"),
    ],
    5: [
        ("rag", 2.0, "Retrieval / IR / RAG (retrieval/rerank)"),
        ("retrieval", 1.5, "Retrieval / IR / RAG (retrieval/rerank)"),
        ("information retrieval", 2.0, "Retrieval / IR / RAG (retrieval/rerank)"),
        ("search", 1.5, "Agentic Search (multi-hop/evidence aggregation)"),
        ("web search", 2.0, "Agentic Search (multi-hop/evidence aggregation)"),
        ("search engine", 1.5, "Agentic Search (multi-hop/evidence aggregation)"),
        ("query rewriting", 1.5, "Retrieval / IR / RAG (retrieval/rerank)"),
        ("deep research", 2.0, "Deep Research Workflow (research agent/report)"),
        ("research agent", 1.5, "Deep Research Workflow (research agent/report)"),
        ("rerank", 1.5, "Retrieval / IR / RAG (retrieval/rerank)"),
    ],
    6: [
        ("technical report", 2.0, "Technical Reports / Method Summaries"),
        ("systematization", 2.0, "Technical Reports / Method Summaries"),
        ("systematization of knowledge", 2.0, "Technical Reports / Method Summaries"),
        ("sok", 2.0, "Technical Reports / Method Summaries"),
        ("systematic review", 1.5, "Survey / Taxonomy / Benchmark"),
        ("survey", 2.0, "Survey / Taxonomy / Benchmark"),
        ("taxonomy", 1.5, "Survey / Taxonomy / Benchmark"),
        ("benchmark", 1.5, "Survey / Taxonomy / Benchmark"),
        ("review", 1.0, "Survey / Taxonomy / Benchmark"),
    ],
    7: [
        ("hci", 2.0, "Interaction & Controllability (UI/feedback)"),
        ("human-computer interaction", 2.0, "Interaction & Controllability (UI/feedback)"),
        ("ux", 1.0, "Interaction & Controllability (UI/feedback)"),
        ("user experience", 1.0, "Interaction & Controllability (UI/feedback)"),
        ("user study", 2.0, "Human-in-the-loop Evaluation (efficiency/trust)"),
        ("interface", 1.5, "Interaction & Controllability (UI/feedback)"),
        ("interaction", 1.5, "Interaction & Controllability (UI/feedback)"),
        ("collaboration", 1.5, "Collaborative Workflows (co-writing/co-planning)"),
        ("mixed-initiative", 1.5, "Collaborative Workflows (co-writing/co-planning)"),
        ("human-in-the-loop", 2.0, "Human-in-the-loop Evaluation (efficiency/trust)"),
    ],
}


def route_by_rules(
    paper: dict,
    *,
    min_score: float = 2.0,
    ambiguity_delta: float = 0.75,
) -> RouteResult:
    """
    Route one paper into a main topic (two-level).

    Heuristic: term hits across all available fields + category priors.
    """
    text = build_paper_fulltext(paper)
    topic_scores: Dict[TopicId, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}
    best_subtopic: Dict[TopicId, Tuple[str, float]] = {tid: ("", 0.0) for tid in topic_scores}

    # Keyword scoring
    for tid, rules in _TOPIC_KEYWORDS.items():
        for term, weight, subtopic in rules:
            if _match_term(text, term):
                topic_scores[tid] += weight
                if weight > best_subtopic[tid][1]:
                    best_subtopic[tid] = (subtopic, weight)

    # Category priors (lightweight; prevent over-routing purely by category)
    primary = (paper.get("primary_category") or "").lower()
    cats = [str(c).lower() for c in (paper.get("categories") or []) if c]
    catset = set([primary] + cats)
    if "cs.hc" in catset:
        topic_scores[7] += 1.5
        if not best_subtopic[7][0]:
            best_subtopic[7] = ("Interaction & Controllability (UI/feedback)", 0.5)
    if "cs.ir" in catset:
        topic_scores[5] += 1.25
        if not best_subtopic[5][0]:
            best_subtopic[5] = ("Retrieval / IR / RAG (retrieval/rerank)", 0.5)
    if "cs.cl" in catset:
        topic_scores[1] += 0.75
        topic_scores[2] += 0.25
    if "cs.cv" in catset:
        topic_scores[1] += 0.5
    if "cs.lg" in catset:
        topic_scores[3] += 0.25
        topic_scores[2] += 0.25
        topic_scores[1] += 0.25
    if "cs.ai" in catset:
        topic_scores[1] += 0.25
        topic_scores[3] += 0.25

    ranked = sorted(topic_scores.items(), key=lambda kv: kv[1], reverse=True)
    top_tid, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    ambiguous = top_score < min_score or (top_score - second_score) < ambiguity_delta
    subtopic = best_subtopic[top_tid][0] or ""

    return RouteResult(
        topic_id=top_tid,
        subtopic=subtopic,
        score=top_score,
        ambiguous=ambiguous,
        candidates=[(tid, sc) for tid, sc in ranked[:3]],
    )
