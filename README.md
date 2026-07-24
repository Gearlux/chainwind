# chainwind

Crypto **trackers & indicators** viewer. Extends [traidwind](https://github.com/Gearlux/traidwind)'s
visualization layer with crypto-specific data sources (CoinGecko, fear/greed, DeFiLlama, Farside ETF
flows, MVRV Z-score) and a local web UI that displays each tracked time series.

A **tracker** is one displayable series — a price chart or an indicator. Each tracker ties together
where its data lives on disk (a zarr written by one of the downloaders), how to (re)fetch it, and how
to draw it. The builtin set ships with a **Bitcoin price tracker** (candlesticks), the **MVRV
Z-Score** (a zone-shaded indicator), and an **Ethereum MVRV ratio** tracker; the other downloaders
slot in by extending the registry.

### MVRV: Bitcoin vs. multi-asset

Two free MVRV downloaders, by coverage:

| Downloader | Coverage | Auth | Columns |
|---|---|---|---|
| `DownloadMVRVZScore` | **BTC only** (bitcoin-data.com) | none | `[mvrv_zscore]` |
| `DownloadCoinMetricsMVRV` | **BTC, ETH, ADA + ~150 assets** (CoinMetrics community) | none | `[mvrv, mvrv_zscore]` |

`DownloadCoinMetricsMVRV` fetches the MVRV ratio (`CapMVRVCur`) and market cap (`CapMrktCurUSD`) for one
asset and derives the Z-Score locally (`(MV − RV) / stdev(MV)`, `RV = MV / ratio`). **Solana is not
covered** — there is no free realized-cap source for the account-based chain, so `asset: SOL` logs an
`[unsupported]` warning and writes nothing. The Z-Score's absolute scale is provider-specific (different
realized-cap methodology + stdev window than bitcoin-data.com), so interpret it on its own historical
range rather than reusing the BTC cycle bands.

```bash
# MVRV ratio + Z-Score for Ethereum (swap asset for BTC / ADA / ...)
sampleflux run chainwind/config/download_coinmetrics_mvrv.yaml
```

## Scope (v0.1.0)

- **Catalog (disk discovery)** — every dataset already downloaded under `$DATA_ROOT` is discovered
  automatically (OHLCV for every pair across spot/futures × timeframes, all CoinGecko coins, on-chain /
  sentiment / macro / funding / liquidations) and listed in a grouped, searchable sidebar with a
  freshness dot and an **Update** button. Datasets with no known downloader (derived dominance / SSR /
  liquidations) show as **view-only**. No hardcoded list — the catalog reflects what's on disk.
- **Panels** — click any dataset to open its chart. Prices render as TradingView candlesticks; indicators
  render as ECharts lines (MVRV is colour-coded by value zone: accumulation / neutral / elevated / top).
- **Compare** — tick several datasets to overlay them in one chart, with a **% change ↔ raw** toggle
  (% change from the window start is cross-scale comparable; raw puts each series on its own y-axis).
- **Update / freshness** — `chainwind update <id>` (re)downloads a dataset incrementally; `chainwind
  freshness` / `catalog` report what is missing or stale and which datasets are updatable. All reuse the
  existing `@configurable` downloaders.
- **Local-only** — `chainwind serve` starts a FastAPI server on `127.0.0.1` and opens your browser.
  Never binds publicly; future upgrade path to PyWebView / Tauri preserved.
- **Coin / portfolio tabs** — future work; the tracker registry + catalog are the foundation.

## Install (development)

```bash
git clone git@github.com:Gearlux/chainwind.git
cd chainwind
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,http]"          # [http] pulls fastapi + uvicorn for `serve`

# Build the UI (Vite + React + TypeScript):
cd frontend && npm ci && npm run build && cd ..
```

For end-user install (once published):

```bash
pip install "git+https://github.com/Gearlux/chainwind.git@main#egg=chainwind[http]"
```

## CLI

```bash
chainwind list-coins                 # show registered coins
chainwind list-trackers              # show the FEATURED (curated) trackers
chainwind catalog                    # list EVERY downloaded dataset, grouped, with freshness + updatable
chainwind freshness                  # flat freshness table over the whole catalog
chainwind update                     # update the featured set (incremental)
chainwind update ohlcv-binance-spot-ETH_USDT-1d   # update one dataset by catalog id
chainwind update --force             # re-fetch the featured set, ignoring the freshness window
chainwind serve [--port 8770] [--no-browser]      # start the UI (browser opens automatically)
```

The catalog is **discovered from disk** — `chainwind catalog` shows the ids you pass to
`chainwind update <id>` and the UI's Update buttons. Featured trackers keep stable ids
(`btc_ohlcv`, `mvrv_zscore`); discovered ones use slugs (`ohlcv-binance-spot-ETH_USDT-1d`,
`coingecko-ethereum`, `fred-WM2NS`). Derived datasets (dominance / SSR / liquidations) are
**view-only** — they display but can't be updated.

Data lands under `$DATA_ROOT` (see the `config/download_*.yaml` headers for exact paths) — make sure
`DATA_ROOT` is exported (e.g. `source project.bashrc` at the workspace root) before running.

## Adding a tracker

Tracker metadata lives **only** in `chainwind/trackers.py` (never inline it into UI code), mirroring
the `CoinSpec` registry. Extend `BUILTIN_TRACKERS` with a `TrackerSpec`:

```python
TrackerSpec(
    id="fear_greed",
    label="Crypto Fear & Greed",
    category="indicator",
    zarr_path="${DATA_ROOT}/traidwind/macro/fear_greed.zarr",
    value_columns=("value",),
    chart_lib="echarts",            # echarts → zone shading / gauges; lightweight → price panes
    chart_type="line",
    downloader_factory=lambda: DownloadFearGreed(out_root="${DATA_ROOT}/traidwind/macro"),
    zones=(Zone(None, 25.0, "#66bb6a", "Extreme fear"), Zone(75.0, None, "#e57373", "Extreme greed")),
)
```

The `downloader_factory` is the single source of truth for a tracker's update path — `chainwind
update` builds and runs it (setting `skip_if_fresh=False` under `--force`).

## Architecture

- **traidwind** owns the market-agnostic download/zarr/path helpers (`traidwind.paths`,
  `DownloadOHLCV`) and the viz primitives chainwind builds on.
- **chainwind** adds the crypto-website downloaders, the `TrackerSpec` registry
  (`chainwind/trackers.py`), the zarr→JSON series reader (`chainwind/series.py`), the update/freshness
  methods (`chainwind/update.py`), the FastAPI server (`chainwind/server.py`), and the React UI
  (`chainwind/frontend/`).
- **Charts split by role** — `lightweight-charts` for financial price panes (candlesticks + volume),
  `echarts` for indicators with value-zone shading and future gauges / diverging bars.
