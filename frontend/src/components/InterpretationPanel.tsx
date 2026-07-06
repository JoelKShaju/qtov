import type { Interpretation, VizMetadata } from "../lib/types";

interface Props {
  interpretation: Interpretation;
  metadata: VizMetadata;
  onPickAlternative: (queryType: string) => void;
}

export function InterpretationPanel({ interpretation, metadata, onPickAlternative }: Props) {
  const params = Object.entries(interpretation.parameters).filter(
    ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0),
  );
  const showConfidence = interpretation.confidence < 0.9;
  const alternatives = interpretation.alternatives ?? [];
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-md bg-brand-50 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-brand-700">
          {interpretation.query_type.replace(/_/g, " ")}
        </span>
        <span className="text-sm text-slate-500">
          {metadata.total_records.toLocaleString()} trials
        </span>
        {showConfidence && (
          <span className="rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
            {Math.round(interpretation.confidence * 100)}% confident
          </span>
        )}
      </div>
      <p className="text-sm text-slate-600">{interpretation.reasoning}</p>
      {alternatives.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400">This query is ambiguous — also view as:</span>
          {alternatives.map((alt) => (
            <button
              key={alt.query_type}
              onClick={() => onPickAlternative(alt.query_type)}
              className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 transition hover:border-brand-300 hover:text-brand-700"
            >
              {alt.query_type.replace(/_/g, " ")} ({alt.chart.replace(/_/g, " ")})
            </button>
          ))}
        </div>
      )}
      {params.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {params.map(([k, v]) => (
            <span key={k} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
              {k.replace(/_/g, " ")}:{" "}
              <span className="font-medium text-slate-800">{formatVal(v)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function formatVal(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}
