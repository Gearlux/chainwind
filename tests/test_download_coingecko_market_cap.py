"""Tests for :class:`chainwind.download.DownloadCoinGeckoMarketCap`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, cast

import pytest
import zarr

from chainwind.download import DownloadCoinGeckoMarketCap


class TestDownloadCoinGeckoMarketCap:
    FREE_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    PRO_URL = "https://pro-api.coingecko.com/api/v3/coins/bitcoin/market_chart"

    @staticmethod
    def _payload(rows: List[tuple[int, float, float, float]]) -> dict:
        """rows = list of (ts_ms, market_cap, price, total_volume)."""
        return {
            "prices": [[r[0], r[2]] for r in rows],
            "market_caps": [[r[0], r[1]] for r in rows],
            "total_volumes": [[r[0], r[3]] for r in rows],
        }

    def test_run_writes_zarr_per_coin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any
    ) -> None:
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        rows = [
            (1700000000000, 1.0e12, 50000.0, 30e9),
            (1700086400000, 1.1e12, 55000.0, 32e9),
            (1700172800000, 1.05e12, 52500.0, 28e9),
        ]
        requests_mock.get(self.FREE_URL, json=self._payload(rows))

        d = DownloadCoinGeckoMarketCap(coin_ids=["bitcoin"], out_root=tmp_path, days=30, skip_if_fresh=False)
        d.run()

        zpath = tmp_path / "coingecko" / "bitcoin.zarr"
        assert zpath.exists()
        grp = zarr.open_group(str(zpath), mode="r")
        assert cast(Any, grp["data"]).shape == (3, 3)
        assert list(cast(Any, grp.attrs["columns"])) == [
            "market_cap",
            "price",
            "total_volume",
        ]
        assert grp.attrs["coin_id"] == "bitcoin"
        assert grp.attrs["provider"] == "coingecko"
        assert list(cast(Any, grp["data"])[:, 0]) == [1.0e12, 1.1e12, 1.05e12]

    def test_uses_free_endpoint_without_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any
    ) -> None:
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        requests_mock.get(self.FREE_URL, json=self._payload([(1, 100.0, 1.0, 10.0)]))
        d = DownloadCoinGeckoMarketCap(coin_ids=["bitcoin"], out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert requests_mock.call_count == 1
        assert "x-cg-demo-api-key" not in requests_mock.last_request.headers

    def test_uses_pro_endpoint_with_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any
    ) -> None:
        monkeypatch.setenv("COINGECKO_API_KEY", "demo-key-xyz")
        requests_mock.get(self.PRO_URL, json=self._payload([(1, 100.0, 1.0, 10.0)]))
        d = DownloadCoinGeckoMarketCap(coin_ids=["bitcoin"], out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert requests_mock.last_request.headers.get("x-cg-demo-api-key") == "demo-key-xyz"

    def test_empty_response_logs_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        requests_mock: Any,
        loguru_capture: List[str],
    ) -> None:
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        requests_mock.get(self.FREE_URL, json={"prices": [], "market_caps": [], "total_volumes": []})
        d = DownloadCoinGeckoMarketCap(coin_ids=["bitcoin"], out_root=tmp_path, skip_if_fresh=False)
        d.run()
        assert not (tmp_path / "coingecko" / "bitcoin.zarr").exists()
        assert any("[empty]" in m and "bitcoin" in m for m in loguru_capture)

    def test_429_retried_with_retry_after_header(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any
    ) -> None:
        """First response 429 + Retry-After: 0; second succeeds. The class
        must retry honoring the header, not just bubble the error."""
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        # requests_mock supports a `response_list` for sequential responses.
        requests_mock.get(
            self.FREE_URL,
            [
                {"status_code": 429, "headers": {"Retry-After": "0"}, "json": {}},
                {"status_code": 200, "json": self._payload([(1, 100.0, 1.0, 10.0)])},
            ],
        )
        d = DownloadCoinGeckoMarketCap(
            coin_ids=["bitcoin"],
            out_root=tmp_path,
            skip_if_fresh=False,
            rate_limit_seconds=0,  # speed up the test
            max_retries_on_429=3,
        )
        d.run()
        assert (tmp_path / "coingecko" / "bitcoin.zarr").exists()
        assert requests_mock.call_count == 2

    def test_429_exhausts_retries_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any
    ) -> None:
        """Every attempt 429s → final raise_for_status surfaces it."""
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        requests_mock.get(self.FREE_URL, status_code=429, headers={"Retry-After": "0"})
        d = DownloadCoinGeckoMarketCap(
            coin_ids=["bitcoin"],
            out_root=tmp_path,
            skip_if_fresh=False,
            rate_limit_seconds=0,
            max_retries_on_429=2,
        )
        import requests as _requests

        with pytest.raises(_requests.HTTPError):
            d.run()
        # 1 initial + 2 retries.
        assert requests_mock.call_count == 3

    def test_days_param_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requests_mock: Any) -> None:
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        requests_mock.get(self.FREE_URL, json=self._payload([(1, 1.0, 1.0, 1.0)]))
        d = DownloadCoinGeckoMarketCap(
            coin_ids=["bitcoin"],
            out_root=tmp_path,
            days=90,
            vs_currency="eur",
            skip_if_fresh=False,
        )
        d.run()
        assert requests_mock.last_request.qs.get("days") == ["90"]
        assert requests_mock.last_request.qs.get("vs_currency") == ["eur"]

    def test_expandvars_resolves_data_root(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATA_ROOT", str(tmp_path))
        monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
        d = DownloadCoinGeckoMarketCap(coin_ids=["bitcoin"], out_root="${DATA_ROOT}/traidwind/macro")
        assert d.out_root == tmp_path / "traidwind" / "macro"
