from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import (
    ACCOUNT_EQUITY_USDT,
    ALLOW_INSECURE_PUBLIC,
    BAR_MINUTES,
    INSTRUMENT,
    MAX_POSITION_FRACTION,
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_RR,
    TIMEFRAME,
)
from data import get_candles, get_live_price, get_usdt_balance
from indicators import add_indicators
from strategy import generate_signal
from trade_plan import build_long_plan

st.set_page_config(
    page_title="ETH Rule-Based Signal Dashboard",
    page_icon="📈",
    layout="wide",
)

# --- Cached loaders -------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def load_candles():
    return add_indicators(get_candles(limit=300)), datetime.now(timezone.utc)

@st.cache_data(ttl=3, show_spinner=False)
def load_price():
    return get_live_price(), datetime.now(timezone.utc)

@st.cache_data(ttl=60, show_spinner=False)
def load_balance() -> tuple[float | None, str | None]:
    return get_usdt_balance()

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def last_cross(candles: pd.DataFrame, column: str) -> str:
    hits = candles.index[candles[column].to_numpy()]
    if len(hits) == 0:
        return "none in the loaded candles"
    i = hits[-1]
    ago = len(candles) - 1 - i
    when = candles.loc[i, "ts"].strftime("%Y-%m-%d %H:%M UTC")
    return f"{when} ({ago} candles ago)"

def seconds_ago(moment: datetime) -> int:
    return max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))

# --- Page header and sidebar ----------------------------------------------------------
st.title("ETH-USDT Rule-Based Signal Dashboard")
st.caption("Always verify prices, fees, and available balance in OKX before trading.")

if ALLOW_INSECURE_PUBLIC:
    st.warning(
        "ALLOW_INSECURE_PUBLIC is on: public market data may be fetched without "
        "certificate checks. Do not trade off these signals until you fix the connection."
    )

synced_balance, balance_error = load_balance()
default_equity = synced_balance if synced_balance is not None else ACCOUNT_EQUITY_USDT

with st.sidebar:
    st.header("Trade State Tracker")
    in_position = st.toggle("🟢 I am in an active trade")
    on_cooldown = st.toggle("⏸️ On cooldown (Stopped out)")
    
    st.header("Live updates")
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    refresh_seconds = st.selectbox(
        "Refresh every (seconds)", [5, 10, 15, 30, 60], index=2, disabled=not auto_refresh
    )

    st.header("Risk settings")
    if synced_balance is not None:
        st.success(f"Synced OKX Read-Only Balance: ${synced_balance:,.2f} USDT")
    elif balance_error:
        st.error(f"Balance sync failed: {balance_error}")
        st.caption("Using manual equity below.")
    else:
        st.caption("Using manual equity (configure Read-Only keys in .env to auto-sync).")

    account_equity = st.number_input(
        "Trading capital (USDT)",
        min_value=1.0,
        value=max(1.0, float(default_equity)),
        step=1.0,
    )

    risk_per_trade = st.slider(
        "Risk per trade (%)",
        min_value=0.25,
        max_value=2.0,
        value=clamp(RISK_PER_TRADE * 100, 0.25, 2.0),
        step=0.25,
    ) / 100

    stop_loss_pct = st.slider(
        "Stop-loss distance (%)",
        min_value=0.5,
        max_value=5.0,
        value=clamp(STOP_LOSS_PCT * 100, 0.5, 5.0),
        step=0.25,
    ) / 100

    take_profit_rr = st.slider(
        "Take-profit reward:risk",
        min_value=1.0,
        max_value=4.0,
        value=clamp(TAKE_PROFIT_RR, 1.0, 4.0),
        step=0.25,
    )

    preview_mode = st.checkbox(
        "Preview trade plan & checklist (even when signal is WAIT)",
        value=False,
    )

    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()

# --- The live part ----------------------------------------------------------------------
def render(account_equity, risk_per_trade, stop_loss_pct, take_profit_rr, preview_mode, in_position, on_cooldown):
    try:
        candles, candles_at = load_candles()
        live_price, price_at = load_price()
        signal = generate_signal(candles)
        latest = candles.iloc[-1]

        closed_at = latest["ts"].to_pydatetime() + timedelta(minutes=BAR_MINUTES)
        mins_since_close = (datetime.now(timezone.utc).replace(tzinfo=None) - closed_at).total_seconds() / 60

        st.caption(
            f"🟢 Price fetched {seconds_ago(price_at)}s ago ({price_at:%H:%M:%S} UTC) · "
            f"candles fetched {seconds_ago(candles_at)}s ago · "
            + (f"auto-refreshing every {refresh_seconds}s" if auto_refresh else "auto-refresh OFF")
            + f" · the signal only changes when a {TIMEFRAME} candle closes"
        )
        if mins_since_close > BAR_MINUTES + 3:
            st.error(
                f"Candle data looks STALE: the newest closed candle ended {mins_since_close:,.0f} minutes ago. Do not trade off this signal."
            )

        prev = st.session_state.get("prev_price")
        st.session_state["prev_price"] = live_price
        delta = None if prev is None else f"{live_price - prev:+,.2f} since last update"

        # State Override Logic
        display_action = signal.action
        display_reason = signal.reason

        if in_position:
            display_action = "MANAGING POSITION"
            if signal.action == "EXIT / DO NOT BUY":
                display_reason = "🚨 EXIT SIGNAL TRIGGERED: The 20 EMA crossed below the 50 EMA. Cancel your OCO and manually sell your position now."
            else:
                display_reason = "You are currently holding a position. Let your OCO order run, or wait for an EXIT signal."
        elif on_cooldown:
            display_action = "COOLDOWN ACTIVE"
            if signal.action == "EXIT / DO NOT BUY":
                display_reason = "Market cycle has reset (bearish crossover). You can turn Cooldown OFF now."
            else:
                display_reason = "You are on cooldown after a stop-out. Ignore new entries and wait for a bearish crossover to reset the market cycle."

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ETH-USDT", f"${live_price:,.2f}", delta=delta)
        col2.metric("Signal", display_action)
        col3.metric("Trend filter", "Bullish" if signal.trend_up else "Bearish / neutral")
        col4.metric("Last closed candle", latest["ts"].strftime("%Y-%m-%d %H:%M UTC"))

        st.subheader("Current market read")
        
        # Highlight urgent manual exits
        if in_position and signal.action == "EXIT / DO NOT BUY":
            st.error(display_reason)
        else:
            st.write(display_reason)

        st.subheader("Indicator status")
        status = {
            "20 EMA": f"${latest['ema_fast']:,.2f}",
            "50 EMA": f"${latest['ema_slow']:,.2f}",
            "200 EMA": f"${latest['ema_trend']:,.2f}",
            "20 EMA above 50 EMA": "Yes" if latest["fast_above_slow"] else "No",
            "Fresh bullish crossover": "Yes" if signal.bullish_crossover else "No",
            "Fresh bearish crossover": "Yes" if signal.bearish_crossover else "No",
            "Last bullish crossover": last_cross(candles, "bullish_crossover"),
            "Last bearish crossover": last_cross(candles, "bearish_crossover"),
        }

        st.table(pd.DataFrame(list(status.items()), columns=["Check", "Value"]).set_index("Check"))

        st.subheader("Next-trade plan")

        if (signal.action == "BUY SIGNAL" and not in_position and not on_cooldown) or preview_mode:
            if preview_mode and (in_position or on_cooldown or signal.action != "BUY SIGNAL"):
                st.warning("PREVIEW MODE ACTIVE: The numbers below show the trade plan format, but you are either in a trade, on cooldown, or missing a live signal.")

            plan = build_long_plan(
                entry_price=live_price,
                account_equity=account_equity,
                risk_per_trade=risk_per_trade,
                stop_loss_pct=stop_loss_pct,
                take_profit_rr=take_profit_rr,
                max_notional=account_equity * MAX_POSITION_FRACTION,
            )

            if not plan.valid:
                st.error(plan.notes)
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Suggested entry", f"${plan.entry:,.2f}")
                c2.metric("Stop-loss", f"${plan.stop_loss:,.2f}")
                c3.metric("Take-profit", f"${plan.take_profit:,.2f}")
                c4.metric("Risk amount", f"${plan.risk_amount:,.2f}")

                c5, c6 = st.columns(2)
                c5.metric("ETH quantity", f"{plan.position_size_eth:.5f}")
                c6.metric("Position value", f"${plan.notional_usdt:,.2f}")

                st.info(plan.notes)

                st.subheader("Step-by-step OKX process")
                st.markdown(
                    f"""
1. Open OKX and go to **Trade → Spot**.
2. Search for **ETH/USDT**.
3. Confirm your available USDT balance is at least **${plan.notional_usdt:,.2f}** plus a buffer for fees.
4. Choose a **Limit** order if you want price control, or **Market** only if immediate entry matters more than exact price.
5. Enter **Buy ETH**.
6. Enter quantity: **{plan.position_size_eth:.5f} ETH**.
7. Review the estimated cost: approximately **${plan.notional_usdt:,.2f}**.
8. Submit the buy order.
9. After it fills, toggle **"🟢 I am in an active trade"** ON in your dashboard sidebar.
10. Place **one** protective sell using OKX's **OCO (take-profit / stop-loss)** order type: take-profit at **${plan.take_profit:,.2f}** and stop-loss trigger at **${plan.stop_loss:,.2f}**.
11. Exit via the OCO, or manually if the dashboard flashes a red EXIT alert.
                    """
                )

        elif in_position:
            st.info("Execution plan hidden while actively managing a position. Wait for an OCO fill or an EXIT signal.")
        elif on_cooldown:
            st.warning("Execution plan hidden while on cooldown. Wait for the market to reset.")
        elif signal.action == "EXIT / DO NOT BUY":
            st.error("The strategy says do not open a new long.")
        else:
            st.warning("No new entry is suggested right now. Wait for the next confirmed 1-hour candle.")

        st.subheader(f"{INSTRUMENT} — {TIMEFRAME} candles")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=candles["ts"], open=candles["open"], high=candles["high"], low=candles["low"], close=candles["close"], name="ETH-USDT"))
        fig.add_trace(go.Scatter(x=candles["ts"], y=candles["ema_fast"], name="20 EMA", line=dict(width=1.5)))
        fig.add_trace(go.Scatter(x=candles["ts"], y=candles["ema_slow"], name="50 EMA", line=dict(width=1.5)))
        fig.add_trace(go.Scatter(x=candles["ts"], y=candles["ema_trend"], name="200 EMA", line=dict(width=2)))
        fig.update_layout(height=600, xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.05))

        st.plotly_chart(fig, width="stretch")

    except Exception as exc:
        st.error(f"Could not update dashboard: {exc}")

run_every = f"{refresh_seconds}s" if auto_refresh else None
st.fragment(run_every=run_every)(render)(
    account_equity, risk_per_trade, stop_loss_pct, take_profit_rr, preview_mode, in_position, on_cooldown
)