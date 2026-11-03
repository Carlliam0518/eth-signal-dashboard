from dataclasses import dataclass
import pandas as pd


@dataclass
class Signal:
    action: str
    reason: str
    trend_up: bool
    bullish_crossover: bool
    bearish_crossover: bool


def generate_signal(df: pd.DataFrame) -> Signal:
    if len(df) < 3:
        return Signal("WAIT", "Not enough historical candles.", False, False, False)

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    trend_up = bool(latest["close"] > latest["ema_trend"])
    bullish = bool(
        previous["ema_fast"] <= previous["ema_slow"]
        and latest["ema_fast"] > latest["ema_slow"]
    )
    bearish = bool(
        previous["ema_fast"] >= previous["ema_slow"]
        and latest["ema_fast"] < latest["ema_slow"]
    )

    if bullish and trend_up:
        return Signal(
            "BUY SIGNAL",
            "20 EMA crossed above 50 EMA and price closed above 200 EMA.",
            trend_up,
            bullish,
            bearish,
        )

    if bearish:
        return Signal(
            "EXIT / DO NOT BUY",
            "20 EMA crossed below 50 EMA.",
            trend_up,
            bullish,
            bearish,
        )

    if trend_up:
        return Signal(
            "WAIT",
            "Uptrend filter is active (price > 200 EMA), but no fresh 20/50 EMA crossover on the last closed candle.",
            trend_up,
            bullish,
            bearish,
        )

    return Signal(
        "WAIT",
        "Price is below the 200 EMA; trend filter does not permit a long entry.",
        trend_up,
        bullish,
        bearish,
    )