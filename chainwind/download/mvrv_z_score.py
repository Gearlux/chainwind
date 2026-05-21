"""bitcoin-data.com daily MVRV Z-Score downloader."""

from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
import zarr

import confluid
from logflow import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# bitcoin-data.com MVRV Z-Score (free, no auth)
# ---------------------------------------------------------------------------
# 4 years of daily MVRV Z-Score history. Per Gemini's checklist (4.1) the
# MVRV Z-Score is one of the canonical Bitcoin cycle-overheating indicators:
#   * MVRV-Z > 6 → cycle top likely
#   * MVRV-Z < 0 → long-term accumulation zone
_BITCOIN_DATA_MVRV_URL = "https://bitcoin-data.com/api/v1/mvrv-zscore"
_MVRV_COLUMNS = ["mvrv_zscore"]


@confluid.configurable
class DownloadMVRVZScore:
    """Fetch the daily Bitcoin MVRV Z-Score history from bitcoin-data.com.

    Stored at ``<out_root>/mvrv_zscore.zarr`` with a 2-D ``(N, 1)`` data
    array of ``[mvrv_zscore]`` rows. No authentication required —
    bitcoin-data.com's /api/v1/mvrv-zscore endpoint is public; the free
    tier returns ~4 years of daily history (2022 onwards).

    Args:
        out_root: Directory under which ``mvrv_zscore.zarr`` is written.
            ``$VAR`` / ``${VAR}`` / ``~`` are expanded. Convention:
            ``$DATA_ROOT/traidwind/macro``.
        skip_if_fresh: If True, skip the fetch when the zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``.
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

        zpath = self.out_root / "mvrv_zscore.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] mvrv_zscore - zarr already fresh at {zpath}")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(_BITCOIN_DATA_MVRV_URL, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            logger.warning("[empty] mvrv_zscore - bitcoin-data.com returned no records")
            return
        # API rows: {"d": "YYYY-MM-DD", "unixTs": <int seconds>, "mvrvZscore": <float>}.
        rows = [[int(r["unixTs"]) * 1000, float(r["mvrvZscore"])] for r in payload]
        rows.sort(key=lambda r: r[0])
        df = pd.DataFrame(rows, columns=["timestamp_ms", "mvrv_zscore"])
        df = (
            df.drop_duplicates(subset="timestamp_ms")
            .sort_values("timestamp_ms")
            .reset_index(drop=True)
        )
        df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        self._write_zarr(zpath, df)
        logger.info(f"[wrote] {len(df)} MVRV Z-score daily records -> {zpath}")

    @staticmethod
    def _write_zarr(zpath: Path, df: pd.DataFrame) -> None:
        values = df[_MVRV_COLUMNS].to_numpy(dtype=np.float64)
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
                "provider": "bitcoin-data.com",
                "metric": "mvrv_zscore",
                "columns": _MVRV_COLUMNS,
                "start": df["date"].iloc[0].isoformat(),
                "end": df["date"].iloc[-1].isoformat(),
                "source": "bitcoin-data.com.api.v1.mvrv-zscore",
            }
        )
