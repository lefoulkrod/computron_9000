"""Tests for select_option tool improvements (BTI-012)."""

import pytest

from tools.browser.select import _find_option_index


@pytest.mark.unit
class TestFindOptionIndex:
    """Option index finding with exact and fuzzy matching."""

    def test_exact_match(self):
        """Exact match returns correct index."""
        options = ["Apple", "Banana", "Cherry"]
        assert _find_option_index(options, "Banana") == 1

    def test_exact_match_first(self):
        """Exact match on first element."""
        options = ["Apple", "Banana", "Cherry"]
        assert _find_option_index(options, "Apple") == 0

    def test_exact_match_last(self):
        """Exact match on last element."""
        options = ["Apple", "Banana", "Cherry"]
        assert _find_option_index(options, "Cherry") == 2

    def test_case_insensitive_fallback(self):
        """Case-insensitive match when exact match fails."""
        options = ["Apple", "Banana", "Cherry"]
        assert _find_option_index(options, "banana") == 1

    def test_whitespace_normalized_fallback(self):
        """Whitespace-normalized match when exact match fails."""
        options = ["  Apple  ", " Banana ", "Cherry"]
        assert _find_option_index(options, "Banana") == 1

    def test_both_case_and_whitespace(self):
        """Case-insensitive + whitespace-normalized match."""
        options = ["  APPLE  ", " banana ", "Cherry"]
        assert _find_option_index(options, "Banana") == 1

    def test_not_found_raises_value_error(self):
        """ValueError raised when option not found."""
        options = ["Apple", "Banana", "Cherry"]
        with pytest.raises(ValueError, match="not found"):
            _find_option_index(options, "Durian")

    def test_empty_options_raises_value_error(self):
        """ValueError raised for empty options list."""
        with pytest.raises(ValueError, match="not found"):
            _find_option_index([], "Apple")

    def test_duplicate_options_returns_first(self):
        """First occurrence returned for duplicate options."""
        options = ["Apple", "Apple", "Banana"]
        assert _find_option_index(options, "Apple") == 0

    def test_numeric_options(self):
        """Numeric option values work correctly."""
        options = ["1", "2", "3", "4", "5"]
        assert _find_option_index(options, "3") == 2

    def test_month_dropdown(self):
        """Real-world month dropdown matching."""
        months = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
        assert _find_option_index(months, "March") == 2
        assert _find_option_index(months, "march") == 2