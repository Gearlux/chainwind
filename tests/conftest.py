"""Shared fixtures for chainwind tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, List, Sequence

import numpy as np
import pytest
import zarr
from loguru import logger as _loguru_logger

# Type of the zarr-writing helper the fixtures expose.
WriteZarr = Callable[[Path, Sequence[Sequence[float]], Sequence[int], Sequence[str]], None]


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _write_zarr(
    path: Path,
    data2d: Sequence[Sequence[float]],
    ts_ms: Sequence[int],
    columns: Sequence[str],
) -> None:
    """Write a tracker-layout zarr group (2-D ``data`` + 1-D ``timestamps_ms`` + ``columns``)."""
    arr = np.asarray(data2d, dtype="float64")
    ts = np.asarray(ts_ms, dtype="int64")
    path.parent.mkdir(parents=True, exist_ok=True)
    root = zarr.open_group(str(path), mode="w")
    root.create_array("data", data=arr, chunks=arr.shape)
    root.create_array("timestamps_ms", data=ts, chunks=ts.shape)
    root.attrs.update({"columns": list(columns)})


@pytest.fixture
def write_zarr() -> WriteZarr:
    """Return the tracker-layout zarr writer (see :func:`_write_zarr`)."""
    return _write_zarr


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``$DATA_ROOT`` at a tmp dir and write a fresh zarr for every builtin tracker.

    Lets the server/CLI tests exercise the real registry without touching the operator's
    on-disk data or the network. Each tracker gets a single fresh (now-timestamped) point
    with one value per declared column.
    """
    from chainwind.series import _expand
    from chainwind.trackers import list_trackers

    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    now = _now_ms()
    for spec in list_trackers():
        ncols = len(spec.value_columns)
        _write_zarr(_expand(spec.zarr_path), [[1.0] * ncols], [now], spec.value_columns)
    return tmp_path


@pytest.fixture
def loguru_capture() -> Iterator[List[str]]:
    """Capture loguru records as plain strings (caplog only sees stdlib logs)."""
    records: List[str] = []
    sink_id = _loguru_logger.add(lambda msg: records.append(str(msg)), level="TRACE")
    try:
        yield records
    finally:
        _loguru_logger.remove(sink_id)
