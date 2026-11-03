import pandas as pd
from config import FAST_EMA, SLOW_EMA, TREND_EMA


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = ema(df["close"], FAST_EMA)
    df["ema_slow"] = ema(df["close"], SLOW_EMA)
    df["ema_trend"] = ema(df["close"], TREND_EMA)

    df["fast_above_slow"] = df["ema_fast"] > df["ema_slow"]
    previous = df["fast_above_slow"].shift(1, fill_value=False)

    df["bullish_crossover"] = df["fast_above_slow"] & ~previous
    df["bearish_crossover"] = ~df["fast_above_slow"] & previous

    return df