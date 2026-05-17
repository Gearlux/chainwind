# chainwind

Crypto-coin data viewer + portfolio (scaffold). Extends [traidwind](https://github.com/Gearlux/traidwind)'s
visualization layer with crypto-specific data sources (CoinGecko, fear/greed, DeFiLlama, Farside ETF
flows, MVRV Z-score) and a per-coin tabbed UI.

## Scope (v0.1.0)

- **Coin tab** — pick a coin, see OHLCV chart with indicator overlays, on-chain/sentiment overlays,
  per-dataset freshness with one-click "Download missing" buttons, and a backtest panel (equity curve,
  drawdown chart, trade markers, sortable per-trade table).
- **Portfolio tab** — scaffold only; "coming soon" placeholder.
- **Portable** — `chainwind serve` starts a FastAPI server on `127.0.0.1` and opens your browser
  (Mac / Windows / Linux). Future upgrade path to PyWebView / Tauri preserved.

## Install (development)

```bash
git clone git@github.com:Gearlux/chainwind.git
cd chainwind
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

For end-user install (once published):

```bash
pip install git+https://github.com/Gearlux/chainwind.git@main
```

## CLI

```bash
chainwind list-coins                # show registered coins
chainwind freshness  <yaml>         # report missing / stale datasets
chainwind update     <yaml>         # download missing / stale datasets
chainwind serve [--port 8770]       # start the UI server (browser opens automatically)
```

## Architecture

- **traidwind** owns the market-agnostic viz primitives, the FastAPI factory, the lightweight-charts
  React component, the tab framework, and the chart-library registry.
- **chainwind** plugs in crypto-specific downloaders, per-coin metadata, on-chain overlay components,
  and composes the `CoinTab` / `PortfolioTab` views.
- The unified `chainwind serve` mounts both sets of routes on a single FastAPI app.

See the workspace plan for the full design.
