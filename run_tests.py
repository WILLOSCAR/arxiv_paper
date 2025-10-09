#!/usr/bin/env python3
"""
Run all tests for arXiv Paper Bot.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py -v           # Verbose output
    python run_tests.py TestFilter   # Run specific test class
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
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = "tests"
    suite = loader.discover(start_dir, pattern=pattern)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    exit_code = run_tests(verbose=verbose)
    sys.exit(exit_code)
