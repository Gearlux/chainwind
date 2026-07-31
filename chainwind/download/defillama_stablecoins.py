"""DeFiLlama total USD-pegged stablecoin circulating-supply downloader."""

from pathlib import Path
from typing import Union

import confluid
import numpy as np
import pandas as pd
import zarr
from loggair import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# DeFiLlama stablecoin supply (raw input for Stablecoin Supply Ratio)
# ---------------------------------------------------------------------------
# DeFiLlama exposes daily total stablecoin circulating supply broken down by
# peg currency (peggedUSD, peggedEUR, peggedJPY, …). For SSR-style
# computations the USD-pegged total is by far dominant (~99% of all
# stablecoins are USD-pegged) and matches the conventional definition.
_DEFILLAMA_STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
_DEFILLAMA_STABLECOIN_COLUMNS = ["circulating_usd"]


@confluid.configurable
class DownloadDeFiLlamaStablecoins:
    """Fetch the daily total USD-pegged stablecoin circulating supply from DeFiLlama.

    Stored at ``<out_root>/defillama/stablecoins_total.zarr`` with a 2-D
    ``(N, 1)`` data array of ``[circulating_usd]`` rows. This is the
    raw input for the Stablecoin Supply Ratio: SSR = BTC mcap /
    stablecoin total — a "dry powder" indicator. High SSR = BTC expensive
    relative to dry-powder stables (potential top); low SSR = lots of
    stables waiting to buy (potential bottom).

    No authentication required. DeFiLlama's stablecoins API is public.

    Args:
        out_root: Directory under which ``defillama/stablecoins_total.zarr``
            is written. ``$VAR`` / ``${VAR}`` / ``~`` are expanded.
        skip_if_fresh: If True, skip the fetch when the zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``. The
            DeFiLlama series is daily; the default 24 h means "always
            refresh at least once a day".
    """

    def __init__(
        self,
        out_root: Union[str, Path],
        skip_if_fresh: bool = True,
        freshness_tolerance_hours: int = 24,
    ) -> None:
        self.out_root = _expand(out_root)
        self.skip_if_fresh = skip_if_fresh
        self.freshness_tolerance_hours = freshness_tolerance_hours

    def run(self) -> None:
        import requests

        zpath = self.out_root / "defillama" / "stablecoins_total.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] stablecoins_total - zarr already fresh at {zpath}")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(_DEFILLAMA_STABLECOINS_URL, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            logger.warning("[empty] stablecoins_total - DeFiLlama returned no records")
            return
        # API rows: {"date": "<unix_seconds_str>",
        #            "totalCirculating": {"peggedUSD": N, ...},
        #            "totalCirculatingUSD": {"peggedUSD": N, ...},
        #            ...}.
        # We want totalCirculatingUSD.peggedUSD (USD-pegged supply, valued
        # in USD). Older rows only have peggedUSD; newer ones add EUR/JPY/etc.
        rows = []
        for entry in payload:
            usd_circ = entry.get("totalCirculatingUSD", {}).get("peggedUSD")
            if usd_circ is None:
                continue
            ts_ms = int(entry["date"]) * 1000
            rows.append([ts_ms, float(usd_circ)])
        if not rows:
            logger.warning("[empty] stablecoins_total - no peggedUSD rows in response")
            return
        rows.sort(key=lambda r: r[0])
        df = pd.DataFrame(rows, columns=["timestamp_ms", "circulating_usd"])
        df = df.drop_duplicates(subset="timestamp_ms").sort_values("timestamp_ms").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        self._write_zarr(zpath, df)
        logger.info(f"[wrote] {len(df)} stablecoin daily records -> {zpath}")

    @staticmethod
    def _write_zarr(zpath: Path, df: pd.DataFrame) -> None:
        values = df[_DEFILLAMA_STABLECOIN_COLUMNS].to_numpy(dtype=np.float64)
        ts_ms = df["timestamp_ms"].to_numpy(dtype=np.int64)
        root = zarr.open_group(str(zpath), mode="w")
        root.create_array("data", data=values, chunks=(min(4096, values.shape[0]), 1))
        root.create_array("timestamps_ms", data=ts_ms, chunks=(min(4096, ts_ms.shape[0]),))
        root.attrs.update(
            {
                "provider": "defillama",
                "metric": "total_stablecoin_circulating_usd",
                "columns": _DEFILLAMA_STABLECOIN_COLUMNS,
                "start": df["date"].iloc[0].isoformat(),
                "stop": df["date"].iloc[-1].isoformat(),
                "source": "defillama.stablecoincharts.all",
            }
        )
