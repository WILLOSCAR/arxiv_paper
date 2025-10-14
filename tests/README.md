# arXiv Paper Bot - Tests

This directory contains unit tests for all major components of the arXiv Paper Bot.

## 🧪 Running Tests

### Run all tests:
```bash
python run_tests.py
```

### Run with verbose output:
```bash
python run_tests.py -v
```

### Run specific test file:
```bash
python -m unittest tests.test_filter
```

### Run specific test class:
```bash
python -m unittest tests.test_filter.TestPaperFilter
```

### Run specific test method:
```bash
python -m unittest tests.test_filter.TestPaperFilter.test_keyword_matching
```

## 📁 Test Structure

```
tests/
├── __init__.py
├── test_models.py      # Tests for data models (Paper, Config classes)
├── test_filter.py      # Tests for keyword filtering and ranking
├── test_storage.py     # Tests for JSON/CSV storage
├── test_notifier.py    # Tests for notification push logic
└── fixtures/           # Test data (if needed)
```

## 🎯 Test Coverage

### `test_models.py`
- Paper model creation and conversion
- Configuration model defaults
- Dictionary and CSV row conversion
- Data validation

### `test_filter.py`
- Keyword matching in titles and abstracts
- Multi-priority keyword weighting
- Score calculation and ranking
- Min score threshold filtering
- Top-k limiting
- Statistics generation

### `test_storage.py`
- JSON file saving and loading
- CSV file saving and loading
- Append mode functionality
- Duplicate removal
- File creation in non-existent directories

### `test_notifier.py`
- Message formatting utility
- Builder validation for各渠道配置
- 飞书/Telegram/微信公众号推送调用（通过 `requests` mock）

## ✅ Expected Results

All tests should pass:
```
Ran X tests in Y.YYYs

OK
```

If any tests fail, check:
1. Dependencies are installed (`pip install -r requirements.txt`)
2. Python version is 3.8+ (`python --version`)
3. Working directory is project root

## 🔍 Writing New Tests

When adding new features, add corresponding tests:

1. Create test class inheriting from `unittest.TestCase`
2. Add `setUp()` method for test data
3. Write test methods starting with `test_`
4. Use descriptive test names
5. Add assertions to verify behavior

Example:
```python
class TestNewFeature(unittest.TestCase):
    def setUp(self):
        self.data = create_test_data()

    def test_feature_works(self):
        result = my_function(self.data)
        self.assertEqual(result, expected_value)
```

## 📊 Test Guidelines

- **Keep tests independent**: Each test should run standalone
- **Use temporary files**: Clean up after tests (see `test_storage.py`)
- **Test edge cases**: Empty input, None values, large datasets
- **Assert clearly**: Use specific assertions (`assertEqual`, `assertIn`, etc.)
- **Document tests**: Add docstrings explaining what is tested
