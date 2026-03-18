"""
Mathematical and statistical helper functions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling z-score of a series."""
    mean = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (series - mean) / std.replace(0, np.nan)


def correlation_matrix(price_dict: dict[str, pd.Series],
                       window: int = 60) -> pd.DataFrame:
    """Compute rolling correlation matrix between multiple pairs."""
    returns = pd.DataFrame({k: v.pct_change() for k, v in price_dict.items()})
    return returns.tail(window).corr()


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0,
                 periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio."""
    excess = returns - risk_free_rate / periods_per_year
    if excess.std() == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std())


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0,
                  periods_per_year: int = 252) -> float:
    """Annualized Sortino ratio."""
    excess = returns - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / downside.std())


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown as a fraction."""
    peak = equity_curve.expanding().max()
    drawdown = (equity_curve - peak) / peak
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calmar ratio: annualized return / max drawdown."""
    equity = (1 + returns).cumprod()
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return 0.0
    annual_return = (1 + returns.mean()) ** periods_per_year - 1
    return float(annual_return / mdd)


def signal_confidence(indicators: dict[str, float],
                      weights: dict[str, float] | None = None) -> float:
    """
    Compute a weighted confidence score from indicator signals.
    Each indicator value should be in [-1, 1] range.
    Returns confidence in [0, 1].
    """
    if not indicators:
        return 0.0
    if weights is None:
        weights = {k: 1.0 / len(indicators) for k in indicators}
    total_weight = sum(weights.get(k, 0.0) for k in indicators)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(
        indicators[k] * weights.get(k, 0.0) for k in indicators
    )
    raw = weighted_sum / total_weight
    return float(np.clip((raw + 1) / 2, 0.0, 1.0))


def jarque_bera_test(returns: pd.Series) -> dict:
    """Test for normality of returns distribution."""
    jb_stat, p_value = stats.jarque_bera(returns.dropna())
    return {"statistic": float(jb_stat), "p_value": float(p_value),
            "is_normal": p_value > 0.05}


def hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
    """Estimate Hurst exponent (H < 0.5: mean-reverting, H > 0.5: trending)."""
    lags = range(2, max_lag)
    tau = []
    for lag in lags:
        diff = (series.iloc[lag:].values - series.iloc[:-lag].values)
        tau.append(np.sqrt(np.std(diff)))
    log_lags = np.log(list(lags))
    log_tau = np.log(tau)
    if len(log_lags) < 2:
        return 0.5
    slope, _, _, _, _ = stats.linregress(log_lags, log_tau)
    return float(slope)


def half_life_mean_reversion(series: pd.Series) -> float:
    """Half-life of mean reversion using OLS."""
    lagged = series.shift(1).dropna()
    delta = series.diff().dropna()
    aligned = pd.concat([delta, lagged], axis=1).dropna()
    if len(aligned) < 2:
        return float("inf")
    slope, _, _, _, _ = stats.linregress(aligned.iloc[:, 1], aligned.iloc[:, 0])
    if slope >= 0:
        return float("inf")
    return float(-np.log(2) / slope)
