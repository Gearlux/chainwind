"""Tests for :class:`chainwind.download.DownloadCoinMetricsMVRV`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple, cast

import numpy as np
import pytest
import zarr

from chainwind.download import DownloadCoinMetricsMVRV

URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


def _payload(rows: List[Tuple[str, float, float]], asset: str = "eth") -> dict:
    """rows = list of (time_iso, mvrv_ratio, market_cap)."""
    return {
        "data": [
            {"asset": asset, "time": t, "CapMVRVCur": str(ratio), "CapMrktCurUSD": str(mcap)} for t, ratio, mcap in rows
        ]
    }


def _expected_zscore(ratios: np.ndarray, mcaps: np.ndarray) -> np.ndarray:
    realized = mcaps / ratios
    sigma = float(np.std(mcaps, ddof=0))
    return cast(np.ndarray, (mcaps - realized) / sigma)


class TestDownloadCoinMetricsMVRV:
    def test_run_writes_two_columns(self, tmp_path: Path, requests_mock: Any) -> None:
        rows = [
            ("2024-01-01T00:00:00.000000000Z", 1.5, 8.0e11),
            ("2024-01-02T00:00:00.000000000Z", 1.8, 9.0e11),
            ("2024-01-03T00:00:00.000000000Z", 2.1, 1.1e12),
        ]
        requests_mock.get(URL, json=_payload(rows))
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=False)
        d.run()

        zpath = tmp_path / "coinmetrics" / "eth_mvrv.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        assert cast(Any, grp["data"]).shape == (3, 2)
        assert list(cast(Any, grp.attrs["columns"])) == ["mvrv", "mvrv_zscore"]
        assert grp.attrs["provider"] == "coinmetrics"
        assert grp.attrs["asset"] == "eth"

        data = cast(Any, grp["data"])[:]
        ratios = np.array([1.5, 1.8, 2.1])
        mcaps = np.array([8.0e11, 9.0e11, 1.1e12])
        np.testing.assert_allclose(data[:, 0], ratios)
        np.testing.assert_allclose(data[:, 1], _expected_zscore(ratios, mcaps), rtol=1e-9)

    def test_unsupported_asset_logs_warning(
        self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]
    ) -> None:
        requests_mock.get(
            URL,
            status_code=400,
            json={"error": {"type": "bad_parameter", "message": "not supported for asset 'sol'"}},
        )
        d = DownloadCoinMetricsMVRV(asset="SOL", out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "coinmetrics" / "sol_mvrv.zarr").exists()
        assert any("[unsupported]" in m and "sol_mvrv" in m for m in loguru_capture)

    def test_empty_response_logs_warning(self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]) -> None:
        requests_mock.get(URL, json={"data": []})
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "coinmetrics" / "eth_mvrv.zarr").exists()
        assert any("[empty]" in m and "eth_mvrv" in m for m in loguru_capture)

    def test_rows_missing_a_metric_are_skipped(self, tmp_path: Path, requests_mock: Any) -> None:
        """A timestamp with only the ratio (no market cap) must be dropped."""
        payload = {
            "data": [
                {
                    "asset": "eth",
                    "time": "2024-01-01T00:00:00.000000000Z",
                    "CapMVRVCur": "1.5",
                    "CapMrktCurUSD": "8e11",
                },
                {"asset": "eth", "time": "2024-01-02T00:00:00.000000000Z", "CapMVRVCur": "1.8"},  # no mcap
                {
                    "asset": "eth",
                    "time": "2024-01-03T00:00:00.000000000Z",
                    "CapMVRVCur": "2.1",
                    "CapMrktCurUSD": "1.1e12",
                },
            ]
        }
        requests_mock.get(URL, json=payload)
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(str(tmp_path / "coinmetrics" / "eth_mvrv.zarr"), mode="r")
        assert cast(Any, grp["data"]).shape == (2, 2)

    def test_sorted_chronologically(self, tmp_path: Path, requests_mock: Any) -> None:
        rows = [
            ("2024-01-03T00:00:00.000000000Z", 2.1, 1.1e12),
            ("2024-01-01T00:00:00.000000000Z", 1.5, 8.0e11),
            ("2024-01-02T00:00:00.000000000Z", 1.8, 9.0e11),
        ]
        requests_mock.get(URL, json=_payload(rows))
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(str(tmp_path / "coinmetrics" / "eth_mvrv.zarr"), mode="r")
        ts = cast(Any, grp["timestamps_ms"])[:]
        assert ts[0] < ts[1] < ts[2]
        np.testing.assert_allclose(cast(Any, grp["data"])[:, 0], [1.5, 1.8, 2.1])

    def test_pagination_follows_next_page_url(self, tmp_path: Path, requests_mock: Any) -> None:
        page2 = f"{URL}?page_token=PAGE2"
        requests_mock.get(
            URL,
            json={
                "data": _payload([("2024-01-01T00:00:00.000000000Z", 1.5, 8.0e11)])["data"],
                "next_page_url": page2,
            },
        )
        requests_mock.get(
            page2,
            json={"data": _payload([("2024-01-02T00:00:00.000000000Z", 1.8, 9.0e11)])["data"]},
        )
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(str(tmp_path / "coinmetrics" / "eth_mvrv.zarr"), mode="r")
        assert cast(Any, grp["data"]).shape == (2, 2)

    def test_skip_if_fresh(self, tmp_path: Path, requests_mock: Any) -> None:
        zpath = tmp_path / "coinmetrics" / "eth_mvrv.zarr"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        ts = np.array([int(datetime.now(timezone.utc).timestamp() * 1000)], dtype=np.int64)
        vals = np.array([[1.5, 0.3]], dtype=np.float64)
        grp = zarr.open_group(str(zpath), mode="w")
        grp.create_array("data", data=vals)
        grp.create_array("timestamps_ms", data=ts)
        grp.attrs.update({"columns": ["mvrv", "mvrv_zscore"]})

        requests_mock.get(URL, status_code=500)  # would fail if called
        d = DownloadCoinMetricsMVRV(asset="ETH", out_root=tmp_path, skip_if_fresh=True, freshness_tolerance_hours=48)
        d.run()
        assert requests_mock.call_count == 0

    def test_asset_id_and_expandvars(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        d = DownloadCoinMetricsMVRV(asset="Eth", out_root="${DATA_ROOT}/traidwind/macro")
        assert d.asset_id == "eth"
        assert d.out_root == tmp_path / "traidwind" / "macro"

    def test_default_asset_is_btc(self) -> None:
        assert DownloadCoinMetricsMVRV().asset_id == "btc"
