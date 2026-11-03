"""Offline tests for the dashboard logic. Run: python tests/test_dashboard.py"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

import data
from data import OKXError, OKXNetworkError
from indicators import add_indicators
from strategy import generate_signal
from trade_plan import build_long_plan


class FakeResp:
    def __init__(self, payload=None, bad_json=False):
        self._payload, self._bad = payload, bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._payload


def test_plan_matches_readme_example():
    plan = build_long_plan(3000, 100, 0.01, 0.02, 2.0, max_notional=95)
    assert plan.valid
    assert abs(plan.stop_loss - 2940) < 1e-9 and abs(plan.take_profit - 3120) < 1e-9
    assert abs(plan.notional_usdt - 50) < 0.05          # ~$50 (floored to lot size)
    assert plan.risk_amount <= 1.0 + 1e-9               # never risks MORE than 1%


def test_plan_cap_reports_real_risk():
    plan = build_long_plan(3000, 100, 0.01, 0.005, 2.0, max_notional=95)  # 0.5% stop wants $200
    assert plan.notional_usdt <= 95 + 1e-9
    assert plan.risk_amount < 1.0 and "capped" in plan.notes


def test_plan_rejects_bad_inputs():
    assert not build_long_plan(3000, 100, 0.01, 0.0, 2.0).valid     # used to divide by zero
    assert not build_long_plan(0, 100, 0.01, 0.02, 2.0).valid
    assert not build_long_plan(3000, 0.01, 0.01, 0.02, 2.0).valid   # rounds to zero ETH


def test_signed_request_never_uses_insecure_mode_or_other_domains():
    calls = []

    def fake_get(url, headers=None, timeout=None, verify=None):
        calls.append((url, verify, headers))
        raise requests.exceptions.SSLError("intercepted")

    with mock.patch.object(data, "API_KEY", "k"), mock.patch.object(data, "SECRET_KEY", "s"), \
         mock.patch.object(data, "PASSPHRASE", "p"), mock.patch.object(data.requests, "get", fake_get), \
         mock.patch.object(data, "ALLOW_INSECURE_PUBLIC", True):
        bal, err = data.get_usdt_balance()
    assert bal is None and err
    assert len(calls) == 1, "signed call must try exactly one domain"
    assert calls[0][1] is not False, "signed call must never disable TLS verification"
    assert calls[0][0].startswith(data.BASE_URL)


def test_okx_rejection_is_reported_not_called_a_network_problem():
    def fake_get(url, headers=None, timeout=None, verify=None):
        return FakeResp({"code": "50111", "msg": "Invalid OK-ACCESS-KEY", "data": []})

    with mock.patch.object(data, "API_KEY", "k"), mock.patch.object(data, "SECRET_KEY", "s"), \
         mock.patch.object(data, "PASSPHRASE", "p"), mock.patch.object(data.requests, "get", fake_get):
        bal, err = data.get_usdt_balance()
    assert bal is None and "50111" in err and "ISP" not in err


def test_public_data_fails_over_between_domains():
    seen = []

    def fake_get(url, headers=None, timeout=None, verify=None):
        seen.append(url)
        if len(seen) == 1:
            raise requests.exceptions.ConnectionError("blocked")
        return FakeResp({"code": "0", "data": [{"last": "3000.5"}]})

    with mock.patch.object(data.requests, "get", fake_get):
        assert data.get_live_price() == 3000.5
    assert len(seen) == 2 and seen[0] != seen[1]


def test_total_network_failure_raises_network_error():
    with mock.patch.object(data.requests, "get", side_effect=requests.exceptions.ConnectionError("x")):
        try:
            data.get_live_price()
        except OKXNetworkError:
            return
    raise AssertionError("expected OKXNetworkError")


def test_get_candles_drops_unconfirmed_and_sorts():
    rows = [  # OKX order: newest first; newest is still forming
        ["3000000", "3", "3", "3", "3", "1", "1", "1", "0"],
        ["2000000", "2", "2", "2", "2", "1", "1", "1", "1"],
        ["1000000", "1", "1", "1", "1", "1", "1", "1", "1"],
    ]
    with mock.patch.object(data, "_okx_get", return_value={"data": rows}):
        df = data.get_candles()
    assert list(df["close"]) == [1.0, 2.0] and df["ts"].is_monotonic_increasing


def test_strategy_signals():
    # flat then rising: fast crosses above slow while above the 200 EMA
    prices = [100.0] * 260 + [100 - i * 0.2 for i in range(40)] + [90 + i * 1.5 for i in range(60)]
    df = pd.DataFrame({"ts": pd.date_range("2025-01-01", periods=len(prices), freq="h"),
                       "close": prices})
    df = add_indicators(df)
    buys = [i for i in range(3, len(df)) if generate_signal(df.iloc[: i + 1]).action == "BUY SIGNAL"]
    assert buys, "expected at least one BUY SIGNAL on the synthetic rally"
    assert all(df["bullish_crossover"].iloc[i] for i in buys)


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failures else 0)
