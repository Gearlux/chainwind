// Overlay several trackers' primary series in one ECharts chart.
// Toggle between % change from the window start (cross-scale comparable) and raw values
// on per-series y-axes — the user-chosen way to compare e.g. BTC (~100k) vs ETH (~3k).
import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { PrimarySeries } from "../api";

const PALETTE = ["#f7931a", "#26a69a", "#42a5f5", "#ab47bc", "#ef5350", "#ffca28", "#8d6e63"];

function firstFinite(values: (number | null)[]): number | null {
  for (const v of values) if (v != null && Number.isFinite(v)) return v;
  return null;
}

function buildOption(series: PrimarySeries[], normalize: boolean): EChartsOption {
  const echSeries = series.map((s, i) => {
    const color = PALETTE[i % PALETTE.length];
    const base = normalize ? firstFinite(s.values) : null;
    const data = s.time.map((t, j) => {
      const v = s.values[j];
      const y = normalize && base ? (v == null ? null : (v / base - 1) * 100) : v;
      return [t, y] as [string, number | null];
    });
    return {
      type: "line" as const,
      name: s.label,
      showSymbol: false,
      lineStyle: { width: 2, color },
      itemStyle: { color },
      yAxisIndex: normalize ? 0 : i,
      data,
    };
  });

  const yAxis = normalize
    ? [{ type: "value" as const, name: "% change", axisLabel: { formatter: "{value}%" } }]
    : series.map((s, i) => ({
        type: "value" as const,
        position: i % 2 === 0 ? ("left" as const) : ("right" as const),
        offset: Math.floor(i / 2) * 52,
        axisLine: { show: true, lineStyle: { color: PALETTE[i % PALETTE.length] } },
        name: s.unit || s.label,
        nameTextStyle: { color: PALETTE[i % PALETTE.length] },
        splitLine: { show: i === 0 },
      }));

  return {
    grid: { left: 56, right: 56, top: 48, bottom: 64 },
    legend: { top: 8, textStyle: { color: "#cbd5e1" } },
    tooltip: { trigger: "axis" },
    xAxis: { type: "time", axisLine: { lineStyle: { color: "#334155" } } },
    yAxis,
    dataZoom: [
      { type: "inside" },
      { type: "slider", bottom: 16, height: 18 },
    ],
    series: echSeries,
  };
}

export function CompareChart({ series }: { series: PrimarySeries[] }) {
  const [normalize, setNormalize] = useState(true);
  const option = useMemo(() => buildOption(series, normalize), [series, normalize]);

  if (series.length === 0) {
    return <div className="chart-empty">Tick “compare” on datasets in the catalog to overlay them here.</div>;
  }
  return (
    <div>
      <div className="compare-head">
        <strong>Compare ({series.length})</strong>
        <div className="toggle">
          <button className={normalize ? "on" : ""} onClick={() => setNormalize(true)}>
            % change
          </button>
          <button className={normalize ? "" : "on"} onClick={() => setNormalize(false)}>
            raw
          </button>
        </div>
      </div>
      <ReactECharts option={option} style={{ height: 380 }} notMerge lazyUpdate />
    </div>
  );
}
