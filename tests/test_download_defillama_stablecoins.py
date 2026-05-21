"""Tests for :class:`chainwind.download.DownloadDeFiLlamaStablecoins`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, cast

import numpy as np
import pytest
import zarr

from chainwind.download import DownloadDeFiLlamaStablecoins


class TestDownloadDeFiLlamaStablecoins:
    URL = "https://stablecoins.llama.fi/stablecoincharts/all"

    @staticmethod
    def _payload(rows: List[tuple[int, float]]) -> List[dict]:
        """rows = list of (unix_seconds, peggedUSD_circulating_usd)."""
        return [
            {
                "date": str(ts),
                "totalCirculating": {"peggedUSD": v},
                "totalCirculatingUSD": {"peggedUSD": v},
            }
            for ts, v in rows
        ]

    def test_run_writes_zarr(self, tmp_path: Path, requests_mock: Any) -> None:
        rows = [(1700000000, 1.0e11), (1700086400, 1.05e11), (1700172800, 1.10e11)]
        requests_mock.get(self.URL, json=self._payload(rows))

        d = DownloadDeFiLlamaStablecoins(out_root=tmp_path, skip_if_fresh=False)
        d.run()

        zpath = tmp_path / "defillama" / "stablecoins_total.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        assert cast(Any, grp["data"]).shape == (3, 1)
        assert list(cast(Any, grp.attrs["columns"])) == ["circulating_usd"]
        assert grp.attrs["provider"] == "defillama"
        assert grp.attrs["source"] == "defillama.stablecoincharts.all"
        assert list(cast(Any, grp["data"])[:, 0]) == [1.0e11, 1.05e11, 1.10e11]

    def test_rows_without_peggedusd_are_skipped(self, tmp_path: Path, requests_mock: Any) -> None:
        """Some rows in DeFiLlama's history lack a peggedUSD entry (very
        early days before USD-pegged stablecoins existed). Drop them
        rather than coercing to NaN/0."""
        rows = [
            {"date": "1000000", "totalCirculatingUSD": {}},  # no peggedUSD
            {"date": "2000000", "totalCirculatingUSD": {"peggedUSD": 100.0}},
        ]
        requests_mock.get(self.URL, json=rows)
        d = DownloadDeFiLlamaStablecoins(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(str(tmp_path / "defillama" / "stablecoins_total.zarr"), mode="r")
        assert cast(Any, grp["data"]).shape == (1, 1)
        assert list(cast(Any, grp["data"])[:, 0]) == [100.0]

    def test_empty_response_logs_warning(self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]) -> None:
        requests_mock.get(self.URL, json=[])
        d = DownloadDeFiLlamaStablecoins(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "defillama" / "stablecoins_total.zarr").exists()
        assert any("[empty]" in m and "stablecoins_total" in m for m in loguru_capture)

    def test_skip_if_fresh(self, tmp_path: Path, requests_mock: Any) -> None:
        zpath = tmp_path / "defillama" / "stablecoins_total.zarr"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        ts = np.array([int(datetime.now(timezone.utc).timestamp() * 1000)], dtype=np.int64)
        vals = np.array([[100.0]], dtype=np.float64)
        grp = zarr.open_group(str(zpath), mode="w")
        grp.create_dataset("data", data=vals, shape=vals.shape, dtype="float64")
        grp.create_dataset("timestamps_ms", data=ts, shape=ts.shape, dtype="int64")
        grp.attrs.update({"columns": ["circulating_usd"]})

        # Would fail if called.
        requests_mock.get(self.URL, status_code=500)

        d = DownloadDeFiLlamaStablecoins(out_root=tmp_path, skip_if_fresh=True, freshness_tolerance_hours=48)
        d.run()
        assert requests_mock.call_count == 0

    def test_expandvars(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        d = DownloadDeFiLlamaStablecoins(out_root="${DATA_ROOT}/traidwind/macro")
        assert d.out_root == tmp_path / "traidwind" / "macro"
