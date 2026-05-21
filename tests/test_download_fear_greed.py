"""Tests for :class:`chainwind.download.DownloadFearGreed`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, cast

import numpy as np
import pytest
import zarr

from chainwind.download import DownloadFearGreed


class TestDownloadFearGreed:
    URL = "https://api.alternative.me/fng/"

    @staticmethod
    def _payload(values: List[tuple[int, int]]) -> dict:
        """Build a fake alternative.me /fng/ payload. ``values`` = list of
        (unix-seconds, fng-value) tuples in NEWEST-FIRST order (the API's
        actual convention)."""
        return {
            "name": "Fear and Greed Index",
            "data": [
                {
                    "value": str(v),
                    "value_classification": "Neutral",
                    "timestamp": str(t),
                    "time_until_update": "0",
                }
                for t, v in values
            ],
            "metadata": {"error": None},
        }

    def test_run_writes_zarr_in_chronological_order(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        # API returns newest-first; we must flip so the zarr is chronological.
        now = int(datetime.now(timezone.utc).timestamp())
        day = 86400
        # Newest-first payload: [today, yesterday, two-days-ago].
        requests_mock.get(
            self.URL,
            json=self._payload([(now, 70), (now - day, 60), (now - 2 * day, 55)]),
        )

        d = DownloadFearGreed(out_root=tmp_path, skip_if_fresh=False)
        d.run()

        zpath = tmp_path / "fear_greed.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        assert cast(Any, grp["data"]).shape == (3, 1)
        assert list(cast(Any, grp.attrs["columns"])) == ["value"]
        assert grp.attrs["source"] == "alternative.me.fng"
        assert grp.attrs["provider"] == "alternative.me"
        # Chronological: oldest first.
        ts = cast(Any, grp["timestamps_ms"])[:]
        assert ts[0] < ts[1] < ts[2]
        values = cast(Any, grp["data"])[:, 0]
        assert list(values) == [55.0, 60.0, 70.0]

    def test_lookback_days_forwarded_as_limit(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        requests_mock.get(self.URL, json=self._payload([(1700000000, 50)]))
        d = DownloadFearGreed(out_root=tmp_path, lookback_days=30, skip_if_fresh=False)
        d.run()
        assert requests_mock.last_request.qs.get("limit") == ["30"]

    def test_default_lookback_zero_means_all_history(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        requests_mock.get(self.URL, json=self._payload([(1700000000, 50)]))
        d = DownloadFearGreed(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert requests_mock.last_request.qs.get("limit") == ["0"]

    def test_skip_if_fresh(self, tmp_path: Path, requests_mock: Any) -> None:
        """Pre-existing fresh zarr ⇒ no HTTP call."""
        zpath = tmp_path / "fear_greed.zarr"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        ts = np.array(
            [int(datetime.now(timezone.utc).timestamp() * 1000)], dtype=np.int64
        )
        vals = np.array([[55.0]], dtype=np.float64)
        grp = zarr.open_group(str(zpath), mode="w")
        grp.create_dataset("data", data=vals, shape=vals.shape, dtype="float64")
        grp.create_dataset("timestamps_ms", data=ts, shape=ts.shape, dtype="int64")
        grp.attrs.update({"columns": ["value"]})

        # If the HTTP call fires the test fails (no mock registered = real network attempt).
        requests_mock.get(self.URL, status_code=500)

        d = DownloadFearGreed(
            out_root=tmp_path, skip_if_fresh=True, freshness_tolerance_hours=48
        )
        d.run()

        assert requests_mock.call_count == 0

    def test_empty_response_logs_warning(
        self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]
    ) -> None:
        requests_mock.get(
            self.URL, json={"name": "FNG", "data": [], "metadata": {"error": "none"}}
        )
        d = DownloadFearGreed(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "fear_greed.zarr").exists()
        assert any("[empty]" in m and "fear_greed" in m for m in loguru_capture)

    def test_negative_lookback_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="lookback_days"):
            DownloadFearGreed(out_root=tmp_path, lookback_days=-1)

    def test_expandvars_resolves_data_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        d = DownloadFearGreed(out_root="${DATA_ROOT}/traidwind/macro")
        assert d.out_root == tmp_path / "traidwind" / "macro"
