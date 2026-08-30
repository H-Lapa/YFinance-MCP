import math
import statistics

import pandas as pd
import pytest

from finance_mcp import risk


class TestDailyReturns:
    def test_simple_returns(self):
        prices = pd.Series([100.0, 110.0, 121.0])

        returns = risk.daily_returns(prices)

        assert returns.tolist() == pytest.approx([0.10, 0.10])

    def test_drops_leading_nan(self):
        prices = pd.Series([100.0, 105.0])

        returns = risk.daily_returns(prices)

        assert len(returns) == 1


class TestVolatility:
    def test_annualizes_sample_std_independently_verified(self):
        # Cross-checked against Python's stdlib `statistics.stdev` (also ddof=1)
        # rather than re-deriving the same pandas call, so this actually
        # validates the convention (sample std, sqrt(252) scaling).
        returns = pd.Series([0.01, -0.02, 0.015, 0.005, -0.01])

        result = risk.volatility(returns)

        expected = statistics.stdev(returns) * math.sqrt(252)
        assert result == pytest.approx(expected)

    def test_custom_trading_days(self):
        returns = pd.Series([0.01, -0.01, 0.02, -0.02])

        result = risk.volatility(returns, trading_days=12)

        expected = statistics.stdev(returns) * math.sqrt(12)
        assert result == pytest.approx(expected)


class TestMaxDrawdown:
    def test_hand_computed_drawdown(self):
        # cummax: 100,120,120,120,120,130 -> trough at 80 vs cummax 120 = -1/3
        prices = pd.Series([100.0, 120.0, 90.0, 110.0, 80.0, 130.0])

        result = risk.max_drawdown(prices)

        assert result == pytest.approx(-1 / 3)

    def test_monotonically_increasing_series_has_zero_drawdown(self):
        prices = pd.Series([100.0, 110.0, 120.0, 130.0])

        result = risk.max_drawdown(prices)

        assert result == pytest.approx(0.0)


class TestSharpeRatio:
    def test_matches_hand_computed_formula(self):
        returns = pd.Series([0.01, -0.01, 0.02, -0.02])
        annual_rf = 0.05
        trading_days = 252

        result = risk.sharpe_ratio(returns, annual_rf, trading_days=trading_days)

        daily_rf = annual_rf / trading_days
        expected = (
            (statistics.mean(returns) - daily_rf)
            / statistics.stdev(returns)
            * math.sqrt(trading_days)
        )
        assert result == pytest.approx(expected)

    def test_zero_risk_free_rate_reduces_to_mean_over_std(self):
        returns = pd.Series([0.01, 0.02, -0.005, 0.015])

        result = risk.sharpe_ratio(returns, 0.0)

        expected = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252)
        assert result == pytest.approx(expected)


class TestHistoricalVar:
    def test_at_exact_quantile_point(self):
        # 21 evenly-spaced values, chosen so the 5th percentile lands exactly on
        # a data point (index 1) rather than needing interpolation to verify by hand.
        returns = pd.Series([-0.10 + 0.01 * i for i in range(21)])

        result = risk.historical_var(returns, confidence=0.95)

        assert result == pytest.approx(-0.09)

    def test_different_confidence_level(self):
        returns = pd.Series([-0.10 + 0.01 * i for i in range(21)])

        result = risk.historical_var(returns, confidence=0.90)

        assert result == pytest.approx(-0.08)


class TestBeta:
    def test_hand_computed_beta(self):
        dates = pd.date_range("2024-01-01", periods=4)
        benchmark_returns = pd.Series([0.01, 0.02, -0.01, 0.03], index=dates)
        asset_returns = benchmark_returns * 1.5  # exactly 1.5x -> beta must be exactly 1.5

        result = risk.beta(asset_returns, benchmark_returns)

        assert result == pytest.approx(1.5)

    def test_non_overlapping_dates_are_excluded_not_corrupting(self):
        dates = pd.date_range("2024-01-01", periods=4)
        benchmark_returns = pd.Series([0.01, 0.02, -0.01, 0.03], index=dates)
        asset_returns = benchmark_returns * 1.5

        # Extra dates present in only one series -- an outlier value that would
        # change the result if the alignment were wrong (e.g. positional zip
        # instead of an index-based inner join).
        asset_with_outlier = pd.concat(
            [asset_returns, pd.Series([999.0], index=[pd.Timestamp("2024-02-01")])]
        )
        benchmark_with_outlier = pd.concat(
            [benchmark_returns, pd.Series([-999.0], index=[pd.Timestamp("2024-03-01")])]
        )

        result = risk.beta(asset_with_outlier, benchmark_with_outlier)

        assert result == pytest.approx(1.5)


class TestCorrelationMatrix:
    def test_perfect_positive_and_negative_correlation(self):
        a = pd.Series([0.01, 0.02, 0.03, 0.04])
        b = a * 2
        c = -a

        result = risk.correlation_matrix({"A": a, "B": b, "C": c})

        assert result.loc["A", "B"] == pytest.approx(1.0)
        assert result.loc["A", "C"] == pytest.approx(-1.0)
        assert result.loc["A", "A"] == pytest.approx(1.0)


class TestPortfolioMetrics:
    def test_matches_direct_calculation_on_combined_series(self):
        dates = pd.date_range("2024-01-01", periods=4)
        a = pd.Series([0.01, 0.02, 0.03, 0.04], index=dates)
        b = pd.Series([0.02, 0.01, 0.04, 0.03], index=dates)

        result = risk.portfolio_metrics({"A": 0.5, "B": 0.5}, {"A": a, "B": b})

        # Independently verified: Var(0.5A + 0.5B) computed directly on the
        # combined series must equal the covariance-matrix quadratic form
        # (w . Sigma . w) the function actually uses -- a mathematical
        # identity, so any mismatch means the matrix math is implemented wrong.
        combined = 0.5 * a + 0.5 * b
        expected_return = statistics.mean(combined) * 252
        expected_vol = statistics.stdev(combined) * math.sqrt(252)

        assert result["annualized_return"] == pytest.approx(expected_return)
        assert result["annualized_volatility"] == pytest.approx(expected_vol)

    def test_weights_auto_normalize_dollars_vs_percentages(self):
        dates = pd.date_range("2024-01-01", periods=4)
        a = pd.Series([0.01, 0.02, 0.03, 0.04], index=dates)
        b = pd.Series([0.02, 0.01, 0.04, 0.03], index=dates)

        pct_result = risk.portfolio_metrics({"A": 0.5, "B": 0.5}, {"A": a, "B": b})
        dollar_result = risk.portfolio_metrics({"A": 5000, "B": 5000}, {"A": a, "B": b})

        assert dollar_result["annualized_return"] == pytest.approx(pct_result["annualized_return"])
        assert dollar_result["annualized_volatility"] == pytest.approx(
            pct_result["annualized_volatility"]
        )
        assert dollar_result["weights"] == pytest.approx(pct_result["weights"])
