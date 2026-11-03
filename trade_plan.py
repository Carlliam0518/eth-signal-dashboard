from dataclasses import dataclass

from risk import calculate_position_size, floor_to_step

# Conservative display rounding (a multiple of 0.00001 is also a multiple of any
# finer lot size). The bot reads the exact lot size from OKX instead.
DISPLAY_LOT = 0.00001


@dataclass
class TradePlan:
    valid: bool
    entry: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_size_eth: float
    notional_usdt: float
    notes: str


def _invalid(entry_price: float, why: str) -> TradePlan:
    return TradePlan(False, entry_price, 0.0, 0.0, 0.0, 0.0, 0.0, why)


def build_long_plan(
    entry_price: float,
    account_equity: float,
    risk_per_trade: float,
    stop_loss_pct: float,
    take_profit_rr: float,
    max_notional: float | None = None,
) -> TradePlan:
    if entry_price <= 0 or account_equity <= 0:
        return _invalid(entry_price, "Price and trading capital must be positive.")
    if not 0 < stop_loss_pct < 1 or risk_per_trade <= 0 or take_profit_rr <= 0:
        return _invalid(entry_price, "Stop distance, risk % and reward:risk must be positive.")

    stop_loss = entry_price * (1 - stop_loss_pct)
    take_profit = entry_price + (entry_price - stop_loss) * take_profit_rr

    # One sizing function for the whole project (risk.py), so it is tested once.
    uncapped = calculate_position_size(account_equity, entry_price, stop_loss, risk_per_trade)
    size = calculate_position_size(
        account_equity, entry_price, stop_loss, risk_per_trade, max_notional=max_notional
    )
    size = floor_to_step(size, DISPLAY_LOT)
    if size <= 0:
        return _invalid(entry_price, "Position size rounds to zero. Increase capital or risk %.")

    notional = size * entry_price
    risk_amount = size * (entry_price - stop_loss)  # what you actually lose at the stop

    notes = []
    if max_notional is not None and uncapped * entry_price > max_notional + 1e-9:
        notes.append(
            f"Position capped at ${max_notional:,.2f} (keeps room for fees; no leverage), "
            "so your real risk is below your target."
        )

    return TradePlan(
        valid=True,
        entry=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_amount=risk_amount,
        position_size_eth=size,
        notional_usdt=notional,
        notes=" ".join(notes) or "Plan is within your configured risk limits.",
    )
