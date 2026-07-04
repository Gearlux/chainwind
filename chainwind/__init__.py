"""Chainwind — crypto trackers & indicators viewer.

Extends :mod:`traidwind`'s market-agnostic visualization layer with:

- crypto-specific downloaders (CoinGecko, fear/greed, DeFiLlama, Farside ETF flows, MVRV Z-score),
- per-coin metadata (:class:`CoinSpec`) and a builtin registry,
- a tracker registry (:class:`TrackerSpec`) tying each displayable series to its on-disk zarr,
  its downloader, and its chart styling,
- update/freshness methods (:mod:`chainwind.update`) over the existing downloaders,
- a local FastAPI server (:mod:`chainwind.server`) serving a JSON API + a React SPA with a
  Bitcoin price (candlestick) panel and an MVRV Z-Score (zoned line) panel.

The FastAPI server requires the ``[http]`` extra (``fastapi`` + ``uvicorn``); the React UI is
built from ``chainwind/frontend`` into ``chainwind/frontend/dist``.
"""

__version__ = "0.1.0"

from chainwind.coins import BUILTIN_COINS, CoinSpec, get_coin, list_coins
from chainwind.discovery import discover_trackers
from chainwind.download import (
    DownloadCoinGeckoMarketCap,
    DownloadCoinMetricsMVRV,
    DownloadDeFiLlamaStablecoins,
    DownloadFarsideETFFlows,
    DownloadFearGreed,
    DownloadMVRVZScore,
)
from chainwind.series import read_primary_series, read_series, tracker_freshness, zones_payload
from chainwind.trackers import (
    BUILTIN_TRACKERS,
    TrackerSpec,
    Zone,
    catalog,
    get_catalog_tracker,
    get_tracker,
    is_updatable,
    list_trackers,
)
from chainwind.update import freshness_report, update_all, update_tracker

__all__ = [
    "CoinSpec",
    "BUILTIN_COINS",
    "get_coin",
    "list_coins",
    "DownloadCoinGeckoMarketCap",
    "DownloadCoinMetricsMVRV",
    "DownloadDeFiLlamaStablecoins",
    "DownloadFarsideETFFlows",
    "DownloadFearGreed",
    "DownloadMVRVZScore",
    "TrackerSpec",
    "Zone",
    "BUILTIN_TRACKERS",
    "get_tracker",
    "list_trackers",
    "catalog",
    "get_catalog_tracker",
    "is_updatable",
    "discover_trackers",
    "read_series",
    "read_primary_series",
    "tracker_freshness",
    "zones_payload",
    "update_tracker",
    "update_all",
    "freshness_report",
]
