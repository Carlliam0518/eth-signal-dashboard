# ETH-USDT Rule-Based Signal Dashboard (OKX Read-Only)

A local Streamlit trading signal dashboard that pulls live **ETH-USDT** market data from OKX V5 public endpoints, evaluates a **20 / 50 / 200 EMA** trend-following strategy, calculates risk-managed position sizes, and generates a manual execution checklist for OKX Spot trading.

**Safety by Design:** This application never places orders, never uses leverage, and does not require trading permissions.

---

## 1. Strategy Rules

| Indicator / Rule | Configuration | Role |
| :--- | :--- | :--- |
| **Fast EMA** | 20-period EMA (1H Close) | Tracks short-term momentum |
| **Slow EMA** | 50-period EMA (1H Close) | Tracks medium-term momentum |
| **Trend Filter** | 200-period EMA (1H Close) | Only allows long entries when `Close > 200 EMA` |
| **BUY SIGNAL** | `20 EMA` crosses above `50 EMA` AND `Close > 200 EMA` | Evaluates on confirmed (closed) 1H candles |
| **EXIT / DO NOT BUY** | `20 EMA` crosses below `50 EMA` | Signals momentum loss; exit existing long or stay in cash |
| **WAIT** | No fresh crossover on the latest closed candle | Hold off on new entries |

---

## 2. Project File Structure

```text
eth-signal-dashboard/
├── .env                # Local environment variables & optional Read-Only API keys
├── requirements.txt    # Python package dependencies
├── config.py           # Strategy constants and .env loader
├── data.py             # OKX V5 public market data & Read-Only balance fetcher
├── indicators.py       # 20, 50, and 200 EMA calculations & crossover detection
├── strategy.py         # Signal state machine (BUY SIGNAL / WAIT / EXIT)
├── risk.py             # The one position-sizing function (used by trade_plan.py)
├── trade_plan.py       # Stop-loss / take-profit plan built on risk.py
├── tests/              # Offline tests: python tests/test_dashboard.py
├── app.py              # Streamlit UI and interactive Plotly candlestick chart
└── README.md           # Setup and execution guide
```

---

## 3. Step-by-Step Setup & Installation

### Step 1: Open Your Terminal & Create the Project Folder
Open your terminal (or VS Code integrated terminal) and run:

```bash
mkdir eth-signal-dashboard
cd eth-signal-dashboard
```

Place all project files (`requirements.txt`, `.env`, `config.py`, `data.py`, `indicators.py`, `strategy.py`, `risk.py`, `trade_plan.py`, `app.py`) inside this folder.

### Step 2: Create and Activate a Virtual Environment
Using an isolated Python virtual environment keeps your global packages clean:

**Windows (PowerShell / CMD):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Required Packages
With your virtual environment activated, install the dependencies:

```bash
pip install -r requirements.txt
```

### Step 4: Configure Your `.env` File
Open `.env` in your code editor:
* **No API Keys Needed for Signals:** Market candles and live ticker prices use public OKX endpoints. You can leave `OKX_API_KEY`, `OKX_SECRET_KEY`, and `OKX_PASSPHRASE` blank and adjust your capital directly in the dashboard sidebar.
* **Optional Read-Only Balance Sync:** If you want the dashboard to automatically pull your available USDT balance from OKX, paste your **Read-Only** API credentials into `.env`. Set `OKX_FLAG=0` for a live OKX account or `OKX_FLAG=1` for an OKX Demo Trading account.

---

## 4. How to Run the Dashboard

From inside the `eth-signal-dashboard` directory (with `.venv` activated), launch Streamlit:

```bash
streamlit run app.py
```

* Streamlit will start a local server and automatically open **`http://localhost:8501`** in your default web browser.
* To stop the server at any time, press **`Ctrl + C`** in your terminal.

---

## 5. How Position Sizing Works

With **$100** trading capital, **1% risk per trade**, a **2% stop-loss**, and a **2:1 reward-to-risk ratio**:
1. **Dollar Risk (`Risk Amount`):** `$100 × 1% = $1.00` maximum loss if your stop-loss is hit.
2. **Position Value (`Notional USDT`):** `$1.00 / 0.02 (2% stop distance) = $50.00` worth of ETH bought on Spot.
3. **If Stop-Loss Hits (`-2%`):** A 2% drop on a `$50.00` position loses **`$1.00`** (exactly 1% of your `$100` account).
4. **If Take-Profit Hits (`+4%` at 2:1 R:R):** A 4% gain on a `$50.00` position nets **`$2.00`** (a 2% gain on your `$100` account).

---

## 6. Live Updates and How to Verify Them

Streamlit normally re-runs only when you click something. The market panel runs on a timer
(sidebar: **Auto-refresh**, every 5 to 60 seconds) with no click and no page reload.

To check it is really live:
1. Watch the line under the title: **"Price fetched Ns ago"** counts up and drops back to a few seconds after each refresh.
2. The ETH-USDT price shows **"+x.xx since last update"** after each refresh.
3. Compare the price with OKX (Trade -> Spot -> ETH/USDT) at the same moment.
4. Set the refresh to 5 s and untick **Auto-refresh** to see the difference: the counter then just keeps growing.
5. If candle data is more than about 63 minutes old, a red **STALE** banner appears.

The **signal** itself only changes when a 1H candle closes (and appears up to ~30 s later, the candle cache time).
The price, the timestamps and the plan numbers move with every refresh.
Run `python tests/test_app_smoke.py` to execute the whole page script offline against simulated data.

## 7. Security Notes

* **TLS is always verified for requests that carry your API key.** Signed calls go to one domain (`OKX_BASE_URL`) and never fall back to unverified HTTPS. If you can't reach OKX, fix the network (Cloudflare WARP / VPN / DNS `1.1.1.1`) rather than disabling certificate checks.
* `ALLOW_INSECURE_PUBLIC=true` exists only as a last resort for **public** candle/price data. The dashboard shows a warning while it is on, because a middleman could then alter the candles.
* Use **Read-Only** keys here. Never enable *Withdraw* on any key.
* If a key has ever been pasted into a chat, an email or a screenshot, delete it in OKX and create a new one.
* `.env` must be a file literally named `.env` and must stay out of Git (see `.gitignore`).

## 8. Turning Your PC Off

This dashboard is stateless and places no orders, so closing it or powering off the PC changes nothing on OKX. Position-state saving, graceful shutdown and restart reconciliation only matter once a bot is placing orders (see the `eth-bot` project).
