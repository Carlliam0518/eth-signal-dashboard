from decimal import Decimal


def floor_to_step(value, step) -> float:
    """Round DOWN to a multiple of step (lot size / tick size)."""
    v, s = Decimal(str(value)), Decimal(str(step))
    return float((v // s) * s)


def calculate_position_size(equity, entry_price, stop_price, risk_per_trade, max_notional=None):
    """Units to buy so that hitting the stop loses `risk_per_trade` of equity.

    max_notional (in quote currency) caps the position so we never try to spend
    more USDT than we have.
    """
    if equity <= 0 or entry_price <= 0:
        raise ValueError("Equity and entry price must be positive")

    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        raise ValueError("Stop-loss must differ from entry price")

    size = (equity * risk_per_trade) / risk_per_unit
    if max_notional is not None:
        size = min(size, max_notional / entry_price)
    return size


def daily_loss_exceeded(start_equity, current_equity, limit):
    if start_equity <= 0:
        return False
    loss = (start_equity - current_equity) / start_equity
    return loss >= limit
