"""Tests for the zarr series reader + freshness helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from chainwind.series import read_series, tracker_freshness, zones_payload
from chainwind.trackers import TrackerSpec, Zone
from tests.conftest import WriteZarr


def _spec(zarr_path: Path, value_columns: tuple, **kw: object) -> TrackerSpec:
    return TrackerSpec(
        id="t",
        label="T",
        category=kw.get("category", "indicator"),  # type: ignore[arg-type]
        zarr_path=str(zarr_path),
        value_columns=value_columns,
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=lambda: None,
        zones=kw.get("zones", ()),  # type: ignore[arg-type]
    )


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_read_series_returns_columns_and_iso_time(tmp_path: Path, write_zarr: WriteZarr) -> None:
    zp = tmp_path / "x.zarr"
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ts = [_ms(base), _ms(base + timedelta(days=1)), _ms(base + timedelta(days=2))]
    write_zarr(zp, [[1.0], [2.0], [3.0]], ts, ["mvrv_zscore"])

    out = read_series(_spec(zp, ("mvrv_zscore",)))
    assert out["exists"] is True
    assert out["n_points"] == 3
    assert out["time"][0].startswith("2024-01-01")
    assert out["columns"]["mvrv_zscore"] == [1.0, 2.0, 3.0]
    assert out["attrs"]["columns"] == ["mvrv_zscore"]


def test_read_series_selects_requested_columns(tmp_path: Path, write_zarr: WriteZarr) -> None:
    zp = tmp_path / "ohlcv.zarr"
    write_zarr(
        zp,
        [[1, 2, 3, 4, 5]],
        [_ms(datetime(2024, 1, 1, tzinfo=timezone.utc))],
        ["open", "high", "low", "close", "volume"],
    )
    out = read_series(_spec(zp, ("close", "volume")))
    assert set(out["columns"]) == {"close", "volume"}
    assert out["columns"]["close"] == [4.0]


def test_read_series_nan_becomes_none(tmp_path: Path, write_zarr: WriteZarr) -> None:
    zp = tmp_path / "nan.zarr"
    write_zarr(zp, [[float("nan")], [2.0]], [1, 2], ["v"])
    out = read_series(_spec(zp, ("v",)))
    assert out["columns"]["v"] == [None, 2.0]


def test_read_series_time_window(tmp_path: Path, write_zarr: WriteZarr) -> None:
    zp = tmp_path / "win.zarr"
    write_zarr(zp, [[1.0], [2.0], [3.0]], [100, 200, 300], ["v"])
    out = read_series(_spec(zp, ("v",)), start_ms=150, end_ms=250)
    assert out["n_points"] == 1
    assert out["columns"]["v"] == [2.0]


def test_read_series_missing_zarr(tmp_path: Path) -> None:
    out = read_series(_spec(tmp_path / "nope.zarr", ("v",)))
    assert out["exists"] is False
    assert out["time"] == []
    assert out["columns"] == {}


def test_tracker_freshness_fresh_vs_stale(tmp_path: Path, write_zarr: WriteZarr) -> None:
    now = datetime.now(timezone.utc)
    fresh = tmp_path / "fresh.zarr"
    write_zarr(fresh, [[1.0]], [_ms(now)], ["v"])
    info = tracker_freshness(_spec(fresh, ("v",)))
    assert info["exists"] is True
    assert info["stale"] is False
    assert info["n_points"] == 1

    stale = tmp_path / "stale.zarr"
    write_zarr(stale, [[1.0]], [_ms(now - timedelta(days=10))], ["v"])
    assert tracker_freshness(_spec(stale, ("v",)))["stale"] is True


def test_tracker_freshness_missing(tmp_path: Path) -> None:
    info = tracker_freshness(_spec(tmp_path / "absent.zarr", ("v",)))
    assert info["exists"] is False
    assert info["last_ts"] is None
    assert info["stale"] is True


def test_zones_payload_serializes(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "z.zarr", ("v",), zones=(Zone(None, 0.0, "#0f0", "low"),))
    payload = zones_payload(spec)
    assert payload == [{"lo": None, "hi": 0.0, "color": "#0f0", "label": "low"}]


def test_tracker_freshness_empty_zarr(tmp_path: Path) -> None:
    import numpy as np
    import zarr

    zp = tmp_path / "empty.zarr"
    root = zarr.open_group(str(zp), mode="w")
    root.create_array("timestamps_ms", data=np.array([]), chunks=(1,))
    root.create_array("data", data=np.zeros((0, 1)), chunks=(1, 1))
    root.attrs.update({"columns": ["v"]})
    info = tracker_freshness(_spec(zp, ("v",)))
    assert info["exists"] is True
    assert info["last_ts"] is None


def test_tracker_freshness_corrupt_zarr(tmp_path: Path) -> None:
    import zarr

    zp = tmp_path / "corrupt.zarr"
    root = zarr.open_group(str(zp), mode="w")  # no timestamps_ms dataset
    root.attrs.update({"columns": ["v"]})
    info = tracker_freshness(_spec(zp, ("v",)))
    assert info["exists"] is False
