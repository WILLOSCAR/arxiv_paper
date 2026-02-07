"""Calendar-day daily pipeline graph (recall -> route -> LLM adjudication -> prune)."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ..fetcher import ArxivFetcher
from ..models import FetchConfig
from ..secrets import resolve_secret
from .prompts import ROUTER_AND_SCORER_SYSTEM_PROMPT, build_router_and_scorer_prompt
from .routing import build_recall_terms, recall_filter, route_by_rules
from .topics import DEFAULT_INTEREST_RUBRIC_TEXT, TOPIC_DEFS, TopicId, topic_limits

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1]
            if t.lstrip().startswith("json"):
                t = t.lstrip()[4:]
    return t.strip()


def _chunk(items: List[dict], size: int) -> List[List[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _extract_first_json_array(text: str) -> str:
    """Extract first top-level JSON array from a mixed LLM response string."""
    src = text or ""
    start = src.find("[")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(src)):
        ch = src[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            depth += 1
            continue
        if ch == "]":
            depth -= 1
            if depth == 0:
                return src[start : idx + 1]

    return ""


def _parse_json_array_from_llm(content: str) -> List[dict]:
    """Parse LLM output and normalize to a JSON list of objects."""
    text = _strip_code_fences(content)
    if not text:
        raise ValueError("Empty LLM output")

    candidates = [text]
    extracted = _extract_first_json_array(text)
    if extracted and extracted != text:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("results", "papers", "output", "data"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return value

    raise ValueError("LLM output is not a JSON array")


def _one_sentence_summary(text: str, *, max_chars: int = 260) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    sentence = raw.split("\n", 1)[0].strip()
    for sep in ["。", "！", "？", ". ", "! ", "? "]:
        if sep in sentence:
            sentence = sentence.split(sep, 1)[0].strip()
            break

    if not sentence:
        return ""
    if len(sentence) > max_chars:
        return sentence[: max_chars - 3].rstrip() + "..."
    return sentence


def _default_headers(llm_cfg: dict) -> dict[str, str] | None:
    if (llm_cfg.get("provider") or "").lower() != "openrouter":
        return None
    return {
        "HTTP-Referer": "https://github.com/arxiv-paper-bot",
        "X-Title": "arXiv Paper Bot",
    }


def _build_llm(llm_cfg: dict, *, task: str) -> ChatOpenAI:
    # Resolve API key without storing it in state.
    api_key = resolve_secret(
        value=llm_cfg.get("api_key"),
        env=llm_cfg.get("api_key_env") or "OPENAI_API_KEY",
        file_path=llm_cfg.get("api_key_file"),
        required=True,
        name="API key",
    )

    model = llm_cfg.get("model") or "gpt-4o"
    if task == "score":
        model = llm_cfg.get("reasoning_model") or model
    else:
        model = llm_cfg.get("simple_model") or model

    return ChatOpenAI(
        model=model,
        temperature=llm_cfg.get("temperature", 0.2),
        api_key=api_key,
        base_url=llm_cfg.get("base_url") or None,
        timeout=llm_cfg.get("timeout"),
        default_headers=_default_headers(llm_cfg),
    )


def _today_in_tz(timezone_name: str) -> date:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(timezone_name)
    return datetime.now(tz).date()


class DailyState(TypedDict, total=False):
    # Inputs
    day: str  # YYYY-MM-DD
    timezone: str
    arxiv_categories: List[str]
    arxiv_max_results: int
    rubric_text: str
    llm_enabled: bool
    llm_config: dict
    relevance_threshold: float

    # Intermediate
    raw_papers: List[dict]
    fetched_papers: List[dict]
    recalled_papers: List[dict]
    dropped_papers: List[dict]
    routed_papers: List[dict]
    scored_papers: List[dict]

    # Outputs
    grouped_output: dict


def fetch_daily_node(state: DailyState) -> dict:
    tz = state.get("timezone") or "Asia/Shanghai"
    day_str = state.get("day")
    if not day_str:
        day = _today_in_tz(tz)
        day_str = day.isoformat()
    else:
        day = date.fromisoformat(day_str)

    categories = state.get("arxiv_categories") or [
        "cs.AI",
        "cs.CV",
        "cs.IR",
        "cs.HC",
        "cs.CL",
        "cs.LG",
    ]
    max_results = int(state.get("arxiv_max_results") or 2000)

    fetcher = ArxivFetcher(
        FetchConfig(
            categories=categories,
            max_results=max_results,
            sort_by="submittedDate",
            sort_order="descending",
            fetch_mode="category_only",
        )
    )

    papers = fetcher.fetch_papers_for_calendar_day(day, timezone_name=tz)

    # Convert to dict for graph state.
    paper_dicts = [p.to_dict() for p in papers]
    for p, obj in zip(paper_dicts, papers):
        # Ensure optional fields are present in dict (to_dict already includes these).
        p.setdefault("comment", obj.comment)
        p.setdefault("journal_ref", obj.journal_ref)
        p.setdefault("doi", obj.doi)
        p.setdefault("primary_category", obj.primary_category)
        p.setdefault("categories", obj.categories)

    logger.info("Fetched %s papers for %s (%s)", len(paper_dicts), day_str, tz)
    raw_copy = [dict(p) for p in paper_dicts]
    return {
        "day": day_str,
        "timezone": tz,
        "raw_papers": raw_copy,
        "fetched_papers": paper_dicts,
    }


def enrich_meta_rules_node(state: DailyState) -> dict:
    papers = state.get("fetched_papers") or []
    enriched: List[dict] = []
    for p in papers:
        text = (
            f"{p.get('title','')}\n{p.get('abstract','')}\n{p.get('comment','')}\n"
            f"{p.get('primary_category','')}\n{' '.join(p.get('categories') or [])}"
        ).lower()
        meta = {
            "has_code": ("github" in text) or ("code" in text),
            "has_user_study": ("user study" in text) or ("participants" in text),
            "is_survey_or_report": any(
                k in text
                for k in ["survey", "technical report", "systematization", "taxonomy", "benchmark", "review"]
            ),
        }
        p2 = dict(p)
        p2["meta"] = meta
        p2["all_text"] = text
        enriched.append(p2)
    return {"fetched_papers": enriched}


def recall_node(state: DailyState) -> dict:
    papers = state.get("fetched_papers") or []
    terms = build_recall_terms()
    kept, dropped = recall_filter(papers, terms, min_hits=1)
    logger.info("Recall kept %s / %s papers", len(kept), len(papers))
    return {"recalled_papers": kept, "dropped_papers": dropped}


def route_rules_node(state: DailyState) -> dict:
    papers = state.get("recalled_papers") or []
    routed: List[dict] = []
    for p in papers:
        rr = route_by_rules(p)
        p2 = dict(p)
        p2["rule_topic_id"] = rr.topic_id
        p2["rule_subtopic"] = rr.subtopic
        p2["rule_score"] = rr.score
        p2["rule_ambiguous"] = rr.ambiguous
        p2["rule_candidates"] = [[tid, sc] for tid, sc in rr.candidates]
        routed.append(p2)
    return {"routed_papers": routed}


def llm_adjudicate_and_score_node(state: DailyState) -> dict:
    papers = state.get("routed_papers") or []
    if not papers:
        return {"scored_papers": []}

    llm_cfg = state.get("llm_config") or {}
    allow_rule_fallback = bool(llm_cfg.get("allow_rule_fallback", False))

    def _consistent(a_items: List[dict], b_items: List[dict]) -> bool:
        """Agreement check between two batch outputs by paper_id/topic/keep."""
        a_map = {str(item.get("paper_id") or "").strip(): item for item in a_items}
        b_map = {str(item.get("paper_id") or "").strip(): item for item in b_items}
        if not a_map or not b_map:
            return False

        shared_ids = [pid for pid in a_map if pid and pid in b_map]
        if len(shared_ids) != len(a_map):
            return False

        for pid in shared_ids:
            a = a_map[pid]
            b = b_map[pid]
            try:
                if int(a.get("topic_id")) != int(b.get("topic_id")):
                    return False
            except Exception:
                return False
            if bool(a.get("keep")) != bool(b.get("keep")):
                return False
        return True

    def _rule_fallback_for(p: dict, *, reason: str, confidence: float) -> dict:
        """Rule-only fallback decision (keeps secrets out of state/output)."""
        # Rough normalization: rule_score in [0, ~6] -> relevance in [0, 1]
        rule_score = float(p.get("rule_score", 0.0) or 0.0)
        fallback_summary = _one_sentence_summary(
            str(p.get("abstract") or "") or str(p.get("title") or "")
        )
        return {
            "paper_id": p.get("arxiv_id"),
            "topic_id": p.get("rule_topic_id"),
            "subtopic": p.get("rule_subtopic") or "",
            "relevance": min(1.0, rule_score / 6.0),
            "keep": bool(rule_score >= 2.0),
            "reason": reason,
            "confidence": confidence,
            "one_sentence_summary": fallback_summary,
        }

    if not state.get("llm_enabled", True):
        if not allow_rule_fallback:
            raise RuntimeError("LLM is required for daily pipeline scoring (llm_enabled=false)")

        scored: List[dict] = []
        for p in papers:
            p2 = dict(p)
            p2.update(
                _rule_fallback_for(
                    p,
                    reason="Fallback (no LLM): matched keywords + category priors.",
                    confidence=0.2,
                )
            )
            scored.append(p2)
        return {"scored_papers": scored}

    rubric_text = state.get("rubric_text") or DEFAULT_INTEREST_RUBRIC_TEXT

    try:
        llm_primary = _build_llm(llm_cfg, task="score")
    except Exception as exc:
        if not allow_rule_fallback:
            raise RuntimeError(f"Failed to initialize LLM: {exc}") from exc

        logger.warning("LLM disabled due to config error: %s", exc)
        scored: List[dict] = []
        for p in papers:
            p2 = dict(p)
            p2.update(
                _rule_fallback_for(
                    p,
                    reason="Fallback (LLM config error): matched keywords + category priors.",
                    confidence=0.2,
                )
            )
            scored.append(p2)
        return {"llm_enabled": False, "scored_papers": scored}

    vote_enabled = bool(llm_cfg.get("vote_enabled") or llm_cfg.get("vote_model"))
    vote_model = (llm_cfg.get("vote_model") or "").strip()
    llm_secondary = None
    if vote_enabled and vote_model:
        try:
            cfg2 = dict(llm_cfg)
            # For scoring tasks, _build_llm picks `reasoning_model`, so override it.
            cfg2["reasoning_model"] = vote_model
            llm_secondary = _build_llm(cfg2, task="score")
        except Exception as exc:
            # Secondary model is best-effort; keep going with primary only.
            logger.warning("LLM vote disabled (secondary model init failed): %s", exc)
            llm_secondary = None

    llm_scope = (llm_cfg.get("scope") or llm_cfg.get("mode") or "all").strip().lower()
    if llm_scope in {"ambiguous", "ambiguous_only", "ambiguous-only"}:
        if allow_rule_fallback:
            to_llm = [p for p in papers if p.get("rule_ambiguous")]
            fallback_only = [p for p in papers if not p.get("rule_ambiguous")]
        else:
            logger.info("LLM strict mode active: ignoring ambiguous_only scope and scoring all recalled papers")
            to_llm = list(papers)
            fallback_only = []
    else:
        to_llm = list(papers)
        fallback_only = []

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ROUTER_AND_SCORER_SYSTEM_PROMPT),
            ("user", build_router_and_scorer_prompt(rubric_text)),
            ("user", "{papers_json}"),
        ]
    )

    results_by_id: Dict[str, dict] = {}
    # Pre-fill rule fallback results for papers we won't send to the LLM (e.g. unambiguous).
    for p in fallback_only:
        pid = str(p.get("arxiv_id"))
        results_by_id[pid] = _rule_fallback_for(
            p,
            reason="Fallback (rule-only): unambiguous topic routing.",
            confidence=0.2,
        )

    batch_size = int(llm_cfg.get("batch_size") or 15)
    parallel_workers = max(1, int(llm_cfg.get("parallel_workers") or 1))

    def _build_batch_inputs(batch_papers: List[dict]) -> List[dict]:
        inputs: List[dict] = []
        for p in batch_papers:
            inputs.append(
                {
                    "paper_id": p.get("arxiv_id"),
                    "title": p.get("title", "")[:300],
                    "abstract": p.get("abstract", "")[:1600],
                    "authors": (p.get("authors") or [])[:10],
                    "comment": (p.get("comment") or "")[:400],
                    "primary_category": p.get("primary_category", ""),
                    "categories": p.get("categories") or [],
                    "published": p.get("published"),
                    "updated": p.get("updated"),
                    "journal_ref": p.get("journal_ref") or "",
                    "doi": p.get("doi") or "",
                    "rule_topic_id": p.get("rule_topic_id"),
                    "rule_subtopic": p.get("rule_subtopic") or "",
                    "rule_candidates": p.get("rule_candidates") or [],
                    "recall_hits": (p.get("recall_hits") or [])[:10],
                }
            )
        return inputs

    def _invoke_with_retries(model: Any, batch_json: str, retries: int) -> List[dict]:
        parsed: Optional[List[dict]] = None
        last_error: Optional[Exception] = None
        for _ in range(retries + 1):
            try:
                msg = (prompt | model).invoke({"papers_json": batch_json})
                parsed = _parse_json_array_from_llm(getattr(msg, "content", "") or "")
                break
            except Exception as exc:
                last_error = exc
        if parsed is None:
            raise last_error or ValueError("LLM returned no parsable output")
        return parsed

    def _run_one_batch(batch: List[dict]) -> Dict[str, dict]:
        try:
            inputs = _build_batch_inputs(batch)
            batch_json = json.dumps(inputs, ensure_ascii=False)
            retries = max(0, int(llm_cfg.get("batch_retries") or 1))

            parsed_primary = _invoke_with_retries(llm_primary, batch_json, retries)
            parsed_final = parsed_primary

            if llm_secondary is not None:
                try:
                    parsed_secondary = _invoke_with_retries(llm_secondary, batch_json, 0)
                    if parsed_primary and parsed_secondary and not _consistent(parsed_primary, parsed_secondary):
                        parsed_rerun = _invoke_with_retries(llm_primary, batch_json, retries)
                        if parsed_rerun:
                            parsed_final = parsed_rerun
                except Exception as exc:
                    # Secondary call is best-effort; keep primary output.
                    logger.warning("LLM vote skipped for batch (secondary error): %s", exc)

            out: Dict[str, dict] = {}
            for item in parsed_final:
                paper_id = str(item.get("paper_id") or "").strip()
                if not paper_id:
                    continue
                out[paper_id] = item

            for p in batch:
                pid = str(p.get("arxiv_id") or "").strip()
                if pid and pid not in out:
                    if not allow_rule_fallback:
                        raise RuntimeError(f"LLM output missed paper_id={pid}")
                    out[pid] = _rule_fallback_for(
                        p,
                        reason="Fallback (LLM missing paper result): matched keywords + category priors.",
                        confidence=0.2,
                    )

            return out
        except Exception as exc:
            if not allow_rule_fallback:
                raise RuntimeError(f"LLM batch failed: {exc}") from exc

            logger.warning("LLM batch failed, using rule fallback for batch: %s", exc)
            fallback_out: Dict[str, dict] = {}
            for p in batch:
                pid = str(p.get("arxiv_id") or "").strip()
                fallback_out[pid] = _rule_fallback_for(
                    p,
                    reason="Fallback (LLM batch error): matched keywords + category priors.",
                    confidence=0.2,
                )
            return fallback_out

    batches = _chunk(to_llm, batch_size)
    if parallel_workers <= 1 or len(batches) <= 1:
        for batch in batches:
            results_by_id.update(_run_one_batch(batch))
    else:
        workers = min(parallel_workers, len(batches))
        logger.info("LLM batching: %s batches with %s parallel workers", len(batches), workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_run_one_batch, batch) for batch in batches]
            for fut in as_completed(futures):
                results_by_id.update(fut.result())

    scored: List[dict] = []
    for p in papers:
        pid = str(p.get("arxiv_id"))
        r = results_by_id.get(pid)
        if not r:
            if not allow_rule_fallback:
                raise RuntimeError(f"Missing LLM result for paper_id={pid}")

            r = _rule_fallback_for(
                p,
                reason="Fallback: missing LLM result.",
                confidence=0.1,
            )

        p2 = dict(p)
        # Keep a stable id field across stages (paper_id == arxiv_id).
        p2["paper_id"] = pid
        # Normalize / validate fields.
        topic_id = r.get("topic_id", p.get("rule_topic_id"))
        try:
            topic_id_int = int(topic_id)
        except Exception:
            topic_id_int = int(p.get("rule_topic_id") or 1)
        if topic_id_int not in TOPIC_DEFS:
            topic_id_int = int(p.get("rule_topic_id") or 1)

        p2["topic_id"] = topic_id_int
        p2["topic_name"] = TOPIC_DEFS[topic_id_int].name
        p2["subtopic"] = str(r.get("subtopic") or p.get("rule_subtopic") or "")
        try:
            p2["relevance"] = float(r.get("relevance", 0.0))
        except Exception:
            p2["relevance"] = 0.0
        p2["keep"] = bool(r.get("keep", False))
        p2["reason"] = str(r.get("reason") or "")
        try:
            p2["confidence"] = float(r.get("confidence", 0.0))
        except Exception:
            p2["confidence"] = 0.0

        summary_text = str(r.get("one_sentence_summary") or "").strip()
        if not summary_text:
            summary_text = _one_sentence_summary(
                p2["reason"] or str(p.get("abstract") or "") or str(p.get("title") or "")
            )
        p2["one_sentence_summary"] = summary_text

        scored.append(p2)

    return {"scored_papers": scored}


def select_and_group_node(state: DailyState) -> dict:
    papers = state.get("scored_papers") or []
    limits = topic_limits()

    # Basic prune threshold (configurable later).
    try:
        threshold = float(state.get("relevance_threshold") or 0.55)
    except Exception:
        threshold = 0.55
    threshold = max(0.0, min(1.0, threshold))

    grouped: Dict[int, List[dict]] = {tid: [] for tid in sorted(TOPIC_DEFS)}
    for p in papers:
        if not p.get("keep"):
            continue
        if float(p.get("relevance") or 0.0) < threshold:
            continue
        tid = int(p.get("topic_id") or p.get("rule_topic_id") or 1)
        if tid not in grouped:
            continue
        grouped[tid].append(p)

    for tid in grouped:
        grouped[tid].sort(
            key=lambda x: (
                float(x.get("relevance") or 0.0),
                float(x.get("rule_score") or 0.0),
                int(x.get("recall_hit_count") or 0),
            ),
            reverse=True,
        )
        grouped[tid] = grouped[tid][: limits[tid]]

    # Build final output payload (stable, JSON-friendly).
    topics_out: List[dict] = []
    for tid in sorted(TOPIC_DEFS):
        tdef = TOPIC_DEFS[tid]
        papers_out: List[dict] = []
        for p in grouped[tid]:
            papers_out.append(
                {
                    "paper_id": p.get("arxiv_id"),
                    "title": p.get("title"),
                    "abstract": p.get("abstract") or "",
                    "authors": p.get("authors") or [],
                    "primary_category": p.get("primary_category"),
                    "categories": p.get("categories") or [],
                    "published": p.get("published"),
                    "updated": p.get("updated"),
                    "comment": p.get("comment") or "",
                    "journal_ref": p.get("journal_ref") or "",
                    "doi": p.get("doi") or "",
                    "entry_url": p.get("entry_url"),
                    "pdf_url": p.get("pdf_url"),
                    "topic_id": tid,
                    "topic": tdef.name,
                    "subtopic": p.get("subtopic") or "",
                    "relevance": p.get("relevance"),
                    "confidence": p.get("confidence"),
                    "reason": p.get("reason") or "",
                    "one_sentence_summary": p.get("one_sentence_summary") or "",
                    "recall_hits": (p.get("recall_hits") or [])[:10],
                    "recall_hit_count": int(p.get("recall_hit_count") or 0),
                }
            )

        topics_out.append(
            {
                "topic_id": tid,
                "topic": tdef.name,
                "limit": limits[tid],
                "count": len(papers_out),
                "papers": papers_out,
            }
        )

    output = {
        "day": state.get("day"),
        "timezone": state.get("timezone"),
        "rubric": state.get("rubric_text") or DEFAULT_INTEREST_RUBRIC_TEXT,
        "threshold": threshold,
        "llm_enabled": bool(state.get("llm_enabled", True)),
        "topics": topics_out,
    }

    return {"grouped_output": output}


def build_daily_graph() -> Any:
    builder = StateGraph(DailyState)
    builder.add_node("fetch_daily", fetch_daily_node)
    builder.add_node("enrich_meta", enrich_meta_rules_node)
    builder.add_node("recall", recall_node)
    builder.add_node("route_rules", route_rules_node)
    builder.add_node("llm_score", llm_adjudicate_and_score_node)
    builder.add_node("select_group", select_and_group_node)

    builder.add_edge(START, "fetch_daily")
    builder.add_edge("fetch_daily", "enrich_meta")
    builder.add_edge("enrich_meta", "recall")
    builder.add_edge("recall", "route_rules")
    builder.add_edge("route_rules", "llm_score")
    builder.add_edge("llm_score", "select_group")
    builder.add_edge("select_group", END)

    graph = builder.compile(checkpointer=MemorySaver())
    return graph
