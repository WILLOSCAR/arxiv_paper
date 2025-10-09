# Examples

This directory contains example scripts demonstrating how to use arXiv Paper Bot.

## 📚 Available Examples

### 1. Quick Start (`quick_start.py`)
Basic usage: fetch papers by category and filter by keywords.

```bash
python examples/quick_start.py
```

**What it does:**
- Fetches papers from cs.AI category
- Filters by keywords (LLM, transformer, etc.)
- Displays top 5 papers
- Saves results to JSON and CSV

---

### 2. Combined Search (`combined_search.py`)
**⭐ Recommended** - Most efficient way to search.

```bash
python examples/combined_search.py
```

**What it does:**
- Searches cs.CV and cs.AI categories
- Filters by keywords at the API level (efficient!)
- Uses `fetch_mode="combined"`

**Why use this:**
- Reduces unnecessary API calls
- Gets exactly what you want
- Faster than category-then-filter approach

---

### 3. Keyword-Only Search (`keyword_search.py`)
Search across all categories by keywords.

```bash
python examples/keyword_search.py
```

**What it does:**
- Searches for vision-language models
- Ignores category restrictions
- Groups results by category

**Use cases:**
- Topic-focused research
- Cross-disciplinary searches
- Finding related work across fields

---

## 🎯 Which Example Should I Use?

| Scenario | Recommended Example |
|----------|-------------------|
| I know the exact category and keywords | `combined_search.py` ⭐ |
| I want all papers from a category | `quick_start.py` |
| I'm researching a specific topic | `keyword_search.py` |
| I'm new to the tool | `quick_start.py` |

## 🔧 Customizing Examples

All examples can be easily modified:

1. **Change categories**: Edit the `categories` list
2. **Change keywords**: Edit the `search_keywords` list
3. **Change date range**: Modify `days` parameter
4. **Change output path**: Update `json_path` and `csv_path`

## 💡 Tips

- **Start simple**: Run `quick_start.py` first
- **Use combined mode**: For best performance, use `combined_search.py` approach
- **Check the output**: Look at `data/` directory for saved files
- **Adjust limits**: Modify `max_results` for more/fewer papers
