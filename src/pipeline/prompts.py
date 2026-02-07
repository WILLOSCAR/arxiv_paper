"""Prompt templates for daily topic routing + rubric scoring."""

from __future__ import annotations

from .topics import DEFAULT_INTEREST_RUBRIC_TEXT, format_topic_options


ROUTER_AND_SCORER_SYSTEM_PROMPT = (
    "You are a research assistant. You must strictly follow the output format.\n"
    "Return valid JSON only. Do not wrap in Markdown. Do not include extra text."
)


def build_router_and_scorer_prompt(rubric_text: str | None = None) -> str:
    rubric = (rubric_text or DEFAULT_INTEREST_RUBRIC_TEXT).strip()
    topic_options = format_topic_options()

    return f"""You are doing paper triage and topic assignment.

## User Rubric (interests)
{rubric}

## Topic Taxonomy (choose one main topic_id 1-7 and one subtopic string)
{topic_options}

## Input
You will receive a JSON array of paper objects. Each paper has:
- paper_id (string)
- title (string)
- abstract (string)
- authors (list[string])
- comment (string, optional)
- primary_category (string, optional)
- categories (list[string], optional)
- published (string, optional)
- updated (string, optional)
- journal_ref (string, optional)
- doi (string, optional)
- rule_topic_id (int, a heuristic guess; may be wrong)
- rule_subtopic (string, a heuristic guess; may be wrong)
- rule_candidates (list of [topic_id, score] pairs; top-3)
- recall_hits (list[string])

## Task
For each paper:
1) Assign the best main topic_id (1-7) and a subtopic (must be one of the listed subtopics for that topic).
2) Score relevance to the user's rubric on a 0.0-1.0 scale.
3) Decide keep=true/false (false means not relevant enough; it will be dropped).
4) Provide a short reason (<=2 sentences) referencing concrete signals from the paper.
5) Provide a confidence 0.0-1.0.
6) Provide one_sentence_summary: one richer English sentence that clearly states problem, method, and key result.

## Output JSON format
Return a JSON array with the same order as input:
[
  {{{{
    "paper_id": "....",
    "topic_id": 1,
    "subtopic": "....",
    "relevance": 0.0,
    "keep": true,
    "reason": "....",
    "confidence": 0.0,
    "one_sentence_summary": "...."
  }}}},
  ...
]

Constraints:
- Output valid JSON only.
- Use numbers for topic_id, relevance, confidence.
- keep must be true/false.
- one_sentence_summary must be present for every paper, 32-80 words, and should not copy the abstract verbatim.
"""
