// Price panel rendered with TradingView lightweight-charts (v5).
// Candlestick + volume sub-pane for OHLCV trackers; a single line for price-line trackers.
import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { Series } from "../api";

// lightweight-charts wants a business-day string or a UNIX timestamp; our daily
// series carries ISO strings, so slice to "YYYY-MM-DD".
const toTime = (iso: string): Time => iso.slice(0, 10) as Time;

// lightweight-charts requires strictly-ascending, unique times. Some sources (e.g.
// CoinGecko) append an intraday "now" point that collapses onto the same business day
// as that day's midnight bar — keep the last value per day so setData doesn't reject it.
function dedupeByTime<T extends { time: Time }>(rows: T[]): T[] {
  const out: T[] = [];
  for (const r of rows) {
    if (out.length && out[out.length - 1].time === r.time) out[out.length - 1] = r;
    else out.push(r);
  }
  return out;
}

export function PriceChart({ series }: { series: Series }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current || !series.exists || series.time.length === 0) return;
    const chart: IChartApi = createChart(ref.current, {
      height: 360,
      layout: { background: { color: "transparent" }, textColor: "#cbd5e1" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      timeScale: { borderColor: "#334155" },
      rightPriceScale: { borderColor: "#334155" },
      autoSize: true,
    });

    if (series.chart_type === "candlestick") {
      const candles = chart.addSeries(CandlestickSeries, {
        upColor: "#26a69a",
        downColor: "#ef5350",
        wickUpColor: "#26a69a",
        wickDownColor: "#ef5350",
        borderVisible: false,
      });
      candles.setData(
        dedupeByTime(
          series.time.map((t, i) => ({
            time: toTime(t),
            open: series.columns.open[i] ?? 0,
            high: series.columns.high[i] ?? 0,
            low: series.columns.low[i] ?? 0,
            close: series.columns.close[i] ?? 0,
          })),
        ),
      );
      if (series.columns.volume) {
        const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, color: "#475569" }, 1);
        vol.setData(
          dedupeByTime(series.time.map((t, i) => ({ time: toTime(t), value: series.columns.volume[i] ?? 0 }))),
        );
      }
    } else {
      const name = Object.keys(series.columns)[0];
      const line = chart.addSeries(LineSeries, { color: "#f7931a", lineWidth: 2 });
      line.setData(
        dedupeByTime(series.time.map((t, i) => ({ time: toTime(t), value: series.columns[name][i] ?? 0 }))),
      );
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [series]);

  if (!series.exists || series.time.length === 0) {
    return <div className="chart-empty">No data on disk — click Update to download.</div>;
  }
  return <div ref={ref} className="chart" />;
}
