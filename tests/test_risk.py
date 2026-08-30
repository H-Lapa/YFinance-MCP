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
