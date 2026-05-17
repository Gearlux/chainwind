"""Chainwind download ops — fetch crypto-specific data from coin/website APIs into Zarr.

These were originally part of ``traidwind.download``; they migrated here because traidwind is
meant to be market-agnostic (CCXT exchange-API + Freqtrade plumbing) while crypto-coin /
sentiment / on-chain sources belong with the crypto-specific tools.

Naming mirrors :mod:`traidwind.download`: each downloader is ``Download<Source>``, lives in
``download/<source>.py``, writes to ``<out_root>/<source>/<name>.zarr`` with a 2-D ``(N, K)``
data array plus a parallel ``timestamps_ms`` array.
"""

from chainwind.download.coingecko_market_cap import DownloadCoinGeckoMarketCap
from chainwind.download.defillama_stablecoins import DownloadDeFiLlamaStablecoins
from chainwind.download.farside_etf_flows import DownloadFarsideETFFlows
from chainwind.download.fear_greed import DownloadFearGreed
from chainwind.download.mvrv_z_score import DownloadMVRVZScore

__all__ = [
    "DownloadCoinGeckoMarketCap",
    "DownloadDeFiLlamaStablecoins",
    "DownloadFarsideETFFlows",
    "DownloadFearGreed",
    "DownloadMVRVZScore",
]
