# chainwind — backlog

Open work for this project. Cross-cutting / multi-project initiatives live in the
workspace root `TASKS.md`. Completed items are not archived here — git history is the record.

- [ ] Wire updaters for the remaining view-only families (coinalyze liquidations/OI, derived dominance/SSR recompute) so they're refreshable too. @low
- [ ] Coin tab (per-coin OHLCV + overlays + backtest panel) and portfolio tab. @medium @feature
- [ ] Richer indicator widgets (Fear & Greed gauge, ETF-flow diverging bars) via the registry + ECharts. @low
- [ ] **`CHAINWIND_HTTP_HOST` can bind the server to a public address** @low @bug — `chainwind serve` is meant to bind loopback only, but `chainwind/chainwind/server.py:169` (`host = os.environ.get("CHAINWIND_HTTP_HOST", host)`) lets the variable override the `host` argument with no warning: measured with a stubbed `uvicorn.run`, `CHAINWIND_HTTP_HOST=0.0.0.0` gives `{'host': '0.0.0.0', 'port': 8770}` and the log line `chainwind UI on http://0.0.0.0:8770`. `tests/test_server.py:144-153` tests only the explicit argument, never the variable.
- [ ] **Docs and comments describe the old surface** @docs @small — two claims no code backs:
  - `chainwind/README.md` — never documents `CHAINWIND_HTTP_HOST` / `CHAINWIND_HTTP_PORT` (`grep -c CHAINWIND_HTTP README.md` → 0), although the workspace `.env:91-94` says "see chainwind/README.md §CLI"; the variables are read only in `chainwind/chainwind/server.py:165-170`.
  - `chainwind/pyproject.toml:4`, `chainwind/chainwind/__init__.py:3` and `chainwind/README.md:3` — say chainwind "extends" traidwind's visualization layer, and `traidwind/traidwind/viz/__init__.py:8-11` says chainwind registers its encoders there; chainwind imports nothing from `traidwind.viz` (its imports from traidwind are `traidwind.paths` and `traidwind.download`: `series.py:24`, `trackers.py:117`, `discovery.py:24`).
