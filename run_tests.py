#!/usr/bin/env python3
"""
Run all tests for arXiv Paper Bot.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py -v           # Verbose output
    # If pytest is installed, this script will run pytest; otherwise it falls back to unittest discovery.
"""

import sys
import unittest


def run_tests(verbose=False, pattern="test_*.py"):
    """
    Run all tests.

    Args:
        verbose: If True, show verbose output
        pattern: Test file pattern (default: test_*.py)
    """
    # Prefer pytest when available (this repo contains pytest-style tests too).
    try:
        import pytest  # type: ignore
    except Exception:
        pytest = None

    if pytest is not None:
        args = ["tests"]
        args.append("-vv" if verbose else "-q")
        return int(pytest.main(args))

    # Fallback: unittest discovery only.
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern=pattern)
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    exit_code = run_tests(verbose=verbose)
    sys.exit(exit_code)
