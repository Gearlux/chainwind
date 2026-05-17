"""CoinGecko per-coin market-cap / price / volume downloader."""

import os
import time
from pathlib import Path
from typing import Any, List, Optional, Union

import confluid
import numpy as np
import pandas as pd
import zarr
from logflow import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# CoinGecko market-cap downloader (raw data for dominance computation)
# ---------------------------------------------------------------------------
# Three columns per coin: [market_cap, price, total_volume] — all returned by
# the same /coins/{id}/market_chart endpoint, so storing all three is free
# and lets future derived metrics (e.g. volume-weighted dominance) reuse the
# same zarr without re-downloading.
_COINGECKO_FREE_BASE_URL = "https://api.coingecko.com/api/v3"
_COINGECKO_PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
_COINGECKO_COLUMNS = ["market_cap", "price", "total_volume"]


@confluid.configurable
class DownloadCoinGeckoMarketCap:
    """Fetch per-coin market-cap / price / volume timeseries from CoinGecko.

    Each ``coin_id`` is persisted as ``<out_root>/coingecko/<coin_id>.zarr``
    with a 2-D ``(N, 3)`` data array of ``[market_cap, price, total_volume]``
    rows. Granularity is whatever CoinGecko returns for the requested
    ``days``: <=1 → 5-minute, 2-90 → hourly, 91-365 → daily, "max" → daily.

    Use this to build the raw inputs for :class:`traidwind.process.ComputeDominance` —
    download e.g. the top 20 coins by mcap, then compute BTC.D as
    ``btc_mcap / sum(top_20_mcaps)`` (within ~2% of the true value since
    the top 20 capture ~95-98% of total crypto mcap).

    Auth: optional. Without a key, hits the public Demo endpoint
    (``api.coingecko.com``) at ~30 calls/min. With ``COINGECKO_API_KEY``,
    uses the Pro endpoint (``pro-api.coingecko.com``) with higher limits.
    Register a free Demo key at https://www.coingecko.com/en/api/pricing.

    Args:
        coin_ids: List of CoinGecko coin IDs (e.g. ``"bitcoin"``,
            ``"ethereum"``, ``"tether"``). Use ``GET /coins/list`` to
            enumerate available IDs.
        out_root: Directory under which ``coingecko/<coin_id>.zarr``
            is written. ``$VAR`` / ``${VAR}`` / ``~`` are expanded.
        days: ``"max"`` (default) or an int. CoinGecko free-tier caps
            ``days=max`` at daily granularity, which is fine for dominance.
        vs_currency: Quote currency (default ``"usd"``).
        skip_if_fresh: If True, skip a coin when its zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``.
        api_key: Optional explicit Demo key override.
    """

    def __init__(
        self,
        coin_ids: List[str],
        out_root: Union[str, Path],
        days: Union[int, str] = "max",
        vs_currency: str = "usd",
        skip_if_fresh: bool = True,
        freshness_tolerance_hours: int = 24,
        api_key: Optional[str] = None,
        rate_limit_seconds: float = 6.5,
        max_retries_on_429: int = 3,
    ) -> None:
        self.coin_ids = coin_ids
        self.out_root = _expand(out_root)
        self.days = days
        self.vs_currency = vs_currency
        self.skip_if_fresh = skip_if_fresh
        self.freshness_tolerance_hours = freshness_tolerance_hours
        # Demo key is optional; without it we use the public endpoint.
        self._api_key = api_key or os.environ.get("COINGECKO_API_KEY")
        # CoinGecko's anonymous tier is throttled to ~10 calls/min;
        # ~6.5 s pacing stays under. With a Demo key, drop to 0.
        self.rate_limit_seconds = 0.0 if self._api_key else rate_limit_seconds
        self.max_retries_on_429 = max_retries_on_429

    def run(self) -> None:
        import requests

        session = requests.Session()
        if self._api_key:
            session.headers.update({"x-cg-demo-api-key": self._api_key})
        base = _COINGECKO_PRO_BASE_URL if self._api_key else _COINGECKO_FREE_BASE_URL
        try:
            for i, coin_id in enumerate(self.coin_ids):
                if i > 0 and self.rate_limit_seconds > 0:
                    time.sleep(self.rate_limit_seconds)
                self._fetch_one(session, base, coin_id)
        finally:
            session.close()

    def _fetch_one(self, session: Any, base_url: str, coin_id: str) -> None:
        zpath = self.out_root / "coingecko" / f"{coin_id}.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] {coin_id} - zarr already fresh at {zpath}")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        params = {"vs_currency": self.vs_currency, "days": str(self.days)}
        url = f"{base_url}/coins/{coin_id}/market_chart"
        # Manual 429-with-Retry-After retry. urllib3.Retry would technically
        # work but doesn't honor Retry-After for arbitrary 429s without
        # extra config — explicit loop is clearer for the rate-limit story.
        resp = None
        for attempt in range(self.max_retries_on_429 + 1):
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code != 429:
                break
            if attempt == self.max_retries_on_429:
                break  # let raise_for_status below surface the final 429
            wait_s = int(resp.headers.get("Retry-After", "60"))
            logger.warning(f"[429] {coin_id} rate-limited; waiting {wait_s}s (attempt {attempt + 1})")
            time.sleep(wait_s)
        assert resp is not None  # loop body always executes ≥ once
        resp.raise_for_status()
        payload = resp.json()
        mcaps = payload.get("market_caps", [])
        prices = payload.get("prices", [])
        volumes = payload.get("total_volumes", [])
        if not mcaps:
            logger.warning(f"[empty] {coin_id} - CoinGecko returned no market-cap history")
            return
        # Each list is [[ts_ms, value], ...]. Join on timestamp; CG aligns
        # them so the lists are the same length, but guard anyway.
        n = min(len(mcaps), len(prices), len(volumes))
        rows = [[int(mcaps[i][0]), float(mcaps[i][1]), float(prices[i][1]), float(volumes[i][1])] for i in range(n)]
        df = pd.DataFrame(rows, columns=["timestamp_ms", "market_cap", "price", "total_volume"])
        df = df.drop_duplicates(subset="timestamp_ms").sort_values("timestamp_ms").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        self._write_zarr(zpath, df, coin_id)
        logger.info(f"[wrote] {len(df)} {coin_id} mcap/price/volume rows -> {zpath}")

    @staticmethod
    def _write_zarr(zpath: Path, df: pd.DataFrame, coin_id: str) -> None:
        data = df[_COINGECKO_COLUMNS].to_numpy(dtype=np.float64)
        ts_ms = df["timestamp_ms"].to_numpy(dtype=np.int64)
        root = zarr.open_group(str(zpath), mode="w")
        root.create_dataset(
            "data",
            data=data,
            shape=data.shape,
            chunks=(min(4096, data.shape[0]), 3),
            dtype="float64",
        )
        root.create_dataset(
            "timestamps_ms",
            data=ts_ms,
            shape=ts_ms.shape,
            chunks=(min(4096, ts_ms.shape[0]),),
            dtype="int64",
        )
        root.attrs.update(
            {
                "provider": "coingecko",
                "coin_id": coin_id,
                "columns": _COINGECKO_COLUMNS,
                "start": df["date"].iloc[0].isoformat(),
                "end": df["date"].iloc[-1].isoformat(),
                "source": f"coingecko.coins.{coin_id}.market_chart",
            }
        )
