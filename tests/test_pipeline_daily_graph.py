import json

import pytest

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def test_llm_node_errors_on_missing_key_in_strict_mode(monkeypatch):
    # Ensure no accidental API keys in env affect this test.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from src.pipeline.daily_graph import llm_adjudicate_and_score_node

    state = {
        "llm_enabled": True,
        "llm_config": {"api_key_env": "NON_EXISTENT_ENV"},
        "routed_papers": [
            {
                "arxiv_id": "p1",
                "title": "Test",
                "abstract": "Test",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": False,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            }
        ],
    }

    with pytest.raises(RuntimeError, match="Failed to initialize LLM"):
        llm_adjudicate_and_score_node(state)


def test_llm_node_ambiguous_only_scope(monkeypatch):
    from src.pipeline import daily_graph

    def fake_llm(prompt_value):
        # The last user message is the JSON batch.
        papers = json.loads(prompt_value.messages[-1].content)
        assert len(papers) == 2
        paper_ids = {p["paper_id"] for p in papers}
        assert paper_ids == {"p1", "p2"}
        return AIMessage(
            content=json.dumps(
                [
                    {
                        "paper_id": "p1",
                        "topic_id": 1,
                        "subtopic": "LLM Fundamentals & Alignment",
                        "relevance": 0.82,
                        "keep": True,
                        "reason": "LLM judged relevant.",
                        "confidence": 0.8,
                    },
                    {
                        "paper_id": "p2",
                        "topic_id": 5,
                        "subtopic": "Agentic Search (multi-hop/evidence aggregation)",
                        "relevance": 0.9,
                        "keep": True,
                        "reason": "LLM judged relevant.",
                        "confidence": 0.8,
                    }
                ]
            )
        )

    monkeypatch.setattr(daily_graph, "_build_llm", lambda *_args, **_kwargs: RunnableLambda(fake_llm))

    state = {
        "llm_enabled": True,
        "llm_config": {"scope": "ambiguous_only"},
        "routed_papers": [
            {
                "arxiv_id": "p1",
                "title": "Unambiguous",
                "abstract": "This is clearly about LLM alignment.",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": False,
                "rule_candidates": [[1, 3.0], [2, 1.0], [3, 0.0]],
                "recall_hits": ["llm"],
            },
            {
                "arxiv_id": "p2",
                "title": "Ambiguous",
                "abstract": "This mentions web search and agents.",
                "rule_topic_id": 1,
                "rule_subtopic": "",
                "rule_score": 1.0,
                "rule_ambiguous": True,
                "rule_candidates": [[1, 1.0], [5, 1.0], [3, 0.5]],
                "recall_hits": ["agent", "search"],
            },
        ],
    }

    out = daily_graph.llm_adjudicate_and_score_node(state)
    assert len(out["scored_papers"]) == 2

    scored_by_id = {p["paper_id"]: p for p in out["scored_papers"]}
    assert scored_by_id["p1"]["reason"] == "LLM judged relevant."
    assert scored_by_id["p2"]["reason"] == "LLM judged relevant."
    assert scored_by_id["p2"]["topic_id"] == 5
    assert scored_by_id["p2"]["relevance"] == 0.9


def test_llm_node_parallel_workers_process_batches(monkeypatch):
    from src.pipeline import daily_graph

    calls = {"count": 0}

    def fake_llm(prompt_value):
        papers = json.loads(prompt_value.messages[-1].content)
        out = []
        for paper in papers:
            out.append(
                {
                    "paper_id": paper["paper_id"],
                    "topic_id": 1,
                    "subtopic": "LLM Fundamentals & Alignment",
                    "relevance": 0.8,
                    "keep": True,
                    "reason": "parallel test",
                    "confidence": 0.9,
                    "one_sentence_summary": "Parallel summary.",
                }
            )
        calls["count"] += 1
        return AIMessage(content=json.dumps(out))

    monkeypatch.setattr(daily_graph, "_build_llm", lambda *_args, **_kwargs: RunnableLambda(fake_llm))

    state = {
        "llm_enabled": True,
        "llm_config": {"batch_size": 1, "parallel_workers": 3},
        "routed_papers": [
            {
                "arxiv_id": "p1",
                "title": "T1",
                "abstract": "A1",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": True,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            },
            {
                "arxiv_id": "p2",
                "title": "T2",
                "abstract": "A2",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": True,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            },
            {
                "arxiv_id": "p3",
                "title": "T3",
                "abstract": "A3",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": True,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            },
        ],
    }

    out = daily_graph.llm_adjudicate_and_score_node(state)

    assert len(out["scored_papers"]) == 3
    assert calls["count"] == 3
    for scored in out["scored_papers"]:
        assert scored["one_sentence_summary"] == "Parallel summary."



def test_llm_vote_reruns_primary_on_disagreement(monkeypatch):
    from src.pipeline import daily_graph

    calls = {"deepseek": 0, "oss": 0}

    def fake_build_llm(cfg, *, task):
        model = cfg.get("reasoning_model") or cfg.get("model")

        if model == "deepseek":
            def deepseek(prompt_value):
                calls["deepseek"] += 1
                # 1st run returns topic 5, rerun returns topic 4 (simulate instability).
                if calls["deepseek"] == 1:
                    out = [{"paper_id": "p1", "topic_id": 5, "subtopic": "Retrieval / IR / RAG (retrieval/rerank)", "relevance": 0.8, "keep": True, "reason": "ds1", "confidence": 0.8}]
                else:
                    out = [{"paper_id": "p1", "topic_id": 4, "subtopic": "Long-term Memory (episodic/semantic)", "relevance": 0.7, "keep": True, "reason": "ds2", "confidence": 0.7}]
                return AIMessage(content=json.dumps(out))

            return RunnableLambda(deepseek)

        if model == "oss":
            def oss(prompt_value):
                calls["oss"] += 1
                out = [{"paper_id": "p1", "topic_id": 3, "subtopic": "Agent Architectures (single/multi-agent, collaboration)", "relevance": 0.6, "keep": True, "reason": "oss", "confidence": 0.6}]
                return AIMessage(content=json.dumps(out))

            return RunnableLambda(oss)

        raise AssertionError(f"unexpected model: {model}")

    monkeypatch.setattr(daily_graph, "_build_llm", fake_build_llm)

    state = {
        "llm_enabled": True,
        "llm_config": {
            "reasoning_model": "deepseek",
            "vote_enabled": True,
            "vote_model": "oss",
            "batch_size": 1,
        },
        "routed_papers": [
            {
                "arxiv_id": "p1",
                "title": "T",
                "abstract": "A",
                "rule_topic_id": 5,
                "rule_subtopic": "",
                "rule_score": 3.0,
                "rule_ambiguous": True,
                "rule_candidates": [[5, 3.0], [3, 2.0], [4, 1.0]],
                "recall_hits": ["agent", "search"],
            }
        ],
    }

    out = daily_graph.llm_adjudicate_and_score_node(state)
    assert calls["oss"] == 1
    # DeepSeek called twice because OSS disagreed.
    assert calls["deepseek"] == 2
    scored = out["scored_papers"][0]
    assert scored["paper_id"] == "p1"
    assert scored["reason"] == "ds2"
    assert scored["topic_id"] == 4


def test_select_group_keeps_rich_metadata():
    from src.pipeline.daily_graph import select_and_group_node

    state = {
        "day": "2026-02-06",
        "timezone": "Asia/Shanghai",
        "relevance_threshold": 0.55,
        "scored_papers": [
            {
                "arxiv_id": "p-rich",
                "title": "Rich Meta Paper",
                "abstract": "Abstract text",
                "authors": ["Alice", "Bob"],
                "primary_category": "cs.AI",
                "categories": ["cs.AI", "cs.CL"],
                "published": "2026-02-06T01:00:00+08:00",
                "updated": "2026-02-06T09:00:00+08:00",
                "comment": "with code",
                "journal_ref": "arXiv preprint",
                "doi": "10.1000/test",
                "entry_url": "https://arxiv.org/abs/2602.00001",
                "pdf_url": "https://arxiv.org/pdf/2602.00001",
                "topic_id": 1,
                "subtopic": "LLM Fundamentals & Alignment",
                "relevance": 0.88,
                "confidence": 0.77,
                "reason": "high match",
                "one_sentence_summary": "One-line summary",
                "keep": True,
                "recall_hits": ["llm", "alignment"],
                "recall_hit_count": 2,
            }
        ],
    }

    out = select_and_group_node(state)
    assert out["grouped_output"]["llm_enabled"] is True
    topics = out["grouped_output"]["topics"]
    topic1 = [t for t in topics if t["topic_id"] == 1][0]
    assert topic1["count"] == 1
    paper = topic1["papers"][0]
    assert paper["abstract"] == "Abstract text"
    assert paper["authors"] == ["Alice", "Bob"]
    assert paper["comment"] == "with code"
    assert paper["doi"] == "10.1000/test"
    assert paper["journal_ref"] == "arXiv preprint"
    assert paper["recall_hit_count"] == 2
    assert paper["one_sentence_summary"] == "One-line summary"


def test_parse_json_array_from_llm_mixed_text():
    from src.pipeline.daily_graph import _parse_json_array_from_llm

    raw = "analysis...\n```json\n[{\"paper_id\":\"p1\",\"topic_id\":1,\"keep\":true}]\n```\nextra"
    out = _parse_json_array_from_llm(raw)
    assert isinstance(out, list)
    assert out[0]["paper_id"] == "p1"


def test_parse_json_array_from_llm_dict_wrapper():
    from src.pipeline.daily_graph import _parse_json_array_from_llm

    raw = '{"results": [{"paper_id": "p2", "topic_id": 3, "keep": true}]}'
    out = _parse_json_array_from_llm(raw)
    assert isinstance(out, list)
    assert out[0]["paper_id"] == "p2"


def test_rule_fallback_generates_one_sentence_summary():
    from src.pipeline.daily_graph import llm_adjudicate_and_score_node

    state = {
        "llm_enabled": False,
        "llm_config": {"allow_rule_fallback": True},
        "routed_papers": [
            {
                "arxiv_id": "p-fallback",
                "title": "Fallback Paper",
                "abstract": "This paper introduces a robust calibration strategy for LLM steering. It also reports strong gains.",
                "rule_topic_id": 1,
                "rule_subtopic": "LLM Fundamentals & Alignment",
                "rule_score": 3.0,
                "rule_ambiguous": False,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            }
        ],
    }

    out = llm_adjudicate_and_score_node(state)
    scored = out["scored_papers"][0]
    assert scored["one_sentence_summary"].startswith("This paper introduces a robust calibration strategy")
