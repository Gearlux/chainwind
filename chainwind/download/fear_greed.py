"""alternative.me Crypto Fear & Greed Index downloader."""

from pathlib import Path
from typing import Union

import confluid
import numpy as np
import pandas as pd
import zarr
from logflow import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# alternative.me Fear & Greed Index
# ---------------------------------------------------------------------------
# Single-series daily macro indicator (0-100). No auth, no symbols, no
# intervals. Stored at ``<out_root>/fear_greed.zarr`` with a 2-D ``(N, 1)``
# data array so the layout stays symmetric with the other workspace zarrs.
_ALTERNATIVE_ME_FNG_URL = "https://api.alternative.me/fng/"
_FEAR_GREED_COLUMNS = ["value"]


@confluid.configurable
class DownloadFearGreed:
    """Fetch the Crypto Fear & Greed Index daily history from alternative.me.

    Stored at ``<out_root>/fear_greed.zarr`` with a 2-D ``data`` array of
    ``[value]`` rows (0=Extreme Fear, 100=Extreme Greed) and a parallel
    ``timestamps_ms`` array. One row per UTC day. No authentication —
    alternative.me's /fng/ endpoint is public.

    Args:
        out_root: Directory under which ``fear_greed.zarr`` is written.
            ``$VAR`` / ``${VAR}`` / ``~`` are expanded. Convention:
            ``$DATA_ROOT/traidwind/macro``.
        lookback_days: How many recent records to fetch. ``0`` means "all
            history" (alternative.me supports this via ``?limit=0``).
            Default 0.
        skip_if_fresh: If True, skip the fetch when the zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``.
    """

    def __init__(
        self,
        out_root: Union[str, Path],
        lookback_days: int = 0,
        skip_if_fresh: bool = True,
        freshness_tolerance_hours: int = 24,
    ) -> None:
        if lookback_days < 0:
            raise ValueError(f"lookback_days must be >= 0 (0 means all history), got {lookback_days}")
        self.out_root = _expand(out_root)
        self.lookback_days = lookback_days
        self.skip_if_fresh = skip_if_fresh
        self.freshness_tolerance_hours = freshness_tolerance_hours

    def run(self) -> None:
        import requests

        zpath = self.out_root / "fear_greed.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] fear_greed - zarr already fresh at {zpath}")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(_ALTERNATIVE_ME_FNG_URL, params={"limit": self.lookback_days}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        records = payload.get("data", [])
        if not records:
            logger.warning("[empty] fear_greed - alternative.me returned no records")
            return
        # API timestamps are seconds; canonical workspace unit is ms.
        # API returns NEWEST-FIRST; flip so the array is chronological.
        rows = [[int(r["timestamp"]) * 1000, float(r["value"])] for r in records]
        rows.sort(key=lambda row: row[0])
        df = pd.DataFrame(rows, columns=["timestamp_ms", "value"])
        df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        self._write_zarr(zpath, df)
        logger.info(f"[wrote] {len(df)} fear-greed daily records -> {zpath}")

    @staticmethod
    def _write_zarr(zpath: Path, df: pd.DataFrame) -> None:
        values = df[_FEAR_GREED_COLUMNS].to_numpy(dtype=np.float64)
        ts_ms = df["timestamp_ms"].to_numpy(dtype=np.int64)
        root = zarr.open_group(str(zpath), mode="w")
        root.create_dataset(
            "data",
            data=values,
            shape=values.shape,
            chunks=(min(4096, values.shape[0]), 1),
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
                "provider": "alternative.me",
                "metric": "fear_and_greed",
                "columns": _FEAR_GREED_COLUMNS,
                "start": df["date"].iloc[0].isoformat(),
                "end": df["date"].iloc[-1].isoformat(),
                "source": "alternative.me.fng",
            }
        )
