"""Farside Investors US spot Bitcoin ETF daily-flow downloader."""

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
# Farside Investors — US spot Bitcoin ETF daily flows
# ---------------------------------------------------------------------------
# Farside publishes the canonical daily flow table for all US spot Bitcoin
# ETFs (IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL, BTCW, MSBT, GBTC,
# BTC) since launch on 2024-01-11. No paid API, no key — just HTML scraping
# behind a Cloudflare check that requires a real-browser User-Agent header.
_FARSIDE_ETF_FLOWS_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
_FARSIDE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
# Summary rows at the bottom of the Farside table (Average / Maximum / Minimum
# / Total / etc.) that look like data rows but aren't dated observations.
_FARSIDE_SUMMARY_ROW_LABELS = {"average", "maximum", "minimum", "total", "stdev", "median"}


@confluid.configurable
class DownloadFarsideETFFlows:
    """Fetch daily US spot Bitcoin ETF flow history from Farside Investors.

    Scrapes the HTML table at /bitcoin-etf-flow-all-data/ (Cloudflare-guarded
    but accessible with a real-browser User-Agent header) and stores it as
    ``<out_root>/farside/bitcoin_etf_flows.zarr`` with a 2-D data array
    whose columns are the individual ETF tickers + ``Total`` (in $M flows;
    negative = redemptions). Daily cadence, starts 2024-01-11 (ETF launch).

    No authentication required.

    Args:
        out_root: Directory under which
            ``farside/bitcoin_etf_flows.zarr`` is written.
            ``$VAR`` / ``${VAR}`` / ``~`` are expanded.
        skip_if_fresh: If True, skip the fetch when the zarr's last row is
            within ``freshness_tolerance_hours`` of now.
        freshness_tolerance_hours: Window used by ``skip_if_fresh``. ETF
            flows are daily; default 24h means "refresh at least once a day".
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

        zpath = self.out_root / "farside" / "bitcoin_etf_flows.zarr"
        if self.skip_if_fresh and _zarr_is_fresh(zpath, self.freshness_tolerance_hours):
            logger.info(f"[skip] bitcoin_etf_flows - zarr already fresh at {zpath}")
            return
        zpath.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(_FARSIDE_ETF_FLOWS_URL, headers={"User-Agent": _FARSIDE_USER_AGENT}, timeout=30)
        resp.raise_for_status()
        df = self._parse_farside_html(resp.text)
        if df.empty:
            logger.warning("[empty] bitcoin_etf_flows - parsed table had no dated rows")
            return
        self._write_zarr(zpath, df)
        logger.info(f"[wrote] {len(df)} ETF-flow daily records -> {zpath}")

    @staticmethod
    def _parse_farside_html(html: str) -> pd.DataFrame:
        """Parse the Farside HTML into a clean DataFrame.

        Steps:
          1. ``pd.read_html`` finds 3-4 tables; the flow table is the only
             one with >100 rows.
          2. Drop the all-NaN header padding row pandas inserts.
          3. Filter rows whose Date doesn't look like ``"D Mon YYYY"`` —
             that strips the Average/Maximum/Minimum summary rows at the
             bottom AND any "Total YTD" / blank-separator rows.
          4. Clean each numeric column: ``"$"`` and ``","`` removed,
             ``"(x)"`` parens → ``"-x"``, ``"-"`` → ``NaN`` → 0.
          5. Parse Date as UTC midnight (Farside reports in US Eastern but
             daily granularity makes the TZ irrelevant for our purposes).
        """
        from io import StringIO

        tables = pd.read_html(StringIO(html))
        # Pick the biggest table by TOTAL CELL COUNT (the flow table is far
        # wider than the 1x1 nav/footer junk tables). Using just row count
        # ties on small fixtures where every table has 1 row.
        df = max(tables, key=lambda t: t.size).copy()
        # First column is Date; rest are tickers + Total.
        date_col = df.columns[0]
        # Step 3 — keep only rows that look like a date.
        date_str = df[date_col].astype(str)
        is_dated = date_str.str.match(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$", na=False)
        # Belt-and-braces: also reject by summary-label match.
        is_summary = date_str.str.strip().str.lower().isin(_FARSIDE_SUMMARY_ROW_LABELS)
        df = df[is_dated & ~is_summary].reset_index(drop=True)
        # Step 4 — clean numeric columns. Vectorized regex replacement is
        # faster than per-column .str chains; ``to_numeric(errors="coerce")``
        # turns "-" and any other non-numeric into NaN which we then 0-fill
        # (Farside's "-" means "this ETF didn't exist yet on that date").
        for col in df.columns[1:]:
            s = (
                df[col]
                .astype(str)
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.replace("(", "-", regex=False)
                .str.replace(")", "", regex=False)
            )
            df[col] = pd.to_numeric(s, errors="coerce").fillna(0.0)
        # Step 5 — parse Date. Farside format: "11 Jan 2024".
        df["date"] = pd.to_datetime(df[date_col], format="%d %b %Y", utc=True)
        df["timestamp_ms"] = (df["date"].astype("int64") // 10**6).astype("int64")
        df = df.drop(columns=[date_col]).sort_values("timestamp_ms").reset_index(drop=True)
        return df

    def _write_zarr(self, zpath: Path, df: pd.DataFrame) -> None:
        # Column order: ETF tickers in the order Farside presents them,
        # followed by Total (always last).
        etf_columns = [c for c in df.columns if c not in ("date", "timestamp_ms")]
        data = df[etf_columns].to_numpy(dtype=np.float64)
        ts_ms = df["timestamp_ms"].to_numpy(dtype=np.int64)
        root = zarr.open_group(str(zpath), mode="w")
        root.create_dataset(
            "data",
            data=data,
            shape=data.shape,
            chunks=(min(4096, data.shape[0]), data.shape[1]),
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
                "provider": "farside.co.uk",
                "metric": "us_spot_bitcoin_etf_daily_flows_usd_millions",
                "columns": etf_columns,
                "start": df["date"].iloc[0].isoformat(),
                "end": df["date"].iloc[-1].isoformat(),
                "source": "farside.bitcoin-etf-flow-all-data",
            }
        )
