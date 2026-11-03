import base64
import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlencode

import certifi
import pandas as pd
import requests
import urllib3

from config import (
    ALLOW_INSECURE_PUBLIC,
    API_KEY,
    BASE_URL,
    FLAG,
    INSTRUMENT,
    PASSPHRASE,
    PUBLIC_FALLBACK_URLS,
    SECRET_KEY,
    TIMEFRAME,
)

if ALLOW_INSECURE_PUBLIC:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OKXError(RuntimeError):
    """OKX answered but rejected the request (bad key, wrong demo/live flag, ...)."""


class OKXNetworkError(RuntimeError):
    """Could not reach OKX at all (ISP block, DNS, timeout, ...)."""


def _public_domains() -> list[str]:
    seen: list[str] = []
    for url in [BASE_URL, *PUBLIC_FALLBACK_URLS]:
        if url not in seen:
            seen.append(url)
    return seen


def _signed_headers(request_path: str) -> dict:
    # Built fresh for EVERY attempt: OKX rejects timestamps more than ~30 s old.
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    message = f"{timestamp}GET{request_path}"
    signature = base64.b64encode(
        hmac.new(SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "x-simulated-trading": FLAG,
    }


def _okx_get(path: str, params: dict | None = None, signed: bool = False) -> dict:
    """GET from OKX.

    - Public data: tries each domain with verified TLS (and, only if you opted in with
      ALLOW_INSECURE_PUBLIC=true, an unverified retry).
    - Signed data: ONE domain (BASE_URL), verified TLS only. Your key and passphrase are
      never sent over a connection whose certificate was not checked.
    """
    request_path = path + (f"?{urlencode(params)}" if params else "")
    domains = [BASE_URL] if signed else _public_domains()
    verify_modes: list = [certifi.where()]
    if ALLOW_INSECURE_PUBLIC and not signed:
        verify_modes.append(False)

    last_err: Exception | None = None
    for domain in domains:
        for verify in verify_modes:
            headers = _signed_headers(request_path) if signed else None
            try:
                resp = requests.get(
                    f"{domain}{request_path}", headers=headers, timeout=8, verify=verify
                )
                payload = resp.json()
            except (requests.exceptions.RequestException, ValueError) as exc:
                last_err = exc  # network / non-JSON (ISP block page): try the next option
                continue

            if payload.get("code") == "0":
                return payload
            # OKX itself said no. That is not a network problem, so say what it said.
            raise OKXError(f"OKX error {payload.get('code')}: {payload.get('msg')}")

    raise OKXNetworkError(
        f"Could not reach OKX ({last_err}). Your ISP may be blocking it. "
        "Try Cloudflare WARP / a VPN or set DNS to 1.1.1.1."
    )


def get_candles(limit: int = 300) -> pd.DataFrame:
    """Closed candles only, oldest first."""
    payload = _okx_get(
        "/api/v5/market/candles",
        params={"instId": INSTRUMENT, "bar": TIMEFRAME, "limit": str(limit)},
    )
    columns = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"]
    df = pd.DataFrame(payload["data"], columns=columns)
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    for col in ["open", "high", "low", "close", "vol"]:
        df[col] = pd.to_numeric(df[col])
    df = df[df["confirm"].astype(str) == "1"]
    return df.sort_values("ts").reset_index(drop=True)


def get_live_price() -> float:
    payload = _okx_get("/api/v5/market/ticker", params={"instId": INSTRUMENT})
    return float(payload["data"][0]["last"])


def get_usdt_balance() -> tuple[float | None, str | None]:
    """Returns (balance, error). (None, None) means no keys configured.

    Uses READ-ONLY keys. The error is returned, not swallowed, so a bad key or a
    demo/live mismatch shows up in the sidebar instead of silently looking like
    "no keys".
    """
    if not (API_KEY and SECRET_KEY and PASSPHRASE):
        return None, None
    try:
        payload = _okx_get("/api/v5/account/balance", params={"ccy": "USDT"}, signed=True)
    except (OKXError, OKXNetworkError) as exc:
        return None, str(exc)

    for account in payload.get("data", []):
        for item in account.get("details", []):
            if item.get("ccy") == "USDT":
                return float(item.get("availBal") or 0.0), None
    return 0.0, None
