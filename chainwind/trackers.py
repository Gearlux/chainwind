"""Tracker registry — :class:`TrackerSpec` and the builtin set the UI displays.

A *tracker* is one displayable time series: a price chart (BTC candlesticks) or an
indicator (the MVRV Z-Score). Each :class:`TrackerSpec` ties together three things the
display layer needs:

* **where the data lives** — a ``${DATA_ROOT}``-relative zarr path written by one of the
  existing ``@configurable`` downloaders (the layout is always a 2-D ``data`` array +
  1-D ``timestamps_ms`` + a ``columns`` attr);
* **how to (re)fetch it** — :attr:`downloader_factory`, a zero-arg closure returning the
  live downloader instance, reused verbatim by :mod:`chainwind.update` so a tracker's
  update path and its bulk ``config/download_*.yaml`` never drift on the params that matter;
* **how to draw it** — :attr:`chart_lib` / :attr:`chart_type` (the lightweight-charts vs
  ECharts split) plus optional value :attr:`zones` for indicator band shading.

This registry is the single source of truth for tracker metadata — UI code MUST read it
rather than inline tracker names/paths (mirrors :mod:`chainwind.coins`). New trackers extend
:data:`BUILTIN_TRACKERS`; the other three crypto downloaders (Fear & Greed, DeFiLlama,
Farside ETF) slot in the same way.
"""

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional, Tuple

from chainwind.download import DownloadCoinGeckoMarketCap, DownloadCoinMetricsMVRV, DownloadMVRVZScore

TrackerCategory = Literal["price", "indicator"]
ChartLib = Literal["lightweight", "echarts"]
ChartType = Literal["candlestick", "line"]


@dataclass(frozen=True)
class Zone:
    """A horizontal value band used to shade an indicator chart (ECharts ``markArea``).

    ``lo``/``hi`` are inclusive-ish y-axis bounds; ``None`` means open-ended (the renderer
    clamps to the axis min/max). Example for MVRV: ``Zone(6.0, None, "#e57373", "Cycle top")``.
    """

    lo: Optional[float]
    hi: Optional[float]
    color: str
    label: str


@dataclass(frozen=True)
class TrackerSpec:
    """Static metadata for one displayable tracker.

    Args:
        id: Canonical id used in URLs and the registry (``"btc_ohlcv"``).
        label: Human-facing title shown in the UI.
        category: ``"price"`` or ``"indicator"`` — drives default styling/grouping.
        zarr_path: ``${DATA_ROOT}``-relative path to the zarr group on disk. Expanded by
            :func:`chainwind.series` via ``traidwind.paths._expand``.
        value_columns: Which of the zarr's ``columns`` to surface to the chart. For OHLCV
            this is the full ``(open, high, low, close, volume)`` tuple; for a line it is a
            single column (``("price",)`` / ``("mvrv_zscore",)``).
        chart_lib: ``"lightweight"`` (TradingView, financial panes) or ``"echarts"``
            (general, value-zone shading + future gauges/bars).
        chart_type: ``"candlestick"`` or ``"line"``.
        downloader_factory: Zero-arg closure returning the live ``@configurable`` downloader
            that (re)writes :attr:`zarr_path`. Reused by :mod:`chainwind.update`. ``None`` marks
            the tracker **view-only** — it is displayed and its freshness reported, but it has no
            known updater (e.g. a derived dataset like dominance / SSR).
        zones: Optional value bands for indicator shading (ECharts only).
        coin: Linked :class:`chainwind.coins.CoinSpec` symbol when the tracker is coin-bound.
        unit: Display unit (``"USD"``, ``"score"``, …); free text for the UI axis label.
        description: One-line description shown in the UI / freshness table.
        group: Catalog grouping label for the UI sidebar (``"OHLCV spot"``, ``"On-chain"``, …).
            Set by disk discovery; empty for hand-curated featured specs.
        featured: True for the curated dashboard trackers (surfaced by :func:`list_trackers`).
    """

    id: str
    label: str
    category: TrackerCategory
    zarr_path: str
    value_columns: Tuple[str, ...]
    chart_lib: ChartLib
    chart_type: ChartType
    downloader_factory: Optional[Callable[[], Any]] = None
    zones: Tuple[Zone, ...] = ()
    coin: Optional[str] = None
    unit: str = ""
    description: str = ""
    group: str = ""
    featured: bool = False


def is_updatable(spec: "TrackerSpec") -> bool:
    """True when the tracker has a known downloader (not a view-only derived dataset)."""
    return spec.downloader_factory is not None


# ---------------------------------------------------------------------------
# Builtin trackers
# ---------------------------------------------------------------------------
# out_roots match the paths the data is ALREADY on disk at (see the
# config/download_*.yaml headers), so the first display reuses downloaded data and
# `chainwind update` rewrites in place. The downloaders do no work in __init__ —
# constructing them here is cheap; `${DATA_ROOT}` is expanded inside their ctors.

# MVRV cycle bands, per the canonical thresholds documented in
# config/download_mvrv_zscore.yaml (>6 top, 0-2 neutral, <0 accumulation).
_MVRV_ZONES: Tuple[Zone, ...] = (
    Zone(None, 0.0, "#66bb6a", "Accumulation (Z < 0)"),
    Zone(0.0, 2.0, "#90a4ae", "Neutral (0 ≤ Z < 2)"),
    Zone(2.0, 6.0, "#ffb74d", "Elevated (2 ≤ Z < 6)"),
    Zone(6.0, None, "#e57373", "Cycle top likely (Z ≥ 6)"),
)


def _btc_ohlcv_downloader() -> Any:
    # Imported lazily so a plain `import chainwind.trackers` doesn't pull traidwind's
    # download module (and its ccxt-adjacent imports) until an update is actually run.
    from traidwind.download import DownloadOHLCV

    return DownloadOHLCV(
        exchange="binance",
        market_type="spot",
        pairs=["BTC/USDT"],
        timeframes=["1d"],
        out_root="${DATA_ROOT}/traidwind/ohlcv",
    )


def _btc_price_downloader() -> Any:
    return DownloadCoinGeckoMarketCap(
        coin_ids=["bitcoin"],
        out_root="${DATA_ROOT}/traidwind/macro",
        days=365,
    )


def _mvrv_downloader() -> Any:
    return DownloadMVRVZScore(out_root="${DATA_ROOT}/traidwind/macro")


def _eth_mvrv_downloader() -> Any:
    # bitcoin-data.com is BTC-only; CoinMetrics' community API is the free
    # multi-asset MVRV source (BTC/ETH/ADA/...). NOT Solana — see the
    # DownloadCoinMetricsMVRV module docstring.
    return DownloadCoinMetricsMVRV(asset="ETH", out_root="${DATA_ROOT}/traidwind/macro")


BUILTIN_TRACKERS: Tuple[TrackerSpec, ...] = (
    TrackerSpec(
        id="btc_ohlcv",
        label="Bitcoin (BTC/USDT 1d)",
        category="price",
        zarr_path="${DATA_ROOT}/traidwind/ohlcv/binance/spot/BTC_USDT-1d.zarr",
        value_columns=("open", "high", "low", "close", "volume"),
        chart_lib="lightweight",
        chart_type="candlestick",
        downloader_factory=_btc_ohlcv_downloader,
        coin="BTC",
        unit="USD",
        description="Daily Binance spot OHLCV candlesticks.",
        group="OHLCV spot",
        featured=True,
    ),
    TrackerSpec(
        id="mvrv_zscore",
        label="Bitcoin MVRV Z-Score",
        category="indicator",
        zarr_path="${DATA_ROOT}/traidwind/macro/mvrv_zscore.zarr",
        value_columns=("mvrv_zscore",),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=_mvrv_downloader,
        zones=_MVRV_ZONES,
        coin="BTC",
        unit="score",
        description="On-chain cycle-overheating indicator (bitcoin-data.com).",
        group="On-chain",
        featured=True,
    ),
    TrackerSpec(
        id="eth_mvrv",
        label="Ethereum MVRV ratio (CoinMetrics)",
        category="indicator",
        zarr_path="${DATA_ROOT}/traidwind/macro/coinmetrics/eth_mvrv.zarr",
        # The zarr also carries a derived `mvrv_zscore` column, but its absolute
        # scale is provider-specific, so we chart the cross-coin-comparable
        # ratio and intentionally attach no zones (the BTC Z-Score bands do not
        # transfer — see DownloadCoinMetricsMVRV).
        value_columns=("mvrv",),
        chart_lib="echarts",
        chart_type="line",
        downloader_factory=_eth_mvrv_downloader,
        coin="ETH",
        unit="ratio",
        description="On-chain market-value / realized-value ratio (CoinMetrics community, free).",
        group="On-chain",
        featured=True,
    ),
    TrackerSpec(
        id="btc_price",
        label="Bitcoin price (CoinGecko daily)",
        category="price",
        zarr_path="${DATA_ROOT}/traidwind/macro/coingecko/bitcoin.zarr",
        value_columns=("price",),
        chart_lib="lightweight",
        chart_type="line",
        downloader_factory=_btc_price_downloader,
        coin="BTC",
        unit="USD",
        description="Daily USD price line from CoinGecko market_chart.",
        group="Market cap / price",
        featured=True,
    ),
)


def list_trackers() -> Tuple[TrackerSpec, ...]:
    """Return the builtin tracker registry as an immutable tuple."""
    return BUILTIN_TRACKERS


def get_tracker(tracker_id: str) -> TrackerSpec:
    """Look up a builtin (featured) tracker by id (case-insensitive)."""
    target = tracker_id.strip().lower()
    for tracker in BUILTIN_TRACKERS:
        if tracker.id == target:
            return tracker
    raise KeyError(f"Unknown tracker id {tracker_id!r}. Known: {[t.id for t in BUILTIN_TRACKERS]}")


def catalog() -> Tuple[TrackerSpec, ...]:
    """Full catalog of trackers: everything discovered on disk + curated featured specs.

    Disk discovery (:func:`chainwind.discovery.discover_trackers`) is the source of truth for
    what exists; the curated :data:`BUILTIN_TRACKERS` overlay supplies friendly ids, labels,
    value zones and ``featured=True`` for the datasets they describe (matched by ``zarr_path``).
    A curated tracker whose data isn't on disk yet is still listed (so it shows as *missing* with
    an Update affordance). Imported lazily to avoid a discovery⇄trackers import cycle.
    """
    from chainwind.discovery import discover_trackers

    merged: dict[str, TrackerSpec] = {}
    # Curated specs first so they win on a shared zarr_path (nicer id/label/zones/featured)
    # and curated-but-not-yet-downloaded datasets still appear.
    for spec in BUILTIN_TRACKERS:
        merged[spec.zarr_path] = spec
    for spec in discover_trackers():
        merged.setdefault(spec.zarr_path, spec)
    return tuple(merged.values())


def get_catalog_tracker(tracker_id: str) -> TrackerSpec:
    """Resolve a tracker id across the FULL catalog (featured + discovered)."""
    target = tracker_id.strip()
    for spec in catalog():
        if spec.id == target:
            return spec
    raise KeyError(f"Unknown tracker id {tracker_id!r}")
