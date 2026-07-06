"""Update trackers and their on-disk values + report freshness.

These are the "methods to update trackers and values" — the programmatic core the CLI
(``chainwind update`` / ``chainwind freshness``) and the FastAPI server both call:

* :func:`update_tracker` builds a tracker's downloader via its
  :attr:`~chainwind.trackers.TrackerSpec.downloader_factory` and runs it. The download is
  incremental by default (the downloaders skip when their zarr is within the freshness
  window); ``force=True`` flips ``skip_if_fresh`` off so the values are re-fetched.
* :func:`update_all` runs the whole registry.
* :func:`freshness_report` maps :func:`~chainwind.series.tracker_freshness` over the registry.

The downloaders are reused verbatim — chainwind adds no new download plumbing (extension,
not fork).
"""

from typing import Any, Dict, List

from loggair import get_logger

from chainwind.series import tracker_freshness
from chainwind.trackers import TrackerSpec, get_catalog_tracker, is_updatable, list_trackers

logger = get_logger(__name__)


def update_tracker(tracker_id: str, force: bool = False) -> Dict[str, Any]:
    """Fetch the latest values for one tracker (resolved across the FULL catalog).

    Args:
        tracker_id: Catalog id (e.g. ``"mvrv_zscore"`` or ``"ohlcv-binance-spot-ETH_USDT-1d"``).
        force: If True, bypass the downloader's ``skip_if_fresh`` so values are re-fetched
            even when the zarr is already fresh.

    Returns:
        The post-run freshness dict from :func:`chainwind.series.tracker_freshness`.

    Raises:
        KeyError: unknown id. ValueError: the tracker is view-only (no downloader).
    """
    spec = get_catalog_tracker(tracker_id)
    return _run_one(spec, force=force)


def update_all(force: bool = False) -> List[Dict[str, Any]]:
    """Update every FEATURED tracker (the dashboard set); returns one freshness dict each.

    Scoped to the curated featured trackers — not the whole catalog — so a single click never
    triggers dozens of network downloads. Update other datasets individually from the catalog.
    """
    results: List[Dict[str, Any]] = []
    for spec in list_trackers():
        results.append(_run_one(spec, force=force))
    return results


def freshness_report() -> List[Dict[str, Any]]:
    """Report on-disk freshness for every FEATURED tracker (no fetching)."""
    return [tracker_freshness(spec) for spec in list_trackers()]


def _run_one(spec: TrackerSpec, force: bool) -> Dict[str, Any]:
    if not is_updatable(spec):
        raise ValueError(f"Tracker {spec.id!r} is view-only (no downloader) — cannot update.")
    assert spec.downloader_factory is not None  # narrowed by is_updatable
    downloader = spec.downloader_factory()
    # The downloaders expose `skip_if_fresh` as a plain attribute; flip it for a forced
    # refresh rather than threading the flag through every factory signature.
    if force and hasattr(downloader, "skip_if_fresh"):
        downloader.skip_if_fresh = False
    label = downloader.__class__.__name__
    logger.info(f"[update] {spec.id} via {label} (force={force})")
    if not hasattr(downloader, "run"):
        raise TypeError(f"Downloader for tracker {spec.id!r} does not implement run()")
    downloader.run()
    return tracker_freshness(spec)
