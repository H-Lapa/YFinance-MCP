import pandas as pd

from finance_mcp.formatting import format_correlation_matrix, format_portfolio_metrics


class TestCurrencyMismatchNote:
    def test_correlation_matrix_notes_mismatched_currencies(self):
        matrix = pd.DataFrame({"AAPL": [1.0, 0.2], "REY.MI": [0.2, 1.0]}, index=["AAPL", "REY.MI"])
        result = {"matrix": matrix, "currencies": {"AAPL": "USD", "REY.MI": "EUR"}}

        output = format_correlation_matrix(result)

        assert "multiple currencies" in output
        assert "AAPL: USD" in output
        assert "REY.MI: EUR" in output

    def test_correlation_matrix_no_note_when_currencies_match(self):
        matrix = pd.DataFrame({"AAPL": [1.0, 0.5], "MSFT": [0.5, 1.0]}, index=["AAPL", "MSFT"])
        result = {"matrix": matrix, "currencies": {"AAPL": "USD", "MSFT": "USD"}}

        output = format_correlation_matrix(result)

        assert "multiple currencies" not in output

    def test_correlation_matrix_no_note_when_currencies_unknown(self):
        matrix = pd.DataFrame({"AAPL": [1.0, 0.5], "MSFT": [0.5, 1.0]}, index=["AAPL", "MSFT"])
        result = {"matrix": matrix, "currencies": {"AAPL": None, "MSFT": None}}

        output = format_correlation_matrix(result)

        assert "multiple currencies" not in output

    def test_portfolio_metrics_notes_mismatched_currencies(self):
        result = {
            "weights": {"AAPL": 0.5, "REY.MI": 0.5},
            "annualized_return": 0.12,
            "annualized_volatility": 0.20,
            "currencies": {"AAPL": "USD", "REY.MI": "EUR"},
        }

        output = format_portfolio_metrics(result)

        assert "multiple currencies" in output

    def test_portfolio_metrics_no_note_when_currencies_match(self):
        result = {
            "weights": {"AAPL": 0.5, "MSFT": 0.5},
            "annualized_return": 0.12,
            "annualized_volatility": 0.20,
            "currencies": {"AAPL": "USD", "MSFT": "USD"},
        }

        output = format_portfolio_metrics(result)

        assert "multiple currencies" not in output
