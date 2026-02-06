import json

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def test_llm_node_falls_back_on_missing_key(monkeypatch):
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
                "rule_subtopic": "LLM 基础方法与对齐",
                "rule_score": 3.0,
                "rule_ambiguous": False,
                "rule_candidates": [[1, 3.0]],
                "recall_hits": ["llm"],
            }
        ],
    }

    out = llm_adjudicate_and_score_node(state)
    assert out["llm_enabled"] is False
    assert len(out["scored_papers"]) == 1
    scored = out["scored_papers"][0]
    assert scored["paper_id"] == "p1"
    assert scored["keep"] is True
    assert scored["topic_id"] == 1
    assert scored["relevance"] == 0.5


def test_llm_node_ambiguous_only_scope(monkeypatch):
    from src.pipeline import daily_graph

    def fake_llm(prompt_value):
        # The last user message is the JSON batch.
        papers = json.loads(prompt_value.messages[-1].content)
        assert len(papers) == 1
        assert papers[0]["paper_id"] == "p2"
        return AIMessage(
            content=json.dumps(
                [
                    {
                        "paper_id": "p2",
                        "topic_id": 5,
                        "subtopic": "Agentic Search（多跳/证据聚合）",
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
                "rule_subtopic": "LLM 基础方法与对齐",
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
    assert scored_by_id["p1"]["reason"].startswith("Fallback (rule-only)")
    assert scored_by_id["p2"]["reason"] == "LLM judged relevant."
    assert scored_by_id["p2"]["topic_id"] == 5
    assert scored_by_id["p2"]["relevance"] == 0.9


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
                    out = [{"paper_id": "p1", "topic_id": 5, "subtopic": "检索/IR/RAG（retrieval/rerank）", "relevance": 0.8, "keep": True, "reason": "ds1", "confidence": 0.8}]
                else:
                    out = [{"paper_id": "p1", "topic_id": 4, "subtopic": "长期记忆（episodic/semantic）", "relevance": 0.7, "keep": True, "reason": "ds2", "confidence": 0.7}]
                return AIMessage(content=json.dumps(out))

            return RunnableLambda(deepseek)

        if model == "oss":
            def oss(prompt_value):
                calls["oss"] += 1
                out = [{"paper_id": "p1", "topic_id": 3, "subtopic": "Agent 架构（单/多 agent、协作）", "relevance": 0.6, "keep": True, "reason": "oss", "confidence": 0.6}]
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
