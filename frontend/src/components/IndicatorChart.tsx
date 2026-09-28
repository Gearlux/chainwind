// Indicator panel rendered with Apache ECharts.
// The line is colour-coded by value zone (visualMap) and the zones are shaded as
// horizontal bands (markArea) — the natural way to read an MVRV-style score with
// overbought / oversold regions.
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { Series, Zone } from "../api";

function buildOption(series: Series): EChartsOption {
  const name = Object.keys(series.columns)[0] ?? "value";
  const values = series.columns[name] ?? [];
  const data = series.time.map((t, i) => [t, values[i]] as [string, number | null]);

  const finite = values.filter((v): v is number => v != null);
  const dataMin = finite.length ? Math.min(...finite) : 0;
  const dataMax = finite.length ? Math.max(...finite) : 1;

  // markArea: one shaded band per zone, clamped to the data range for open ends.
  const markAreaData = series.zones.map((z: Zone) => [
    { yAxis: z.lo ?? dataMin, itemStyle: { color: z.color, opacity: 0.12 }, name: z.label },
    { yAxis: z.hi ?? dataMax },
  ]);

  // visualMap: colour the line by which zone each value falls in.
  const pieces = series.zones.map((z: Zone) => {
    const piece: Record<string, unknown> = { color: z.color };
    if (z.lo != null) piece.gte = z.lo;
    if (z.hi != null) piece.lt = z.hi;
    return piece;
  });

  return {
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "time", axisLine: { lineStyle: { color: "#334155" } } },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { lineStyle: { color: "#334155" } },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    visualMap: pieces.length
      ? { type: "piecewise", show: false, dimension: 1, seriesIndex: 0, pieces }
      : undefined,
    series: [
      {
        type: "line",
        name,
        showSymbol: false,
        lineStyle: { width: 2 },
        data,
        markArea: markAreaData.length
          ? { silent: true, label: { show: false }, data: markAreaData as unknown as never }
          : undefined,
      },
    ],
  };
}

export function IndicatorChart({ series }: { series: Series }) {
  if (!series.exists || series.time.length === 0) {
    return <div className="chart-empty">No data on disk — click Update to download.</div>;
  }
  return <ReactECharts option={buildOption(series)} style={{ height: 360 }} notMerge lazyUpdate />;
}
