"""Tests for the tracker update / freshness methods."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import chainwind.update as update_mod
from chainwind.trackers import TrackerSpec
from tests.conftest import WriteZarr


class FakeDownloader:
    """Records run()/skip_if_fresh and writes a fresh zarr so freshness reads back real."""

    def __init__(self, zpath: Path, write_zarr: WriteZarr) -> None:
        self.skip_if_fresh = True
        self.ran = False
        self._zpath = zpath
        self._write = write_zarr

    def run(self) -> None:
        self.ran = True
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        self._write(self._zpath, [[1.0]], [now], ["v"])


def _fake_spec(zpath: Path, downloader: FakeDownloader) -> TrackerSpec:
    return TrackerSpec(
        id="t",
        label="T",
        category="indicator",
        zarr_path=str(zpath),
        value_columns=("v",),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=lambda: downloader,
    )


def test_update_tracker_runs_and_reports_fresh(
    tmp_path: Path, write_zarr: WriteZarr, monkeypatch: pytest.MonkeyPatch
) -> None:
    dl = FakeDownloader(tmp_path / "t.zarr", write_zarr)
    spec = _fake_spec(tmp_path / "t.zarr", dl)
    monkeypatch.setattr(update_mod, "get_catalog_tracker", lambda _id: spec)

    result = update_mod.update_tracker("t")
    assert dl.ran is True
    assert result["exists"] is True
    assert result["stale"] is False


def test_update_tracker_force_disables_skip(
    tmp_path: Path, write_zarr: WriteZarr, monkeypatch: pytest.MonkeyPatch
) -> None:
    dl = FakeDownloader(tmp_path / "t.zarr", write_zarr)
    spec = _fake_spec(tmp_path / "t.zarr", dl)
    monkeypatch.setattr(update_mod, "get_catalog_tracker", lambda _id: spec)

    update_mod.update_tracker("t", force=True)
    assert dl.skip_if_fresh is False


def test_update_all_loops_registry(tmp_path: Path, write_zarr: WriteZarr, monkeypatch: pytest.MonkeyPatch) -> None:
    dl = FakeDownloader(tmp_path / "t.zarr", write_zarr)
    spec = _fake_spec(tmp_path / "t.zarr", dl)
    monkeypatch.setattr(update_mod, "list_trackers", lambda: (spec,))

    results = update_mod.update_all()
    assert len(results) == 1
    assert dl.ran is True
    assert results[0]["id"] == "t"


def test_freshness_report_maps_registry(tmp_path: Path, write_zarr: WriteZarr, monkeypatch: pytest.MonkeyPatch) -> None:
    write_zarr(tmp_path / "t.zarr", [[1.0]], [int(datetime.now(timezone.utc).timestamp() * 1000)], ["v"])
    spec = _fake_spec(tmp_path / "t.zarr", FakeDownloader(tmp_path / "t.zarr", write_zarr))
    monkeypatch.setattr(update_mod, "list_trackers", lambda: (spec,))

    report = update_mod.freshness_report()
    assert [r["id"] for r in report] == ["t"]
    assert report[0]["exists"] is True


def test_update_tracker_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        update_mod.update_tracker("does_not_exist")


def test_run_one_requires_run_method(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class NoRun:
        skip_if_fresh = True

    spec = TrackerSpec(
        id="t",
        label="T",
        category="indicator",
        zarr_path=str(tmp_path / "t.zarr"),
        value_columns=("v",),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=lambda: NoRun(),
    )
    monkeypatch.setattr(update_mod, "get_catalog_tracker", lambda _id: spec)
    with pytest.raises(TypeError):
        update_mod.update_tracker("t")


def test_update_view_only_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = TrackerSpec(
        id="vo",
        label="View only",
        category="indicator",
        zarr_path=str(tmp_path / "vo.zarr"),
        value_columns=("v",),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=None,  # view-only
    )
    monkeypatch.setattr(update_mod, "get_catalog_tracker", lambda _id: spec)
    with pytest.raises(ValueError, match="view-only"):
        update_mod.update_tracker("vo")
