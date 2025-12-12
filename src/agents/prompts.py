"""Prompt templates for LangGraph agents."""

# ===== Analysis Agent Prompt =====
ANALYSIS_PROMPT = """You are a research interest analyzer. Analyze the user's paper reading history to identify their research interests.

## Liked Papers (User showed interest):
{liked_papers}

## Disliked Papers (User showed no interest):
{disliked_papers}

## Total Papers Analyzed: {paper_count}

## Task:
Analyze the user's research interests and output a JSON with:
1. **main_interests**: Core research topics the user is interested in (2-5 specific topics)
2. **emerging_interests**: New areas the user seems to be exploring (1-3 topics)
3. **disliked_topics**: Topics the user consistently avoids (0-3 topics)
4. **confidence**: Your confidence in this analysis (0.0-1.0)

## Guidelines:
- Focus on SPECIFIC technical terms (e.g., "vision-language models", "diffusion-based generation")
- Avoid broad categories like "machine learning" or "deep learning"
- Consider the matched keywords from liked papers as strong signals
- If disliked papers share common topics, add them to disliked_topics

Respond with valid JSON only."""


# ===== Query Generation Agent Prompt =====
QUERY_GENERATION_PROMPT = """You are a research query optimizer. Generate an optimized arXiv search strategy based on user interests.

## User's Main Interests:
{main_interests}

## Emerging Interests:
{emerging_interests}

## Topics to Avoid:
{disliked_topics}

## Current Hot Topics in Retrieved Papers:
{current_hot_topics}

## Task:
Generate:
1. **query**: A synthetic arXiv query string that combines user interests
   - Use OR for alternatives within a topic
   - Use AND to combine different aspects
   - Example: "(transformer OR attention) AND (vision OR multimodal)"

2. **high_priority_keywords**: Keywords that should receive high weight (3.0)
   - Most aligned with main interests
   - 3-5 specific terms

3. **medium_priority_keywords**: Keywords for moderate weight (2.0)
   - Related to emerging interests or supporting topics
   - 3-5 terms

4. **negative_keywords**: Keywords to demote (weight -1.0)
   - Topics user dislikes or irrelevant areas
   - 0-3 terms

## Guidelines:
- Balance user interests with current research trends
- Be specific: prefer "CLIP" over "contrastive learning"
- Consider synonyms and variations
- The query should be valid arXiv search syntax

Respond with valid JSON only."""


# ===== Validation Agent Prompt =====
VALIDATION_PROMPT = """You are a recommendation quality validator. Review the paper ranking and ensure it aligns with user interests.

## Top Ranked Papers:
{papers}

## User's Known Interests:
{user_interests}

## Topics User Dislikes:
{disliked_topics}

## Task:
1. **Evaluate** if the ranking aligns with user interests (score 0.0-1.0)
2. **Identify** any papers that seem misranked (too high or too low)
3. **Generate** brief explanations for top 5 papers explaining why they're recommended
4. **Suggest** reordering if needed (list of paper_ids in new order)
5. **Confidence** score for your evaluation (0.0-1.0)

## Output Format:
{{
    "evaluation_score": 0.85,
    "confidence": 0.8,
    "misranked_papers": [
        {{"paper_id": "xxx", "issue": "too high/too low", "reason": "..."}}
    ],
    "explanations": [
        {{"paper_id": "xxx", "explanation": "Recommended because..."}}
    ],
    "suggested_reorder": ["paper_id_1", "paper_id_2", ...] or null
}}

## Guidelines:
- A paper is well-ranked if it matches main interests
- Papers matching disliked topics should be lower
- Consider the diversity of recommendations
- Explanations should be concise (1-2 sentences) and user-friendly

Respond with valid JSON only."""


# ===== Scoring Helper Prompt =====
SCORING_PROMPT = """You are a paper relevance scorer. Score how relevant each paper is to the user's interests.

## User Interests:
{interests}

## Paper to Score:
Title: {title}
Abstract: {abstract}
Matched Keywords: {matched_keywords}

## Task:
Rate the paper's relevance from 0.0 to 1.0 based on:
- How well it matches the user's main interests
- Whether it covers emerging interests (bonus)
- Whether it touches disliked topics (penalty)

Output a single float number between 0.0 and 1.0."""
