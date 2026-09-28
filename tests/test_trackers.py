"""Tests for the tracker registry."""

from __future__ import annotations

import dataclasses

import pytest

from chainwind.trackers import BUILTIN_TRACKERS, TrackerSpec, get_tracker, list_trackers


def test_registry_has_builtin_trackers() -> None:
    ids = {t.id for t in list_trackers()}
    assert {"btc_ohlcv", "mvrv_zscore", "btc_price"} <= ids


def test_get_tracker_case_insensitive() -> None:
    assert get_tracker("MVRV_ZSCORE").id == "mvrv_zscore"
    assert get_tracker("  btc_ohlcv ").id == "btc_ohlcv"


def test_get_tracker_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_tracker("does_not_exist")


def test_specs_are_frozen() -> None:
    spec = list_trackers()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.id = "mutated"  # type: ignore[misc]


def test_chart_fields_are_closed_values() -> None:
    for t in BUILTIN_TRACKERS:
        assert t.category in ("price", "indicator")
        assert t.chart_lib in ("lightweight", "echarts")
        assert t.chart_type in ("candlestick", "line")


def test_mvrv_has_zone_bands() -> None:
    mvrv = get_tracker("mvrv_zscore")
    assert mvrv.chart_lib == "echarts"
    assert len(mvrv.zones) == 4
    # Bands tile the value domain end-to-end (open lower bound .. open upper bound).
    assert mvrv.zones[0].lo is None
    assert mvrv.zones[-1].hi is None


def test_downloader_factories_build_runnables() -> None:
    for t in BUILTIN_TRACKERS:
        assert t.downloader_factory is not None  # all featured trackers are updatable
        downloader = t.downloader_factory()
        assert hasattr(downloader, "run")
        assert hasattr(downloader, "skip_if_fresh")


def test_value_columns_typed_tuple() -> None:
    spec = get_tracker("btc_ohlcv")
    assert spec.value_columns == ("open", "high", "low", "close", "volume")
    assert isinstance(spec, TrackerSpec)
