import ReactECharts from "echarts-for-react";

import { buildOption, labelFromClick } from "../lib/echarts";
import type { Visualization } from "../lib/types";

interface Props {
  viz: Visualization;
  onSelect: (label: string) => void;
}

export function ChartView({ viz, onSelect }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-1 text-lg font-semibold text-slate-800">{viz.title}</h2>
      <p className="mb-3 text-xs text-slate-400">
        Source: {viz.metadata.source} · Filters: {viz.metadata.filters_applied} · Click a data point
        to trace its trials
      </p>
      {viz.metadata.data_caveat && (
        <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
          ⚠ {viz.metadata.data_caveat}
        </p>
      )}
      <ReactECharts
        option={buildOption(viz)}
        style={{ height: 460, width: "100%" }}
        notMerge
        onEvents={{
          click: (params: any) => {
            const label = labelFromClick(viz, params);
            if (label) onSelect(label);
          },
        }}
      />
    </div>
  );
}
