"""Topic taxonomy and rubric helpers (two-level)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal


TopicId = Literal[1, 2, 3, 4, 5, 6, 7]


@dataclass(frozen=True)
class TopicDef:
    """Topic definition with two-level labels."""

    topic_id: TopicId
    name: str
    subtopics: List[str]


TOPIC_DEFS: Dict[TopicId, TopicDef] = {
    1: TopicDef(
        topic_id=1,
        name="LLM/MLLM Foundations & Unified Modeling",
        subtopics=[
            "LLM Fundamentals & Alignment",
            "MLLM / Multimodal (VLM)",
            "Unified Multimodal Understanding & Generation",
        ],
    ),
    2: TopicDef(
        topic_id=2,
        name="Reasoning & Planning",
        subtopics=[
            "Reasoning (Math/Logic/Code)",
            "Tool Use & Planning (tool-use/planner)",
            "Reliability & Evaluation (reasoning eval)",
        ],
    ),
    3: TopicDef(
        topic_id=3,
        name="Agents & RL",
        subtopics=[
            "Agent Architectures (single/multi-agent, collaboration)",
            "RL for Agents (RLHF/online/long-horizon)",
            "Agent Evaluation & Reliability",
        ],
    ),
    4: TopicDef(
        topic_id=4,
        name="Memory & Personalization",
        subtopics=[
            "Long-term Memory (episodic/semantic)",
            "Memory Retrieval / Compression / Forgetting",
            "Personalization / User Modeling (personalization as memory)",
        ],
    ),
    5: TopicDef(
        topic_id=5,
        name="Agentic Search / Deep Research / AI Search",
        subtopics=[
            "Retrieval / IR / RAG (retrieval/rerank)",
            "Agentic Search (multi-hop/evidence aggregation)",
            "Deep Research Workflow (research agent/report)",
        ],
    ),
    6: TopicDef(
        topic_id=6,
        name="Technical Reports / Surveys / Systematic Synthesis",
        subtopics=[
            "Technical Reports / Method Summaries",
            "Survey / Taxonomy / Benchmark",
        ],
    ),
    7: TopicDef(
        topic_id=7,
        name="HCI + LLM (Human-AI Collaboration)",
        subtopics=[
            "Collaborative Workflows (co-writing/co-planning)",
            "Interaction & Controllability (UI/feedback)",
            "Human-in-the-loop Evaluation (efficiency/trust)",
        ],
    ),
}


DEFAULT_INTEREST_RUBRIC_TEXT = (
    "My research interests span multiple directions, with a core focus on LLM and MLLM systems. "
    "Within that scope, I especially care about agents and reinforcement learning (RL), memory mechanisms, reasoning, "
    "technical reports/systematic method synthesis, and unified multimodal understanding/generation models. "
    "I also maintain strong interest in agentic search, deep research, and AI search workflows, "
    "as well as work on human-model collaboration in HCI + LLM settings."
)


def format_topic_options() -> str:
    """Format topics/subtopics for prompts."""
    lines: List[str] = []
    for tid in sorted(TOPIC_DEFS):
        t = TOPIC_DEFS[tid]
        lines.append(f"{t.topic_id}. {t.name}")
        for idx, sub in enumerate(t.subtopics, start=1):
            lines.append(f"  - {tid}.{idx} {sub}")
    return "\n".join(lines)


def topic_limits() -> Dict[TopicId, int]:
    """Per-topic output limits."""
    limits: Dict[TopicId, int] = {1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3}
    return limits
