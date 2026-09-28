"""Read tracker zarr groups into JSON-serializable series + freshness, for the API.

Every workspace downloader writes the same zarr layout — a 2-D ``data`` array, a 1-D
``timestamps_ms`` (int64 epoch-ms) array, and a ``columns`` attr (see
``traidwind.convert.zarr_to_feather.ZarrToFeather`` for the canonical reader this mirrors).
These helpers turn that layout into plain dicts the FastAPI layer hands to the React charts:

* :func:`read_series` → ISO-8601 timestamps + per-column float lists (NaN → ``None`` so the
  payload is strict-JSON safe, matching traidwind's viz convention);
* :func:`tracker_freshness` → existence / last-timestamp / staleness, reading only the last
  ``timestamps_ms`` entry so the dashboard's per-tracker badges are cheap.

Path expansion and the staleness window reuse ``traidwind.paths`` so chainwind and traidwind
never disagree on where data lives or what "fresh" means.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import numpy as np
import zarr
from loggair import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

from chainwind.trackers import TrackerSpec

logger = get_logger(__name__)

# Default staleness window for freshness reporting (daily trackers go stale after a day).
DEFAULT_FRESHNESS_TOLERANCE_HOURS = 24


def _iso(ms: int) -> str:
    """epoch-ms → ISO-8601 UTC string."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _json_safe(x: float) -> Optional[float]:
    """NaN/inf → None so the series is strict-JSON serializable."""
    return None if (math.isnan(x) or math.isinf(x)) else float(x)


def read_series(
    spec: TrackerSpec,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Read ``spec``'s zarr into a JSON-serializable series dict.

    Args:
        spec: The tracker whose ``zarr_path`` is read.
        start_ms: Optional inclusive lower bound (epoch-ms) on the timestamps.
        end_ms: Optional inclusive upper bound (epoch-ms) on the timestamps.

    Returns:
        ``{"id", "label", "exists", "time": [iso...], "columns": {name: [float|None]},
        "attrs": {...}, "n_points": int}``. When the zarr is missing, ``exists`` is False
        and ``time``/``columns`` are empty (the UI renders an empty panel + an Update button).
    """
    zpath = _expand(spec.zarr_path)
    out: Dict[str, Any] = {
        "id": spec.id,
        "label": spec.label,
        "exists": False,
        "time": [],
        "columns": {},
        "attrs": {},
        "n_points": 0,
    }
    if not zpath.exists():
        logger.debug(f"[series] no zarr for {spec.id} at {zpath}")
        return out

    grp = zarr.open_group(str(zpath), mode="r")
    attrs = dict(grp.attrs)
    cols = list(cast(Any, attrs.get("columns", [])))
    ts = cast(np.ndarray, cast(Any, grp["timestamps_ms"])[:]).astype(np.int64)
    data = cast(np.ndarray, cast(Any, grp["data"])[:]).astype(np.float64)

    mask = np.ones(ts.shape[0], dtype=bool)
    if start_ms is not None:
        mask &= ts >= start_ms
    if end_ms is not None:
        mask &= ts <= end_ms
    ts = ts[mask]
    data = data[mask]

    # Surface only the requested value columns; fall back to all columns if the spec's
    # selection isn't present (e.g. a renamed source) so the panel still shows something.
    wanted = [c for c in spec.value_columns if c in cols] or cols
    col_idx = {name: cols.index(name) for name in wanted}

    out["exists"] = True
    out["attrs"] = {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in attrs.items()}
    out["time"] = [_iso(int(t)) for t in ts]
    out["columns"] = {name: [_json_safe(v) for v in data[:, idx].tolist()] for name, idx in col_idx.items()}
    out["n_points"] = int(ts.shape[0])
    return out


def tracker_freshness(
    spec: TrackerSpec,
    tolerance_hours: int = DEFAULT_FRESHNESS_TOLERANCE_HOURS,
) -> Dict[str, Any]:
    """Report on-disk freshness for ``spec`` (cheap — reads only the last timestamp).

    Returns:
        ``{"id", "label", "category", "chart_lib", "chart_type", "unit", "description",
        "coin", "exists", "last_ts": iso|None, "age_hours": float|None, "stale": bool,
        "n_points": int}``.
    """
    zpath = _expand(spec.zarr_path)
    info: Dict[str, Any] = {
        "id": spec.id,
        "label": spec.label,
        "category": spec.category,
        "chart_lib": spec.chart_lib,
        "chart_type": spec.chart_type,
        "unit": spec.unit,
        "description": spec.description,
        "coin": spec.coin,
        "exists": False,
        "last_ts": None,
        "age_hours": None,
        "stale": True,
        "n_points": 0,
    }
    if not zpath.exists():
        return info

    try:
        grp = zarr.open_group(str(zpath), mode="r")
        ts = cast(np.ndarray, cast(Any, grp["timestamps_ms"])[:])
    except (KeyError, FileNotFoundError, ValueError):
        return info
    if len(ts) == 0:
        info["exists"] = True
        return info

    last_ms = int(ts[-1])
    last_dt = datetime.fromtimestamp(last_ms / 1000.0, tz=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600.0
    info.update(
        {
            "exists": True,
            "last_ts": last_dt.isoformat(),
            "age_hours": round(age_hours, 2),
            "stale": not _zarr_is_fresh(zpath, tolerance_hours),
            "n_points": int(len(ts)),
        }
    )
    return info


def zones_payload(spec: TrackerSpec) -> List[Dict[str, Any]]:
    """Serialize a tracker's value zones for the ECharts ``markArea`` overlay."""
    return [{"lo": z.lo, "hi": z.hi, "color": z.color, "label": z.label} for z in spec.zones]


def read_primary_series(
    spec: TrackerSpec,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Read just the ONE primary column of ``spec`` — for the multi-series compare overlay.

    For OHLCV the primary is ``close``; otherwise the first declared value column. Returns
    ``{id, label, unit, time, values, exists}`` — a lightweight payload (no full OHLC) the
    Compare chart overlays + normalizes.
    """
    full = read_series(spec, start_ms=start_ms, end_ms=end_ms)
    cols = full["columns"]
    if "close" in cols:
        name: Optional[str] = "close"
    elif spec.value_columns and spec.value_columns[0] in cols:
        name = spec.value_columns[0]
    else:
        name = next(iter(cols), None)
    return {
        "id": spec.id,
        "label": spec.label,
        "unit": spec.unit,
        "exists": full["exists"],
        "time": full["time"],
        "values": cols.get(name, []) if name else [],
    }
