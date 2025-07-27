# arXiv Paper Bot - Your Personal AI Paper Assistant

A personalized and self-learning AI assistant for arXiv papers. It not only automates your research paper feed but also continuously learns and adapts to your academic preferences based on daily feedback, enabling truly personalized content recommendations.

Say goodbye to manually browsing arXiv or filtering by keywords — let the knowledge that understands you the most come to you proactively.

## ✨ Core Features

- **🎯 Accurate Retrieval**: Customize one or more arXiv categories (e.g., `cs.CV`, `stat.ML`) to fetch the latest papers daily on a scheduled basis.

- **🧠 Dual-Mode Intelligent Filtering**:
  - **Static Mode**: Quickly filters papers based on your predefined keyword list.
  - **Dynamic Mode**: Activates the **Self-Learning Preference Model**, ranking papers based on semantic relevance — the more you use it, the better it understands you.

- **🤖 AI-Powered Summarization**: Uses large language models (LLMs, e.g., OpenAI GPT) to distill long abstracts into structured short summaries like “one-sentence highlight” and “core method,” helping you grasp the essence in seconds.

- **💡 Self-Learning Preference Model**:
  - Learns your true interests based on '**👍 Like**' / '**👎 Dislike**' feedback on pushed messages.
  - Automatically adjusts recommendation weights for better precision, and surfaces “dark horse” papers you might otherwise miss.

- **🚀 Multi-Platform Push**: Seamlessly delivers content to your favorite platforms. Currently supported:
  - **Feishu Group Bot** (Webhook with interactive cards)
  - **Telegram Bot** (with interactive buttons)
  - **WeChat Work Bot** (Webhook)
  - **Local Markdown/JSON files**, for archiving and further processing

- **⚙️ Highly Configurable**: All features are managed via a single `config.yaml` file, including fetch rules, filter modes, LLM API keys, and push channel switches — no need to touch the codebase.

## 🔁 Workflow (with Feedback Loop)

The core workflow is an intelligent pipeline with a **closed feedback loop**:

**[Scheduled Trigger] → [① Fetch] → [② Filter & Rank] → [③ AI Summarize] → [④ Push] → [⑤ User Feedback 👍/👎] → [⑥ Update Preference Model] → (Affects Next-Day Step ②)**

1. **Fetch**: Scheduled task retrieves new papers published that day.
2. **Filter & Rank**:
   - **Static Mode**: Scores papers based only on keywords.
   - **Dynamic Mode**: Computes a personalized recommendation score using the **preference model**, combined with keyword scores.
3. **Summarize**: Generates concise AI-powered summaries for top-ranked papers.
4. **Push**: Sends summaries with `👍/👎` buttons to your configured platforms.
5. **Feedback**: User reactions help the system understand preferences.
6. **Learn**: System updates your **preference vector** in real time for future recommendations.

## 🛠️ Tech Stack

- **Language**: Python 3.8+
- **Core Libraries**:
  - Paper Retrieval: `arxiv`
  - AI Summarization: `openai`
  - Task Scheduling: `APScheduler`
- **Preference Model**:
  - Embedding: `sentence-transformers`
  - Vector Similarity: `scikit-learn`, `numpy`
  - Storage: Built-in `SQLite`
- **Utilities**:
  - Push Service: `requests`
  - Config Management: `PyYAML`

## 🚀 Quick Start
