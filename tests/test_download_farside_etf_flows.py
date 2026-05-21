"""Tests for :class:`chainwind.download.DownloadFarsideETFFlows`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, cast

import numpy as np
import pytest
import zarr

from chainwind.download import DownloadFarsideETFFlows


def _farside_html_fixture(rows: List[List[str]]) -> str:
    """Minimal HTML mirroring Farside's layout: nav table + flow table + footer."""
    body = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>"
        for r in rows
    )
    return f"""
    <html><body>
    <table><tr><td>Nav</td></tr></table>
    <table>
      <thead><tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    <table><tr><td>Footer</td></tr></table>
    </body></html>
    """


class TestDownloadFarsideETFFlows:
    URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"

    def test_run_writes_zarr_and_filters_summary_rows(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        rows = [
            ["11 Jan 2024", "111.7", "227.0", "338.7"],
            ["12 Jan 2024", "386.0", "195.3", "581.3"],
            ["15 Jan 2024", "(95.0)", "150.0", "55.0"],  # parens = negative
            # Summary rows that MUST be filtered out:
            ["Average", "100.0", "150.0", "250.0"],
            ["Maximum", "500.0", "400.0", "900.0"],
            ["Minimum", "(200.0)", "(50.0)", "(250.0)"],
        ]
        requests_mock.get(self.URL, text=_farside_html_fixture(rows))
        d = DownloadFarsideETFFlows(out_root=tmp_path, skip_if_fresh=False)
        d.run()

        zpath = tmp_path / "farside" / "bitcoin_etf_flows.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        # 3 dated rows; summary rows dropped.
        assert cast(Any, grp["data"]).shape == (3, 3)
        assert list(cast(Any, grp.attrs["columns"])) == ["IBIT", "FBTC", "Total"]
        assert grp.attrs["provider"] == "farside.co.uk"
        assert grp.attrs["source"] == "farside.bitcoin-etf-flow-all-data"
        # Negative parens parsed correctly.
        ibit = cast(Any, grp["data"])[:, 0]
        assert list(ibit) == [111.7, 386.0, -95.0]

    def test_user_agent_header_sent(self, tmp_path: Path, requests_mock: Any) -> None:
        """Farside Cloudflare blocks default UAs; class MUST send a real-browser UA."""
        requests_mock.get(
            self.URL, text=_farside_html_fixture([["11 Jan 2024", "100", "100", "200"]])
        )
        d = DownloadFarsideETFFlows(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        ua = requests_mock.last_request.headers.get("User-Agent")
        assert ua is not None
        assert "Mozilla/5.0" in ua

    def test_missing_etf_dash_becomes_zero(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        """Farside uses '-' for 'ETF didn't exist yet'. Coerce to 0.0 (not NaN)."""
        rows = [["11 Jan 2024", "100", "-", "100"]]
        requests_mock.get(self.URL, text=_farside_html_fixture(rows))
        d = DownloadFarsideETFFlows(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(
            str(tmp_path / "farside" / "bitcoin_etf_flows.zarr"), mode="r"
        )
        fbtc = cast(Any, grp["data"])[:, 1]
        assert list(fbtc) == [0.0]

    def test_empty_table_logs_warning(
        self, tmp_path: Path, requests_mock: Any, loguru_capture: List[str]
    ) -> None:
        requests_mock.get(
            self.URL, text=_farside_html_fixture([["Average", "1", "1", "2"]])
        )
        d = DownloadFarsideETFFlows(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "farside" / "bitcoin_etf_flows.zarr").exists()
        assert any("[empty]" in m and "bitcoin_etf_flows" in m for m in loguru_capture)

    def test_skip_if_fresh(self, tmp_path: Path, requests_mock: Any) -> None:
        zpath = tmp_path / "farside" / "bitcoin_etf_flows.zarr"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        ts = np.array(
            [int(datetime.now(timezone.utc).timestamp() * 1000)], dtype=np.int64
        )
        vals = np.array([[100.0, 200.0, 300.0]], dtype=np.float64)
        grp = zarr.open_group(str(zpath), mode="w")
        grp.create_dataset("data", data=vals, shape=vals.shape, dtype="float64")
        grp.create_dataset("timestamps_ms", data=ts, shape=ts.shape, dtype="int64")
        grp.attrs.update({"columns": ["IBIT", "FBTC", "Total"]})

        requests_mock.get(self.URL, status_code=500)  # fail if called
        d = DownloadFarsideETFFlows(
            out_root=tmp_path, skip_if_fresh=True, freshness_tolerance_hours=48
        )
        d.run()
        assert requests_mock.call_count == 0

    def test_rows_sorted_chronologically(
        self, tmp_path: Path, requests_mock: Any
    ) -> None:
        """Out-of-order input rows → output zarr ascending by date."""
        rows = [
            ["15 Jan 2024", "50", "50", "100"],
            ["11 Jan 2024", "10", "10", "20"],
            ["12 Jan 2024", "20", "20", "40"],
        ]
        requests_mock.get(self.URL, text=_farside_html_fixture(rows))
        d = DownloadFarsideETFFlows(out_root=tmp_path, skip_if_fresh=False)
        d.run()
        grp = zarr.open_group(
            str(tmp_path / "farside" / "bitcoin_etf_flows.zarr"), mode="r"
        )
        ts = cast(Any, grp["timestamps_ms"])[:]
        assert ts[0] < ts[1] < ts[2]
        assert list(cast(Any, grp["data"])[:, 0]) == [10.0, 20.0, 50.0]

    def test_expandvars(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        d = DownloadFarsideETFFlows(out_root="${DATA_ROOT}/traidwind/macro")
        assert d.out_root == tmp_path / "traidwind" / "macro"
