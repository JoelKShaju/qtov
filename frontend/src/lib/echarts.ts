// Translate the backend's Visualization spec into an ECharts option, and map a
// chart click back to the citation "bucket" label so the source trail can open.

import type { NetworkData, Visualization } from "./types";

type Of<T extends Visualization["type"]> = Extract<Visualization, { type: T }>;

const PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#0ea5e9"];

export function buildOption(viz: Visualization): any {
  switch (viz.type) {
    case "network":
      return networkOption(viz.data);
    case "grouped_bar":
      return groupedBarOption(viz);
    case "scatter":
      return scatterOption(viz);
    default:
      return lineBarOption(viz);
  }
}

function scatterOption(viz: Of<"scatter">): any {
  const cc = viz.metadata.chart_config;
  const points = viz.data;
  // One series per phase so the legend doubles as a color key.
  const phases = Array.from(new Set(points.map((p) => p.phase)));
  return {
    tooltip: {
      trigger: "item",
      formatter: (p: any) =>
        `${p.data.nct_id}<br/>${cc.x_label}: ${p.data.value[0]}<br/>${cc.y_label}: ${p.data.value[1]}`,
    },
    legend: { top: 0, data: phases },
    grid: { left: 64, right: 24, top: 32, bottom: 56 },
    xAxis: { type: "value", name: cc.x_label, nameLocation: "middle", nameGap: 32, scale: true },
    yAxis: { type: "value", name: cc.y_label, nameLocation: "middle", nameGap: 44, scale: true },
    series: phases.map((phase, i) => ({
      name: phase,
      type: "scatter",
      symbolSize: 9,
      itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.7 },
      data: points
        .filter((p) => p.phase === phase)
        .map((p) => ({ value: [p.x, p.y], nct_id: p.nct_id, name: p.nct_id })),
    })),
  };
}

function lineBarOption(viz: Of<"line" | "bar">): any {
  const cc = viz.metadata.chart_config;
  const data = viz.data;
  const isLine = viz.type === "line";
  const incomplete = (d: (typeof data)[number]) => Boolean(d.projected || d.partial);
  const incompleteLabels = data.filter(incomplete).map((d) => String(d.x));
  // Shade the in-progress / projected tail of a time trend so it doesn't read as a real dip.
  const markArea =
    isLine && incompleteLabels.length
      ? {
          silent: true,
          itemStyle: { color: "rgba(245, 158, 11, 0.10)" },
          data: [[{ xAxis: incompleteLabels[0] }, { xAxis: incompleteLabels[incompleteLabels.length - 1] }]],
        }
      : undefined;
  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any[]) => {
        const p = params[0];
        const d = data[p.dataIndex];
        const tag = d?.projected ? " (projected)" : d?.partial ? " (in progress)" : "";
        return `${p.axisValue}${tag}<br/>${cc.y_label}: ${p.data?.value ?? p.data}`;
      },
    },
    grid: { left: 64, right: 24, top: 24, bottom: 88 },
    xAxis: {
      type: "category",
      name: cc.x_label,
      nameLocation: "middle",
      nameGap: 56,
      data: data.map((d) => String(d.x)),
      axisLabel: { rotate: cc.x_axis_rotation, hideOverlap: true },
    },
    yAxis: { type: "value", name: cc.y_label, nameLocation: "middle", nameGap: 44 },
    series: [
      {
        type: isLine ? "line" : "bar",
        smooth: isLine,
        symbolSize: 7,
        // Hollow, dimmed markers for incomplete (partial/projected) points.
        data: data.map((d) =>
          incomplete(d)
            ? { value: d.y, itemStyle: { opacity: 0.4 }, symbol: "circle", symbolKeepAspect: true }
            : d.y,
        ),
        itemStyle: { color: "#6366f1", borderRadius: isLine ? 0 : [4, 4, 0, 0] },
        areaStyle: isLine ? { opacity: 0.1 } : undefined,
        markArea,
        barWidth: "55%",
      },
    ],
  };
}

function groupedBarOption(viz: Of<"grouped_bar">): any {
  const rows = viz.data;
  const cc = viz.metadata.chart_config;
  const entities = rows.length ? Object.keys(rows[0]).filter((k) => k !== "bucket") : [];
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 64, right: 24, top: 40, bottom: 64 },
    xAxis: {
      type: "category",
      name: cc.x_label,
      nameLocation: "middle",
      nameGap: 36,
      data: rows.map((r) => String(r.bucket)),
    },
    yAxis: { type: "value", name: cc.y_label, nameLocation: "middle", nameGap: 44 },
    series: entities.map((e, i) => ({
      name: e,
      type: "bar",
      data: rows.map((r) => r[e] ?? 0),
      itemStyle: { color: PALETTE[i % PALETTE.length], borderRadius: [4, 4, 0, 0] },
    })),
  };
}

function networkOption(net: NetworkData): any {
  const categories = net.categories ?? [];
  const catIndex = (name: string) => Math.max(0, categories.findIndex((c) => c.name === name));
  return {
    tooltip: {
      formatter: (p: any) =>
        p.dataType === "edge" ? `${p.value} shared trials` : `${p.data.name} (${p.data.value})`,
    },
    legend: [{ data: categories.map((c) => c.name), top: 0 }],
    color: PALETTE,
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        categories,
        label: { show: true, position: "right", formatter: (p: any) => p.data.name },
        labelLayout: { hideOverlap: true },
        force: { repulsion: 220, edgeLength: [70, 180], gravity: 0.08 },
        data: net.nodes.map((n) => ({
          id: n.id,
          name: n.name,
          category: catIndex(n.category),
          symbolSize: Math.min(12 + n.value * 3, 52),
          value: n.value,
        })),
        links: net.links.map((l) => ({
          source: l.source,
          target: l.target,
          value: l.value,
          lineStyle: { width: Math.min(1 + l.value, 6) },
        })),
        lineStyle: { color: "source", curveness: 0.12, opacity: 0.55 },
        emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
      },
    ],
  };
}

export function labelFromClick(viz: Visualization, params: any): string | null {
  if (viz.type === "network") {
    if (params.dataType === "node") return params.data?.name ?? null;
    if (params.dataType === "edge") {
      const net = viz.data;
      const src = net.nodes.find((n) => n.id === params.data.source)?.name;
      const tgt = net.nodes.find((n) => n.id === params.data.target)?.name;
      return src && tgt ? `${src} → ${tgt}` : null;
    }
    return null;
  }
  if (viz.type === "grouped_bar") {
    return params.seriesName && params.name ? `${params.seriesName} · ${params.name}` : null;
  }
  if (viz.type === "scatter") {
    return params.data?.nct_id ?? null;
  }
  return params.name ?? null;
}
