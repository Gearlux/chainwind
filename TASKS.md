# chainwind — backlog

Open work for this project. Cross-cutting / multi-project initiatives live in the
workspace root `TASKS.md`. Completed items are not archived here — git history is the record.

- [ ] Wire updaters for the remaining view-only families (coinalyze liquidations/OI, derived dominance/SSR recompute) so they're refreshable too. @low
- [ ] Coin tab (per-coin OHLCV + overlays + backtest panel) and portfolio tab. @medium @feature
- [ ] Richer indicator widgets (Fear & Greed gauge, ETF-flow diverging bars) via the registry + ECharts. @low
- [ ] **`CHAINWIND_HTTP_HOST` can bind the server to a public address** @low @bug — `chainwind serve` is meant to bind loopback only, but `chainwind/chainwind/server.py:169` (`host = os.environ.get("CHAINWIND_HTTP_HOST", host)`) lets the variable override the `host` argument with no warning: measured with a stubbed `uvicorn.run`, `CHAINWIND_HTTP_HOST=0.0.0.0` gives `{'host': '0.0.0.0', 'port': 8770}` and the log line `chainwind UI on http://0.0.0.0:8770`. `tests/test_server.py:144-153` tests only the explicit argument, never the variable. `CHAINWIND_HTTP_PORT` overrides `--port` the same way: both variables WIN over the command-line flags rather than filling in when a flag is absent (the README documents that today; decide it with the host question).
