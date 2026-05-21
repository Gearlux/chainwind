"""Tests for :class:`chainwind.download.DownloadMVRVZScore`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, cast

import numpy as np
import pytest
import zarr

from chainwind.download import DownloadMVRVZScore


class TestDownloadMVRVZScore:
    URL = "https://bitcoin-data.com/api/v1/mvrv-zscore"

    @staticmethod
    def _payload(rows: List[tuple[str, int, float]]) -> List[dict]:
        """rows = list of (date_iso, unix_seconds, mvrv_zscore)."""
        return [{"d": d, "unixTs": t, "mvrvZscore": v} for d, t, v in rows]

    def test_run_writes_zarr(self, tmp_path: Path, requests_mock: Any) -> None:
        rows = [
            ("2024-01-01", 1704067200, 0.5),
            ("2024-01-02", 1704153600, 0.7),
            ("2024-01-03", 1704240000, 0.9),
        ]
        requests_mock.get(self.URL, json=self._payload(rows))
        d = DownloadMVRVZScore(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        zpath = tmp_path / "mvrv_zscore.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        assert cast(Any, grp["data"]).shape == (3, 1)
        assert list(cast(Any, grp.attrs["columns"])) == ["mvrv_zscore"]
        assert grp.attrs["provider"] == "bitcoin-data.com"
        assert grp.attrs["source"] == "bitcoin-data.com.api.v1.mvrv-zscore"
        assert list(cast(Any, grp["data"])[:, 0]) == [0.5, 0.7, 0.9]

    def test_empty_response_logs_warning(
        self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]
    ) -> None:
        requests_mock.get(self.URL, json=[])
        d = DownloadMVRVZScore(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "mvrv_zscore.zarr").exists()
        assert any("[empty]" in m and "mvrv_zscore" in m for m in loguru_capture)

    def test_skip_if_fresh(self, tmp_path: Path, requests_mock: Any) -> None:
        zpath = tmp_path / "mvrv_zscore.zarr"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        ts = np.array(
            [int(datetime.now(timezone.utc).timestamp() * 1000)], dtype=np.int64
        )
        vals = np.array([[1.0]], dtype=np.float64)
        grp = zarr.open_group(str(zpath), mode="w")
        grp.create_dataset("data", data=vals, shape=vals.shape, dtype="float64")
        grp.create_dataset("timestamps_ms", data=ts, shape=ts.shape, dtype="int64")
        grp.attrs.update({"columns": ["mvrv_zscore"]})

        # Would fail if called.
        requests_mock.get(self.URL, status_code=500)
        d = DownloadMVRVZScore(
            out_root=tmp_path, skip_if_fresh=True, freshness_tolerance_hours=48
        )
        d.run()
        assert requests_mock.call_count == 0

    def test_sorted_chronologically(self, tmp_path: Path, requests_mock: Any) -> None:
        """API may return rows out of order; output zarr MUST be ascending."""
        rows = [
            ("2024-01-03", 1704240000, 0.9),
            ("2024-01-01", 1704067200, 0.5),
            ("2024-01-02", 1704153600, 0.7),
        ]
        requests_mock.get(self.URL, json=self._payload(rows))
        d = DownloadMVRVZScore(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(str(tmp_path / "mvrv_zscore.zarr"), mode="r")
        ts = cast(Any, grp["timestamps_ms"])[:]
        assert ts[0] < ts[1] < ts[2]
        assert list(cast(Any, grp["data"])[:, 0]) == [0.5, 0.7, 0.9]

    def test_expandvars(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        d = DownloadMVRVZScore(out_root="${DATA_ROOT}/traidwind/macro")
        assert d.out_root == tmp_path / "traidwind" / "macro"
