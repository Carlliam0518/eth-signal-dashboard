"""Runs app.py end to end against a stand-in Streamlit and simulated OKX responses.
Not a browser test, but it executes every line of the page script and checks the live-update
wiring. Run: python tests/test_app_smoke.py"""
import os
import runpy
import sys
import time
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

sys.modules["plotly"] = mock.MagicMock()
sys.modules["plotly.graph_objects"] = mock.MagicMock()

import data  # noqa: E402


def candle_rows(hours_ago_newest=0, n=300):
    """OKX format: newest first, newest candle still forming (confirm='0')."""
    hour = 3600 * 1000
    newest_open = (int(time.time() * 1000) // hour) * hour - hours_ago_newest * hour
    rows = []
    for k in range(n):
        ts = newest_open - k * hour
        px = 3000 + 5 * ((n - k) % 17)
        rows.append([str(ts), str(px), str(px + 2), str(px - 2), str(px), "1", "1", "1", "0" if k == 0 else "1"])
    return rows


def fake_okx(price, stale_hours=0, fail=False):
    def _get(path, params=None, signed=False):
        if fail:
            raise data.OKXNetworkError("simulated outage")
        if "candles" in path:
            return {"data": candle_rows(stale_hours)}
        if "ticker" in path:
            return {"data": [{"last": str(price)}]}
        raise AssertionError(path)
    return _get


class Page:
    """Stand-in for the `streamlit` module that records what the app draws."""

    def __init__(self, auto_refresh=True, refresh=15):
        self.session_state = {}
        self.run_every_seen = []
        self.errors, self.warnings, self.captions, self.columns_made = [], [], [], []
        self.auto_refresh, self.refresh = auto_refresh, refresh

    def module(self):
        page, st = self, mock.MagicMock()
        st.session_state = self.session_state

        def cache_data(*a, **k):
            return (lambda f: f)
        cache_data.clear = lambda: None
        st.cache_data = cache_data

        def fragment(*a, run_every=None, **k):
            page.run_every_seen.append(run_every)
            return lambda f: f
        st.fragment = fragment

        def columns(n, **k):
            cols = [mock.MagicMock() for _ in range(n)]
            page.columns_made.extend(cols)
            return cols
        st.columns = columns
        st.number_input = lambda *a, **k: k["value"]
        st.slider = lambda *a, **k: k["value"]
        st.button = lambda *a, **k: False
        st.checkbox = lambda label, value=False, **k: page.auto_refresh if "refresh" in label.lower() else value
        st.selectbox = lambda label, options, index=0, **k: page.refresh
        st.error = lambda msg, *a, **k: page.errors.append(str(msg))
        st.warning = lambda msg, *a, **k: page.warnings.append(str(msg))
        st.caption = lambda msg, *a, **k: page.captions.append(str(msg))
        return st

    def metrics(self, label):
        return [c.args[0:2] + (c.kwargs.get("delta"),) for col in self.columns_made
                for c in col.metric.call_args_list if c.args and c.args[0] == label]


def run_app(page, **okx_kwargs):
    with mock.patch.object(data, "_okx_get", fake_okx(**okx_kwargs)), \
         mock.patch.dict(sys.modules, {"streamlit": page.module()}):
        runpy.run_path(os.path.join(ROOT, "app.py"))


def test_fresh_data_renders_and_shows_data_age():
    page = Page()
    run_app(page, price=3012.34)
    assert not [e for e in page.errors if "Could not update" in e or "STALE" in e], page.errors
    assert page.metrics("ETH-USDT")[0][1] == "$3,012.34"
    assert any("Price fetched" in c and "auto-refreshing every 15s" in c for c in page.captions)


def test_timer_is_registered_so_page_updates_without_clicks():
    on = Page(auto_refresh=True, refresh=5)
    run_app(on, price=3000)
    assert on.run_every_seen == ["5s"]
    off = Page(auto_refresh=False)
    run_app(off, price=3000)
    assert off.run_every_seen == [None]
    assert any("auto-refresh OFF" in c for c in off.captions)


def test_price_change_is_shown_between_updates():
    page = Page()
    run_app(page, price=3000.00)
    run_app(page, price=3004.50)           # next timer tick (session_state is shared)
    first, second = page.metrics("ETH-USDT")
    assert first[2] is None and second[2] == "+4.50 since last update", (first, second)


def test_stale_candles_raise_a_visible_error():
    page = Page()
    run_app(page, price=3000, stale_hours=6)
    assert any("STALE" in e for e in page.errors), page.errors


def test_okx_outage_shows_message_instead_of_crashing():
    page = Page()
    run_app(page, price=3000, fail=True)
    assert any("Could not update dashboard" in e and "simulated outage" in e for e in page.errors)


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                import traceback; failures += 1; print(f"FAIL {name}: {exc!r}"); traceback.print_exc()
    sys.exit(1 if failures else 0)
