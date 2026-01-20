"""Tests for daily pipeline rule-based recall and routing."""

import unittest

from src.pipeline.routing import build_recall_terms, recall_filter, route_by_rules


class TestRecallTerms(unittest.TestCase):
    def test_terms_are_deduped(self):
        terms = build_recall_terms()
        self.assertGreater(len(terms), 10)
        self.assertEqual(len(terms), len(set(terms)))


class TestRecallFilter(unittest.TestCase):
    def test_recall_keeps_matching_papers(self):
        papers = [
            {
                "arxiv_id": "1",
                "title": "An Agentic Search Framework for LLMs",
                "abstract": "We propose a retrieval-augmented agent for deep research.",
                "primary_category": "cs.AI",
                "categories": ["cs.AI", "cs.IR"],
            },
            {
                "arxiv_id": "2",
                "title": "Classical Image Segmentation with U-Net",
                "abstract": "We study convolutional segmentation models.",
                "primary_category": "cs.CV",
                "categories": ["cs.CV"],
            },
        ]
        kept, dropped = recall_filter(papers, build_recall_terms(), min_hits=1)
        kept_ids = {p["arxiv_id"] for p in kept}
        self.assertIn("1", kept_ids)
        self.assertNotIn("2", kept_ids)


class TestRouting(unittest.TestCase):
    def test_route_hci(self):
        paper = {
            "arxiv_id": "x",
            "title": "Human-AI Collaboration for LLM Writing Interfaces",
            "abstract": "We present a user study and an interface for co-writing.",
            "primary_category": "cs.HC",
            "categories": ["cs.HC"],
        }
        r = route_by_rules(paper)
        self.assertEqual(r.topic_id, 7)

    def test_route_search(self):
        paper = {
            "arxiv_id": "x",
            "title": "RAG with Reranking for Information Retrieval",
            "abstract": "We study retrieval augmented generation for IR.",
            "primary_category": "cs.IR",
            "categories": ["cs.IR", "cs.CL"],
        }
        r = route_by_rules(paper)
        self.assertEqual(r.topic_id, 5)

    def test_route_memory(self):
        paper = {
            "arxiv_id": "x",
            "title": "Long-term Memory for Personalized LLM Agents",
            "abstract": "We build episodic memory and user profiles for personalization.",
            "primary_category": "cs.AI",
            "categories": ["cs.AI"],
        }
        r = route_by_rules(paper)
        self.assertEqual(r.topic_id, 4)


if __name__ == "__main__":
    unittest.main()

