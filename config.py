import os

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    """Read a float from .env; fall back to the default if blank or invalid."""
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return float(default)


INSTRUMENT = "ETH-USDT"
TIMEFRAME = "1H"
BAR_MINUTES = 60  # must match TIMEFRAME; used to detect stale candle data
FAST_EMA = 20
SLOW_EMA = 50
TREND_EMA = 200

# Signed (API-key) requests are sent ONLY to this domain.
BASE_URL = os.getenv("OKX_BASE_URL", "https://aws.okx.com").strip().rstrip("/")
# Public market-data requests may fail over between these (all verified TLS).
PUBLIC_FALLBACK_URLS = ["https://www.okx.com", "https://aws.okx.com"]

API_KEY = os.getenv("OKX_API_KEY", "").strip()
SECRET_KEY = os.getenv("OKX_SECRET_KEY", "").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()
FLAG = os.getenv("OKX_FLAG", "1").strip()  # 1 = demo (safe default), 0 = live

# Off by default. Even when on, it applies to PUBLIC data only, never to signed calls.
ALLOW_INSECURE_PUBLIC = os.getenv("ALLOW_INSECURE_PUBLIC", "false").strip().lower() == "true"

ACCOUNT_EQUITY_USDT = _float_env("ACCOUNT_EQUITY_USDT", 100)
RISK_PER_TRADE = _float_env("RISK_PER_TRADE", 0.01)
STOP_LOSS_PCT = _float_env("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_RR = _float_env("TAKE_PROFIT_RR", 2.0)
MAX_POSITION_FRACTION = _float_env("MAX_POSITION_FRACTION", 0.95)
