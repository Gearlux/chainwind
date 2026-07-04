"""Tests for on-disk tracker discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from chainwind.discovery import discover_trackers
from chainwind.trackers import catalog, is_updatable
from tests.conftest import WriteZarr

_NOW = int(datetime.now(timezone.utc).timestamp() * 1000)
_OHLCV = ["open", "high", "low", "close", "volume"]


@pytest.fixture
def disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_zarr: WriteZarr) -> Path:
    """A tmp ``$DATA_ROOT`` seeded with one zarr per discovery family."""
    root = tmp_path
    tw = root / "traidwind"
    write_zarr(tw / "ohlcv/binance/spot/ETH_USDT-1d.zarr", [[1, 2, 0.5, 1.5, 9]], [_NOW], _OHLCV)
    write_zarr(tw / "ohlcv/binance/futures/BTC_USDT:USDT-1h.zarr", [[1, 2, 0.5, 1.5, 9]], [_NOW], _OHLCV)
    write_zarr(
        tw / "macro/coingecko/ethereum.zarr", [[1e9, 3000.0, 5e8]], [_NOW], ["market_cap", "price", "total_volume"]
    )
    write_zarr(tw / "macro/coinmetrics/btc_mvrv.zarr", [[2.5, 1.1]], [_NOW], ["mvrv", "mvrv_zscore"])
    write_zarr(tw / "macro/fred/WM2NS.zarr", [[21000.0]], [_NOW], ["value"])
    write_zarr(tw / "macro/yfinance/BTC-USD.zarr", [[1, 2, 0.5, 1.5, 9]], [_NOW], _OHLCV)
    write_zarr(tw / "macro/mvrv_zscore.zarr", [[1.2]], [_NOW], ["mvrv_zscore"])
    write_zarr(tw / "macro/fear_greed.zarr", [[55.0]], [_NOW], ["value"])
    write_zarr(tw / "macro/defillama/stablecoins_total.zarr", [[1.5e11]], [_NOW], ["circulating_usd"])
    write_zarr(tw / "macro/farside/bitcoin_etf_flows.zarr", [[10.0, 10.0]], [_NOW], ["IBIT", "Total"])
    write_zarr(tw / "funding/binance/futures/BTC_USDT:USDT.zarr", [[0.0001]], [_NOW], ["funding_rate"])
    write_zarr(tw / "macro/dominance/btc_dominance.zarr", [[55.0]], [_NOW], ["dominance"])
    write_zarr(tw / "macro/ratio/ssr.zarr", [[12.0]], [_NOW], ["ratio"])
    write_zarr(
        tw / "liquidations/coinalyze/BTCUSDT_PERP.A-daily.zarr", [[1.0, 2.0]], [_NOW], ["longvolume", "shortvolume"]
    )
    # The stray legacy market-type-less OHLCV file must be ignored.
    write_zarr(tw / "ohlcv/binance/BTC_USDT-1d.zarr", [[1, 2, 0.5, 1.5, 9]], [_NOW], _OHLCV)
    monkeypatch.setenv("DATA_ROOT", str(root))
    return root


def _by_id(specs: list) -> dict:
    return {s.id: s for s in specs}


def test_discovers_each_family(disk: Path) -> None:
    specs = _by_id(discover_trackers())
    assert "ohlcv-binance-spot-ETH_USDT-1d" in specs
    assert "coingecko-ethereum" in specs
    assert "fred-WM2NS" in specs
    assert "mvrv_zscore" in specs
    # futures pair keeps its settle suffix (slugified)
    assert any(i.startswith("ohlcv-binance-futures-BTC_USDT") for i in specs)


def test_ohlcv_spec_shape_and_factory(disk: Path) -> None:
    spec = _by_id(discover_trackers())["ohlcv-binance-spot-ETH_USDT-1d"]
    assert spec.chart_type == "candlestick"
    assert spec.chart_lib == "lightweight"
    assert spec.group == "OHLCV spot"
    assert spec.value_columns == tuple(_OHLCV)
    dl = spec.downloader_factory()  # type: ignore[misc]
    assert dl.pairs == ["ETH/USDT"] and dl.timeframes == ["1d"] and dl.market_type == "spot"


def test_futures_pair_reconstructed(disk: Path) -> None:
    spec = next(s for s in discover_trackers() if s.group == "OHLCV futures")
    dl = spec.downloader_factory()  # type: ignore[misc]
    assert dl.pairs == ["BTC/USDT:USDT"]
    assert dl.market_type == "futures"


def test_coingecko_primary_is_price(disk: Path) -> None:
    spec = _by_id(discover_trackers())["coingecko-ethereum"]
    assert spec.value_columns == ("price",)
    assert is_updatable(spec)


def test_dominance_is_view_only(disk: Path) -> None:
    spec = _by_id(discover_trackers())["dominance-btc_dominance"]
    assert spec.group == "Derived"
    assert not is_updatable(spec)
    assert spec.downloader_factory is None


def test_legacy_marketless_ohlcv_skipped(disk: Path) -> None:
    # Only spot/ and futures/ are walked — the bare ohlcv/binance/BTC_USDT-1d.zarr is ignored.
    specs = discover_trackers()
    assert all("binance-BTC_USDT-1d" not in s.id.replace("spot-", "").replace("futures-", "") for s in specs)
    assert not any(s.id == "ohlcv-binance--BTC_USDT-1d" for s in specs)


def test_catalog_merges_curated_overlay(disk: Path) -> None:
    # The featured mvrv_zscore (curated) supplies zones + featured flag on the discovered path.
    spec = next(s for s in catalog() if s.id == "mvrv_zscore")
    assert spec.featured is True
    assert len(spec.zones) == 4


def test_all_families_discovered(disk: Path) -> None:
    groups = {s.group for s in discover_trackers()}
    assert {
        "OHLCV spot",
        "OHLCV futures",
        "Market cap / price",
        "On-chain",
        "Macro (FRED)",
        "Macro (yfinance)",
        "Sentiment",
        "Macro",
        "Flows",
        "Funding",
        "Derived",
        "Liquidations",
    } <= groups


def test_every_updatable_factory_builds(disk: Path) -> None:
    # Exercises every per-family downloader builder (lazy imports + construction, no network).
    for spec in discover_trackers():
        if is_updatable(spec):
            assert spec.downloader_factory is not None
            dl = spec.downloader_factory()
            assert hasattr(dl, "run")


def test_funding_and_farside_specs(disk: Path) -> None:
    specs = _by_id(discover_trackers())
    funding = next(s for s in specs.values() if s.group == "Funding")
    assert funding.value_columns == ("funding_rate",)
    assert funding.downloader_factory().market_type == "futures"  # type: ignore[misc]
    farside = next(s for s in specs.values() if s.group == "Flows")
    assert farside.value_columns == ("Total",)  # primary-column preference picks Total


def test_liquidations_view_only(disk: Path) -> None:
    liq = next(s for s in discover_trackers() if s.group == "Liquidations")
    assert not is_updatable(liq)


def test_discovery_empty_without_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "nonexistent"))
    assert discover_trackers() == []
