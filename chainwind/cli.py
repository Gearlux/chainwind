"""Chainwind CLI.

Commands:

* ``chainwind list-coins``                — print the builtin coin registry.
* ``chainwind list-trackers``             — print the featured (curated) tracker registry.
* ``chainwind catalog``                   — list EVERY downloaded dataset, grouped, with freshness.
* ``chainwind freshness``                 — flat freshness table over the full catalog.
* ``chainwind update [tracker_id] [--force]`` — fetch latest values (featured set, or one catalog id).
* ``chainwind serve [--port N] [--no-browser]`` — start the local UI server.

NOTE: do not add ``from __future__ import annotations`` here — liquifai's DI inspects the actual
class objects from parameter annotations and PEP 563 string annotations break that lookup.
"""

from liquifai import LiquifyApp
from loggair import get_logger

from chainwind.coins import list_coins
from chainwind.series import tracker_freshness
from chainwind.trackers import catalog, is_updatable, list_trackers
from chainwind.update import update_all, update_tracker

logger = get_logger(__name__)

app = LiquifyApp(name="chainwind", description="crypto trackers & indicators viewer.")


@app.script_command(name="list-coins")
def list_coins_cmd() -> None:
    """Print the builtin coin registry."""
    coins = list_coins()
    width = max(len(c.symbol) for c in coins)
    print(f"{'symbol'.ljust(width)}  name           default_pair       coingecko_id")
    print(f"{'-' * width}  -------------  -----------------  -------------")
    for coin in coins:
        print(f"{coin.symbol.ljust(width)}  {coin.name:<13}  {coin.default_pair:<17}  {coin.coingecko_id}")
    print()
    print(f"{len(coins)} coin(s) registered.")


@app.script_command(name="list-trackers")
def list_trackers_cmd() -> None:
    """Print the builtin tracker registry."""
    trackers = list_trackers()
    width = max(len(t.id) for t in trackers)
    print(f"{'id'.ljust(width)}  category   chart                 label")
    print(f"{'-' * width}  ---------  --------------------  -----")
    for t in trackers:
        chart = f"{t.chart_lib}/{t.chart_type}"
        print(f"{t.id.ljust(width)}  {t.category:<9}  {chart:<20}  {t.label}")
    print()
    print(f"{len(trackers)} tracker(s) registered.")


def _print_freshness(reports: list) -> None:
    width = max((len(r["id"]) for r in reports), default=2)
    print(f"{'id'.ljust(width)}  exists  stale  update    points  last_ts")
    print(f"{'-' * width}  ------  -----  --------  ------  -------")
    for r in reports:
        exists = "yes" if r["exists"] else "NO"
        stale = "yes" if r["stale"] else "no"
        upd = "yes" if r.get("updatable", True) else "view-only"
        last = r["last_ts"] or "-"
        print(f"{r['id'].ljust(width)}  {exists:<6}  {stale:<5}  {upd:<8}  {r['n_points']:<6}  {last}")


def _catalog_freshness() -> list:
    """Freshness rows over the full catalog, each tagged with ``updatable``."""
    return [{**tracker_freshness(s), "updatable": is_updatable(s)} for s in catalog()]


@app.script_command(name="catalog")
def catalog_cmd() -> None:
    """List every downloaded dataset, grouped, with freshness + updatability."""
    specs = catalog()
    groups: dict = {}
    for s in specs:
        groups.setdefault(s.group or "Other", []).append(s)
    for group, items in groups.items():
        print(f"\n## {group} ({len(items)})")
        rows = [{**tracker_freshness(s), "updatable": is_updatable(s)} for s in items]
        _print_freshness(rows)
    updatable = sum(is_updatable(s) for s in specs)
    print(f"\n{len(specs)} dataset(s): {updatable} updatable, {len(specs) - updatable} view-only.")


@app.script_command(name="freshness")
def freshness_cmd() -> None:
    """Flat freshness table over the full catalog (no fetching)."""
    _print_freshness(_catalog_freshness())


@app.script_command(name="update", positionals=["tracker_id"])
def update_cmd(tracker_id: str = "", force: bool = False) -> None:
    """Download latest values for all trackers, or one named ``tracker_id``.

    Examples::

        chainwind update                 # update every tracker (incremental)
        chainwind update mvrv_zscore     # update just one
        chainwind update --force         # re-fetch everything, ignoring freshness
    """
    target = tracker_id.strip()
    if target:
        try:
            reports = [update_tracker(target, force=force)]
        except (KeyError, ValueError) as exc:
            print(f"Cannot update {target!r}: {exc}")
            return
    else:
        reports = update_all(force=force)
    _print_freshness(reports)


@app.script_command(name="serve")
def serve_cmd(host: str = "127.0.0.1", port: int = 8770, no_browser: bool = False) -> None:
    """Start the local trackers & indicators UI server (binds to 127.0.0.1).

    Example: ``chainwind serve --port 8888 --no-browser``.
    """
    from chainwind.server import serve

    serve(host=host, port=port, open_browser=not no_browser)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
