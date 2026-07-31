"""CoinMetrics Community API MVRV downloader — free, no-auth, multi-asset."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

import confluid
import numpy as np
import pandas as pd
import zarr
from loggair import get_logger
from traidwind.paths import _expand, _zarr_is_fresh

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# CoinMetrics Community Network Data — free, no authentication
# ---------------------------------------------------------------------------
# Unlike bitcoin-data.com (Bitcoin-only — see DownloadMVRVZScore), CoinMetrics'
# community API publishes the MVRV *ratio* (CapMVRVCur) and market cap
# (CapMrktCurUSD) for ~150 assets (BTC, ETH, ADA, ...) at daily frequency with
# NO API key. We derive the MVRV Z-Score locally from those two free metrics:
#     realized_cap = market_cap / mvrv_ratio
#     z            = (market_cap - realized_cap) / stdev(market_cap, all-time)
#
# IMPORTANT — cross-provider scale: the realized-cap methodology and the stdev
# window differ from bitcoin-data.com, so the Z-Score's ABSOLUTE scale is NOT
# directly comparable across providers. The signal/shape tracks closely, but
# the canonical BTC cycle-band thresholds (>6 top, <0 accumulation) do NOT
# transfer 1:1 — interpret the CoinMetrics Z-Score on its own historical range.
#
# Solana is NOT covered (no free realized-cap source for an account-based chain
# with CoinMetrics community); requesting it logs a clear [unsupported] warning
# and writes nothing. Both metrics are required (the user asked for both the
# ratio AND the Z-Score column), so an asset whose market cap is credential-
# gated is also treated as unsupported.
_COINMETRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
_RATIO_METRIC = "CapMVRVCur"
_MCAP_METRIC = "CapMrktCurUSD"
_MVRV_COLUMNS = ["mvrv", "mvrv_zscore"]


@confluid.configurable
class DownloadCoinMetricsMVRV:
    """Fetch the daily MVRV ratio + derived Z-Score for one asset from CoinMetrics.

    Free, no authentication. Stored at ``<out_root>/coinmetrics/<asset>_mvrv.zarr``
    with a 2-D ``(N, 2)`` data array of ``[mvrv, mvrv_zscore]`` rows — the raw
    MVRV ratio (``CapMVRVCur``) and the locally-derived MVRV Z-Score.

    Covers BTC, ETH, ADA and ~150 other CoinMetrics community assets. Solana is
    NOT available (no free realized-cap source) — requesting an unsupported (or
    credential-gated) asset logs ``[unsupported]`` and writes nothing rather
    than raising, so a multi-asset batch keeps going.

    The Z-Score is derived as ``(MV - RV) / stdev(MV)`` with ``RV = MV / ratio``
    and ``MV`` the market cap (``CapMrktCurUSD``), ``stdev`` taken over the full
    downloaded history (the canonical all-time MVRV Z-Score definition). Because
    the realized-cap methodology and stdev window differ from bitcoin-data.com's
    BTC series, the Z-Score's absolute scale is provider-specific — see the
    module docstring before reusing the BTC cycle-band thresholds.

    Args:
        asset: Ticker symbol (case-insensitive, e.g. ``"BTC"``, ``"ETH"``).
            Lowercased to the CoinMetrics asset id.
        out_root: Directory under which ``coinmetrics/<asset>_mvrv.zarr`` is
            written. ``$VAR`` / ``${VAR}`` / ``~`` are expanded. Convention:
            ``$DATA_ROOT/traidwind/macro``.
        skip_if_fresh: If True, skip the fetch when the zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``.
    """

    def __init__(
        self,
        asset: str = "BTC",
        out_root: Union[str, Path] = "${DATA_ROOT}/traidwind/macro",
        skip_if_fresh: bool = True,
        freshness_tolerance_hours: int = 24,
    ) -> None:
        self.asset = asset
        self.out_root = _expand(out_root)
        self.skip_if_fresh = skip_if_fresh
        self.freshness_tolerance_hours = freshness_tolerance_hours

    @property
    def asset_id(self) -> str:
        """CoinMetrics asset id — the lowercased ticker (``"BTC"`` -> ``"btc"``)."""
        return self.asset.strip().lower()

    def run(self) -> None:
        import requests

        asset_id = self.asset_id
        zpath = self.out_root / "coinmetrics" / f"{asset_id}_mvrv.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] {asset_id}_mvrv - zarr already fresh at {zpath}")
            return
        records = self._fetch_all(requests, asset_id)
        if records is None:
            return  # unsupported / gated asset — already logged
        if not records:
            logger.warning(f"[empty] {asset_id}_mvrv - CoinMetrics returned no records")
            return
        df = self._build_frame(records)
        if df.empty:
            logger.warning(f"[empty] {asset_id}_mvrv - no rows with both ratio and market cap")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        self._write_zarr(zpath, df, asset_id)
        logger.info(f"[wrote] {len(df)} {asset_id} MVRV ratio+zscore daily records -> {zpath}")

    @staticmethod
    def _fetch_all(requests_mod: Any, asset_id: str) -> Optional[List[Dict[str, Any]]]:
        """Paginate the CoinMetrics timeseries endpoint.

        Returns the accumulated data rows, or ``None`` when the asset/metric is
        unsupported or credential-gated (HTTP 400/403) — that case is logged and
        treated as "skip this asset" rather than an error.
        """
        params: Optional[Dict[str, str]] = {
            "assets": asset_id,
            "metrics": f"{_RATIO_METRIC},{_MCAP_METRIC}",
            "frequency": "1d",
            "page_size": "10000",
        }
        url: Optional[str] = _COINMETRICS_URL
        out: List[Dict[str, Any]] = []
        while url:
            # The first request carries query params; next_page_url already
            # embeds them, so params is only sent on the initial call.
            resp = requests_mod.get(url, params=params, timeout=30)
            if resp.status_code in (400, 403):
                try:
                    msg = resp.json().get("error", {}).get("message", resp.text)
                except ValueError:
                    msg = resp.text
                logger.warning(f"[unsupported] {asset_id}_mvrv - CoinMetrics: {msg}")
                return None
            resp.raise_for_status()
            payload = resp.json()
            out.extend(payload.get("data", []))
            url = payload.get("next_page_url")
            params = None
        return out

    @staticmethod
    def _build_frame(records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Build a chronological frame with the ratio + derived Z-Score columns."""
        rows = []
        for r in records:
            ratio = r.get(_RATIO_METRIC)
            mcap = r.get(_MCAP_METRIC)
            if ratio is None or mcap is None:
                continue  # only keep timestamps where BOTH metrics are present
            ts_ms = pd.Timestamp(r["time"]).value // 1_000_000  # ns -> ms
            rows.append((int(ts_ms), float(ratio), float(mcap)))
        if not rows:
            return pd.DataFrame(columns=["timestamp_ms", "mvrv", "market_cap", "mvrv_zscore", "date"])
        df = pd.DataFrame(rows, columns=["timestamp_ms", "mvrv", "market_cap"])
        df = df.drop_duplicates(subset="timestamp_ms").sort_values("timestamp_ms").reset_index(drop=True)
        df["mvrv_zscore"] = _compute_zscore(
            df["market_cap"].to_numpy(dtype=np.float64),
            df["mvrv"].to_numpy(dtype=np.float64),
        )
        df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        return df

    @staticmethod
    def _write_zarr(zpath: Path, df: pd.DataFrame, asset_id: str) -> None:
        values = df[_MVRV_COLUMNS].to_numpy(dtype=np.float64)
        ts_ms = df["timestamp_ms"].to_numpy(dtype=np.int64)
        root = zarr.open_group(str(zpath), mode="w")
        root.create_array("data", data=values, chunks=(min(4096, values.shape[0]), len(_MVRV_COLUMNS)))
        root.create_array("timestamps_ms", data=ts_ms, chunks=(min(4096, ts_ms.shape[0]),))
        root.attrs.update(
            {
                "provider": "coinmetrics",
                "metric": "mvrv",
                "asset": asset_id,
                "columns": _MVRV_COLUMNS,
                "start": df["date"].iloc[0].isoformat(),
                "stop": df["date"].iloc[-1].isoformat(),
                "source": f"coinmetrics.community.v4.{asset_id}.CapMVRVCur+CapMrktCurUSD",
            }
        )


def _compute_zscore(market_cap: np.ndarray, ratio: np.ndarray) -> np.ndarray:
    """MVRV Z-Score = ``(market_cap - realized_cap) / stdev(market_cap)``.

    Realized cap is recovered from the published ratio as ``market_cap / ratio``
    (``ratio = market_cap / realized_cap``). ``stdev`` is the population stdev
    over the full series — the canonical all-time MVRV Z-Score window. Rows with
    a non-positive ratio yield ``NaN`` (division guard); a degenerate zero-stdev
    series yields all-zero scores.
    """
    realized = np.divide(
        market_cap,
        ratio,
        out=np.full_like(market_cap, np.nan, dtype=np.float64),
        where=ratio > 0,
    )
    sigma = float(np.std(market_cap, ddof=0))
    if sigma == 0.0:
        return np.zeros_like(market_cap, dtype=np.float64)
    return cast(np.ndarray, (market_cap - realized) / sigma)
