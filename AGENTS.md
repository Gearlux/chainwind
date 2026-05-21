# Chainwind Mandates

- **Extension, Not Fork:** Chainwind extends traidwind's visualization layer for crypto-specific data; it MUST NOT duplicate traidwind's download/backtest plumbing. Reuse `FreqtradeAdapter`, the YAML→JSON `config` translator, and the indicator/overlay registry.
- **Five Crypto-Website Downloaders:** `DownloadCoinGeckoMarketCap`, `DownloadDeFiLlamaStablecoins`, `DownloadFarsideETFFlows`, `DownloadFearGreed`, `DownloadMVRVZScore` are the canonical website-scraping sources. CCXT exchange data and non-crypto macro (FRED, yfinance) stay in traidwind — don't move them here.
- **CoinSpec Registry:** Per-coin metadata (data sources, indicator presets, on-chain overlays) lives in `coins.CoinSpec`. BTC / ETH / SOL are the builtin trio; new coins MUST extend the registry, never inline metadata into UI code.
- **Local-Only FastAPI:** `chainwind serve` binds to `127.0.0.1` and opens the local browser. Never bind to `0.0.0.0` or expose the server publicly — the future PyWebView / Tauri upgrade path assumes single-machine operation.
- **Inactive Submodule:** Chainwind is registered with `active = false` in `.gitmodules` so work-workstation checkouts skip it. Don't flip this in `.gitmodules`; activate locally with `git config --local submodule.chainwind.active true`.
- **Per-Coin Freshness UX:** The coin tab MUST report per-dataset freshness with one-click "Download missing" affordances. Background fetches MUST go through traidwind's downloader interface so logflow lineage is preserved.
