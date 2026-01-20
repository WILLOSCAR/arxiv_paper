"""Topic taxonomy and rubric helpers (two-level)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple


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
        name="LLM/MLLM 基座与统一建模",
        subtopics=[
            "LLM 基础方法与对齐",
            "MLLM / 多模态（VLM）",
            "多模态理解与生成统一建模",
        ],
    ),
    2: TopicDef(
        topic_id=2,
        name="推理与规划",
        subtopics=[
            "推理（数学/逻辑/程序）",
            "工具使用与规划（tool-use/planner）",
            "可靠性与评测（reasoning eval）",
        ],
    ),
    3: TopicDef(
        topic_id=3,
        name="Agent 与 RL",
        subtopics=[
            "Agent 架构（单/多 agent、协作）",
            "RL for Agents（RLHF/online/long-horizon）",
            "Agent 评测与可靠性",
        ],
    ),
    4: TopicDef(
        topic_id=4,
        name="记忆机制与个性化",
        subtopics=[
            "长期记忆（episodic/semantic）",
            "记忆检索/压缩/遗忘",
            "个性化/用户建模（personalization as memory）",
        ],
    ),
    5: TopicDef(
        topic_id=5,
        name="Agentic Search / Deep Research / AI 搜索",
        subtopics=[
            "检索/IR/RAG（retrieval/rerank）",
            "Agentic Search（多跳/证据聚合）",
            "Deep Research 工作流（research agent/报告）",
        ],
    ),
    6: TopicDef(
        topic_id=6,
        name="Technical Report / Survey / 系统性总结",
        subtopics=[
            "Technical Report / 方法总结",
            "Survey/Taxonomy/Benchmark",
        ],
    ),
    7: TopicDef(
        topic_id=7,
        name="HCI + LLM（人机协作）",
        subtopics=[
            "协作工作流（co-writing/co-planning）",
            "交互与可控性（UI/feedback）",
            "人类在环评测（效率/信任）",
        ],
    ),
}


DEFAULT_INTEREST_RUBRIC_TEXT = (
    "我的科研兴趣覆盖多个方向，整体聚焦于 LLM 与 MLLM 这一大类问题。"
    "在此之上，我尤其关注 agent 与强化学习（RL）、记忆机制（memory）、推理（reasoning）、"
    "technical report / 系统性方法总结，以及多模态理解与生成的统一建模（unified models）。"
    "同时，我也对 agentic search / deep research / AI 搜索 等方向保持持续兴趣，"
    "并关注 HCI + LLM 交叉领域中人与模型协作方式的研究。"
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
    limits: Dict[TopicId, int] = {1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 5}
    return limits

