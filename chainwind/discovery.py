"""Discover trackers from the on-disk zarr tree under ``$DATA_ROOT``.

The hand-curated :data:`chainwind.trackers.BUILTIN_TRACKERS` only knows about a handful of
datasets, but the workspace downloaders leave dozens on disk (OHLCV for many pairs across
spot/futures × timeframes, every CoinGecko coin, on-chain / sentiment / macro series, …).
:func:`discover_trackers` walks the known path conventions, reads each zarr's ``columns`` attr,
and emits a :class:`~chainwind.trackers.TrackerSpec` per dataset — so the catalog reflects what
is *actually downloaded* rather than a static list.

Each provider maps a path pattern to a label/group/chart kind and a ``downloader_factory`` (the
same ``@configurable`` downloaders the bulk configs use, narrowed to the one dataset) — or
``None`` for derived datasets (dominance / SSR / liquidations) that have no simple re-fetch, which
surface as **view-only**. Path↔identifier conventions are the inverse of the writers
(``traidwind.paths._zarr_path`` etc.), so discovery and the downloaders always agree.
"""

import re
from functools import partial
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

import zarr
from loggair import get_logger
from traidwind.paths import _expand

from chainwind.trackers import TrackerCategory, TrackerSpec

logger = get_logger(__name__)

# Preference order when picking the single line a non-OHLCV tracker charts.
_PRIMARY_COLUMN_PREFERENCE = (
    "price",
    "close",
    "value",
    "ratio",
    "dominance",
    "funding_rate",
    "mvrv",
    "Total",
)
_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def _slug(raw: str) -> str:
    """URL/path-safe id (keeps ``-``/``_``/``.``; collapses everything else to ``_``)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", raw)


def _read_columns(zpath: Path) -> List[str]:
    """Return the zarr's ``columns`` attr, or ``[]`` if unreadable."""
    try:
        grp = zarr.open_group(str(zpath), mode="r")
        return [str(c) for c in cast(Any, grp.attrs.get("columns", []))]
    except (KeyError, FileNotFoundError, ValueError, OSError):
        return []


def _primary_column(columns: Sequence[str]) -> str:
    for pref in _PRIMARY_COLUMN_PREFERENCE:
        if pref in columns:
            return pref
    return columns[0] if columns else "value"


def _template(base: Path, zpath: Path) -> str:
    """``${DATA_ROOT}/traidwind/<rel>`` so the spec matches curated paths + re-expands cleanly."""
    return "${DATA_ROOT}/traidwind/" + zpath.relative_to(base).as_posix()


def _line_spec(
    *,
    base: Path,
    zpath: Path,
    spec_id: str,
    label: str,
    group: str,
    category: TrackerCategory,
    downloader_factory: Optional[Any],
    unit: str = "",
    coin: Optional[str] = None,
    primary: Optional[str] = None,
) -> Optional[TrackerSpec]:
    cols = _read_columns(zpath)
    if not cols:
        return None
    col = primary if (primary and primary in cols) else _primary_column(cols)
    return TrackerSpec(
        id=spec_id,
        label=label,
        category=category,
        zarr_path=_template(base, zpath),
        value_columns=(col,),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=downloader_factory,
        coin=coin,
        unit=unit,
        group=group,
        description=f"{group} · column {col}",
    )


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _discover_ohlcv(base: Path) -> List[TrackerSpec]:
    """``ohlcv/<exchange>/<spot|futures>/<PAIR>-<tf>.zarr`` → candlestick trackers."""
    out: List[TrackerSpec] = []
    root = base / "ohlcv"
    if not root.is_dir():
        return out
    for market_type in ("spot", "futures"):  # skip the stray legacy market-type-less file
        for exch_dir in sorted(root.glob("*")):
            mt_dir = exch_dir / market_type
            if not mt_dir.is_dir():
                continue
            exchange = exch_dir.name
            for zpath in sorted(mt_dir.glob("*.zarr")):
                stem = zpath.name[: -len(".zarr")]
                if "-" not in stem:
                    continue
                pair_us, tf = stem.rsplit("-", 1)
                pair = pair_us.replace("_", "/", 1)  # inverse of _zarr_path's pair.replace('/','_')
                cols = _read_columns(zpath)
                out.append(
                    TrackerSpec(
                        id=_slug(f"ohlcv-{exchange}-{market_type}-{pair_us}-{tf}"),
                        label=f"{pair} {tf} ({exchange} {market_type})",
                        category="price",
                        zarr_path=_template(base, zpath),
                        value_columns=tuple(cols) if cols else _OHLCV_COLUMNS,
                        chart_lib="lightweight",
                        chart_type="candlestick",
                        downloader_factory=partial(_ohlcv_downloader, exchange, market_type, pair, tf),
                        unit="USD",
                        group=f"OHLCV {market_type}",
                        description=f"{exchange} {market_type} OHLCV candlesticks.",
                    )
                )
    return out


def _ohlcv_downloader(exchange: str, market_type: str, pair: str, timeframe: str) -> Any:
    from traidwind.download import DownloadOHLCV

    return DownloadOHLCV(
        exchange=exchange,
        market_type=market_type,
        pairs=[pair],
        timeframes=[timeframe],
        out_root="${DATA_ROOT}/traidwind/ohlcv",
    )


def _discover_coingecko(base: Path) -> List[TrackerSpec]:
    out: List[TrackerSpec] = []
    root = base / "macro" / "coingecko"
    for zpath in sorted(root.glob("*.zarr")) if root.is_dir() else []:
        coin = zpath.name[: -len(".zarr")]
        spec = _line_spec(
            base=base,
            zpath=zpath,
            spec_id=_slug(f"coingecko-{coin}"),
            label=f"{coin} price (CoinGecko)",
            group="Market cap / price",
            category="price",
            downloader_factory=lambda c=coin: _coingecko_downloader(c),
            unit="USD",
            primary="price",
        )
        if spec:
            out.append(spec)
    return out


def _coingecko_downloader(coin: str) -> Any:
    from chainwind.download import DownloadCoinGeckoMarketCap

    return DownloadCoinGeckoMarketCap(coin_ids=[coin], out_root="${DATA_ROOT}/traidwind/macro", days=365)


def _discover_coinmetrics(base: Path) -> List[TrackerSpec]:
    out: List[TrackerSpec] = []
    root = base / "macro" / "coinmetrics"
    for zpath in sorted(root.glob("*_mvrv.zarr")) if root.is_dir() else []:
        asset = zpath.name[: -len("_mvrv.zarr")]
        spec = _line_spec(
            base=base,
            zpath=zpath,
            spec_id=_slug(f"coinmetrics-{asset}"),
            label=f"{asset.upper()} MVRV ratio (CoinMetrics)",
            group="On-chain",
            category="indicator",
            downloader_factory=lambda a=asset: _coinmetrics_downloader(a),
            unit="ratio",
            primary="mvrv",
        )
        if spec:
            out.append(spec)
    return out


def _coinmetrics_downloader(asset: str) -> Any:
    from chainwind.download import DownloadCoinMetricsMVRV

    return DownloadCoinMetricsMVRV(asset=asset.upper(), out_root="${DATA_ROOT}/traidwind/macro")


def _discover_macro_singletons(base: Path) -> List[TrackerSpec]:
    """The fixed-name macro datasets, each with its own downloader."""
    out: List[TrackerSpec] = []
    specs = [
        ("macro/mvrv_zscore.zarr", "mvrv_zscore", "Bitcoin MVRV Z-Score", "On-chain", "score", _mvrv_downloader),
        ("macro/fear_greed.zarr", "fear_greed", "Crypto Fear & Greed", "Sentiment", "score", _fear_greed_downloader),
        (
            "macro/defillama/stablecoins_total.zarr",
            "defillama_stablecoins",
            "Stablecoin supply (DeFiLlama)",
            "Macro",
            "USD",
            _defillama_downloader,
        ),
        (
            "macro/farside/bitcoin_etf_flows.zarr",
            "farside_etf_flows",
            "Spot BTC ETF flows (Farside)",
            "Flows",
            "USD (M)",
            _farside_downloader,
        ),
    ]
    for rel, spec_id, label, group, unit, factory in specs:
        zpath = base / rel
        if not zpath.exists():
            continue
        spec = _line_spec(
            base=base,
            zpath=zpath,
            spec_id=spec_id,
            label=label,
            group=group,
            category="indicator",
            downloader_factory=factory,
            unit=unit,
        )
        if spec:
            out.append(spec)
    return out


def _mvrv_downloader() -> Any:
    from chainwind.download import DownloadMVRVZScore

    return DownloadMVRVZScore(out_root="${DATA_ROOT}/traidwind/macro")


def _fear_greed_downloader() -> Any:
    from chainwind.download import DownloadFearGreed

    return DownloadFearGreed(out_root="${DATA_ROOT}/traidwind/macro")


def _defillama_downloader() -> Any:
    from chainwind.download import DownloadDeFiLlamaStablecoins

    return DownloadDeFiLlamaStablecoins(out_root="${DATA_ROOT}/traidwind/macro")


def _farside_downloader() -> Any:
    from chainwind.download import DownloadFarsideETFFlows

    return DownloadFarsideETFFlows(out_root="${DATA_ROOT}/traidwind/macro")


def _discover_fred(base: Path) -> List[TrackerSpec]:
    out: List[TrackerSpec] = []
    root = base / "macro" / "fred"
    for zpath in sorted(root.glob("*.zarr")) if root.is_dir() else []:
        series = zpath.name[: -len(".zarr")]
        spec = _line_spec(
            base=base,
            zpath=zpath,
            spec_id=_slug(f"fred-{series}"),
            label=f"{series} (FRED)",
            group="Macro (FRED)",
            category="indicator",
            downloader_factory=lambda s=series: _fred_downloader(s),
        )
        if spec:
            out.append(spec)
    return out


def _fred_downloader(series: str) -> Any:
    from traidwind.download import DownloadFREDSeries

    return DownloadFREDSeries(series_ids=[series], out_root="${DATA_ROOT}/traidwind/macro")


def _discover_yfinance(base: Path) -> List[TrackerSpec]:
    out: List[TrackerSpec] = []
    root = base / "macro" / "yfinance"
    for zpath in sorted(root.glob("*.zarr")) if root.is_dir() else []:
        ticker = zpath.name[: -len(".zarr")]
        spec = _line_spec(
            base=base,
            zpath=zpath,
            spec_id=_slug(f"yfinance-{ticker}"),
            label=f"{ticker} (yfinance)",
            group="Macro (yfinance)",
            category="price",
            downloader_factory=lambda t=ticker: _yfinance_downloader(t),
            unit="USD",
        )
        if spec:
            out.append(spec)
    return out


def _yfinance_downloader(ticker: str) -> Any:
    from traidwind.download import DownloadYFinanceTickers

    return DownloadYFinanceTickers(tickers=[ticker], out_root="${DATA_ROOT}/traidwind/macro")


def _discover_funding(base: Path) -> List[TrackerSpec]:
    """``funding/<exchange>/futures/<PAIR>.zarr`` → funding-rate trackers."""
    out: List[TrackerSpec] = []
    root = base / "funding"
    if not root.is_dir():
        return out
    for exch_dir in sorted(root.glob("*")):
        fut_dir = exch_dir / "futures"
        if not fut_dir.is_dir():
            continue
        exchange = exch_dir.name
        for zpath in sorted(fut_dir.glob("*.zarr")):
            pair_us = zpath.name[: -len(".zarr")]
            pair = pair_us.replace("_", "/", 1)
            spec = _line_spec(
                base=base,
                zpath=zpath,
                spec_id=_slug(f"funding-{exchange}-{pair_us}"),
                label=f"{pair} funding ({exchange})",
                group="Funding",
                category="indicator",
                downloader_factory=lambda e=exchange, p=pair: _funding_downloader(e, p),
                primary="funding_rate",
            )
            if spec:
                out.append(spec)
    return out


def _funding_downloader(exchange: str, pair: str) -> Any:
    from traidwind.download import DownloadFundingRates

    return DownloadFundingRates(
        exchange=exchange, pairs=[pair], market_type="futures", out_root="${DATA_ROOT}/traidwind/funding"
    )


def _discover_view_only(base: Path) -> List[TrackerSpec]:
    """Derived / no-simple-downloader datasets — displayed + freshness, but not updatable."""
    out: List[TrackerSpec] = []
    families = [
        (base / "macro" / "dominance", "Derived", "dominance-"),
        (base / "macro" / "ratio", "Derived", "ratio-"),
        (base / "liquidations", "Liquidations", "liq-"),
    ]
    for root, group, prefix in families:
        if not root.is_dir():
            continue
        for zpath in sorted(root.rglob("*.zarr")):
            rel = zpath.relative_to(root).as_posix()[: -len(".zarr")]
            spec = _line_spec(
                base=base,
                zpath=zpath,
                spec_id=_slug(f"{prefix}{rel}"),
                label=f"{rel} ({group}, view-only)",
                group=group,
                category="indicator",
                downloader_factory=None,
            )
            if spec:
                out.append(spec)
    return out


_PROVIDERS = (
    _discover_ohlcv,
    _discover_coingecko,
    _discover_coinmetrics,
    _discover_macro_singletons,
    _discover_fred,
    _discover_yfinance,
    _discover_funding,
    _discover_view_only,
)


def discover_trackers() -> List[TrackerSpec]:
    """Walk ``$DATA_ROOT/traidwind`` and return one TrackerSpec per discovered zarr dataset.

    Returns an empty list (with a debug log) when ``$DATA_ROOT`` is unset or the tree is absent.
    """
    base = _expand("${DATA_ROOT}/traidwind")
    if not base.is_dir():
        logger.debug(f"[discovery] no traidwind data tree at {base}")
        return []
    found: List[TrackerSpec] = []
    for provider in _PROVIDERS:
        try:
            found.extend(provider(base))
        except OSError as exc:  # a flaky dir read shouldn't kill the whole catalog
            logger.warning(f"[discovery] {provider.__name__} failed: {exc}")
    logger.debug(f"[discovery] found {len(found)} datasets under {base}")
    return found
