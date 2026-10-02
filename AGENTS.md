# Chainwind Mandates

Rules only. Usage is in the [README](README.md). Root `AGENTS.md` rules are not repeated here.

## Current state

A crypto-coin data viewer built on traidwind's downloaders and path helpers. The pieces:
- `chainwind/download/`: the six crypto and on-chain downloaders.
- `coins.py` (`CoinSpec`) and `trackers.py` (`TrackerSpec`): the two registries.
- `discovery.py`: the catalog scanned from disk.
- `series.py` (zarr to JSON), `update.py` (update and freshness).
- `server.py` (local FastAPI) and `frontend/` (React SPA).

CLI: `list-coins`, `list-trackers`, `catalog`, `freshness`, `update`, `serve`. The per-coin tab
and the portfolio tab are not built (`TASKS.md`). Solana MVRV is unsupported (below).

## Rules

- Extend traidwind, never duplicate it. Today chainwind reuses traidwind's downloaders and
  `traidwind.paths`. A backtest panel must reuse `FreqtradeAdapter`, the config translator and
  the indicator/overlay registry.
- The crypto-website and on-chain sources are `DownloadCoinGeckoMarketCap`,
  `DownloadDeFiLlamaStablecoins`, `DownloadFarsideETFFlows`, `DownloadFearGreed`,
  `DownloadMVRVZScore` and `DownloadCoinMetricsMVRV`. CCXT exchange data and non-crypto macro
  (FRED, yfinance) stay in traidwind.
- MVRV is two downloaders, split by coverage:
  - `DownloadMVRVZScore` is Bitcoin-only and writes `[mvrv_zscore]`.
  - `DownloadCoinMetricsMVRV` is multi-asset, derives the Z-Score locally and writes
    `[mvrv, mvrv_zscore]`. An unsupported or gated asset (Solana) logs `[unsupported]`, writes
    nothing and never raises.
    (`tests/test_download_coinmetrics_mvrv.py::TestDownloadCoinMetricsMVRV::test_unsupported_asset_logs_warning`)
  - The two Z-Scores are not scale-comparable. Chart the ratio of a CoinMetrics series and attach
    no `zones` unless they are calibrated per asset (the `eth_mvrv` tracker does this).
- Metadata lives in the registries, never inline in UI, CLI or API code. New coins extend
  `BUILTIN_COINS`, new trackers extend `BUILTIN_TRACKERS`, and the UI reads `list_trackers()` /
  `get_tracker()`. (`tests/test_coins.py`, `tests/test_trackers.py`)
  - A tracker's `downloader_factory` is the single source of its update path:
    `chainwind update` builds it and sets `skip_if_fresh=False` under `--force`.
    (`tests/test_update.py::test_update_tracker_force_disables_skip`)
  - `category`, `chart_lib` and `chart_type` stay closed `Literal`s
    (`tests/test_trackers.py::test_chart_fields_are_closed_values`).
- The catalog is disk truth: `trackers.catalog()` is `discovery.discover_trackers()` merged with
  the curated `BUILTIN_TRACKERS`, matched by `zarr_path`. A curated tracker not yet on disk
  still lists, as missing.
  - Discovery's path-to-id conventions stay the exact inverse of the writers
    (`traidwind.paths._zarr_path`): disk `BTC_USDT:USDT` is CCXT `BTC/USDT:USDT`. Only `spot/`
    and `futures/` are walked. (`tests/test_discovery.py`)
  - A dataset with no downloader is view-only: `update_tracker` raises `ValueError` and the
    server answers HTTP 400. (`tests/test_server.py::test_update_view_only_returns_400`)
  - A new downloader or path convention gets a discovery provider in the same change.
- The renderer comes from `TrackerSpec.chart_lib`: `lightweight-charts` for prices, ECharts for
  zoned indicators. Never hard-code a library per panel. Before `setData`, dedupe times by
  business day, last wins, because `lightweight-charts` needs strictly ascending unique times
  (`frontend/src/components/PriceChart.tsx`). *(unpinned)*
- `chainwind serve` binds `127.0.0.1` only. Never `0.0.0.0`, never public.
  (`tests/test_server.py::test_serve_invokes_uvicorn`)
  - The SPA source is `frontend/` and builds to `frontend/dist`, which the server mounts at `/`.
  - `fastapi` and `uvicorn` stay behind the `[http]` extra, so a data-only install has no web
    stack.
- The coin tab (not built) reports per-dataset freshness with a one-click "Download missing".
  Background fetches go through the downloaders, so loggair lineage is kept.
- chainwind is `active = false` in the root `.gitmodules`. Leave that line alone and activate
  locally with `git config --local submodule.chainwind.active true`.
