from types import SimpleNamespace

import pandas as pd
import pytest

from finance_mcp import market_data
from finance_mcp.market_data import MarketDataError


def _fast_info(**overrides):
    defaults = {
        "last_price": 150.0,
        "previous_close": 148.0,
        "last_volume": 1_000_000,
        "market_cap": 2_500_000_000_000,
        "year_high": 180.0,
        "year_low": 120.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _history_df(n_rows: int) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_rows, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n_rows)],
            "High": [101.0 + i for i in range(n_rows)],
            "Low": [99.0 + i for i in range(n_rows)],
            "Close": [100.5 + i for i in range(n_rows)],
            "Volume": [1000 + i for i in range(n_rows)],
        },
        index=dates,
    )


class TestFetchQuotes:
    def test_happy_path(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.fast_info = _fast_info()

        [row] = market_data.fetch_quotes(["aapl"])

        assert row["ticker"] == "AAPL"
        assert row["price"] == 150.0
        assert row["change"] == 2.0
        assert row["error"] == ""

    def test_unknown_ticker_embeds_error_without_raising(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.fast_info = _fast_info(last_price=None)

        [row] = market_data.fetch_quotes(["BOGUS"])

        assert row["ticker"] == "BOGUS"
        assert row["price"] is None
        assert "no data found" in row["error"]

    def test_lookup_exception_embeds_error_without_raising(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.side_effect = RuntimeError("network down")

        [row] = market_data.fetch_quotes(["AAPL"])

        assert "no data found" in row["error"]

    def test_partial_batch_failure_does_not_drop_good_rows(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.fast_info = _fast_info()

        rows = market_data.fetch_quotes(["AAPL", ""])

        assert rows[0]["error"] == ""
        assert rows[1]["error"] == "empty ticker"


class TestFetchHistory:
    def test_happy_path_no_resample(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.history.return_value = _history_df(10)

        result = market_data.fetch_history("aapl", period="1mo", interval="1d")

        assert result["ticker"] == "AAPL"
        assert result["note"] is None
        assert len(result["rows"]) == 10
        assert result["rows"][0]["date"] == "2024-01-01"

    def test_long_history_gets_downsampled(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.history.return_value = _history_df(500)

        result = market_data.fetch_history("aapl", period="5y", interval="1d")

        assert result["note"] is not None
        assert len(result["rows"]) <= market_data.MAX_HISTORY_ROWS

    def test_empty_history_raises(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.history.return_value = pd.DataFrame()

        with pytest.raises(MarketDataError):
            market_data.fetch_history("BOGUS")

    def test_blank_ticker_raises(self):
        with pytest.raises(MarketDataError):
            market_data.fetch_history("   ")


class TestFetchCompanyInfo:
    def test_happy_path(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 2_500_000_000_000,
            "trailingPE": 30.0,
            "dividendYield": 0.005,
            "beta": 1.2,
            "longBusinessSummary": "Apple designs, manufactures, and markets smartphones.",
        }

        info = market_data.fetch_company_info("aapl")

        assert info["name"] == "Apple Inc."
        assert info["sector"] == "Technology"

    def test_unknown_ticker_raises(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.info = {}

        with pytest.raises(MarketDataError):
            market_data.fetch_company_info("BOGUS")

    def test_long_summary_is_truncated(self, mocker):
        mock_ticker = mocker.patch("finance_mcp.market_data.yf.Ticker")
        mock_ticker.return_value.info = {
            "longName": "Apple Inc.",
            "longBusinessSummary": "word " * 300,
        }

        info = market_data.fetch_company_info("aapl")

        assert len(info["summary"]) <= 804
        assert info["summary"].endswith("...")


class TestSearchTickers:
    def test_happy_path(self, mocker):
        mock_search = mocker.patch("finance_mcp.market_data.yf.Search")
        mock_search.return_value.quotes = [
            {"symbol": "AAPL", "shortname": "Apple Inc.", "exchange": "NMS", "quoteType": "EQUITY"}
        ]

        [match] = market_data.search_tickers("apple")

        assert match["ticker"] == "AAPL"
        assert match["name"] == "Apple Inc."

    def test_no_matches_raises(self, mocker):
        mock_search = mocker.patch("finance_mcp.market_data.yf.Search")
        mock_search.return_value.quotes = []

        with pytest.raises(MarketDataError):
            market_data.search_tickers("zzzzzznotarealcompany")

    def test_blank_query_raises(self):
        with pytest.raises(MarketDataError):
            market_data.search_tickers("   ")
