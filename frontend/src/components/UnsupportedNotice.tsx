import type { UnsupportedResponse } from "../lib/types";

interface Props {
  data: UnsupportedResponse;
  onPick: (q: string) => void;
}

export function UnsupportedNotice({ data, onPick }: Props) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
      <h2 className="mb-1 font-semibold text-amber-900">I can't answer that one</h2>
      <p className="mb-4 text-sm text-amber-800">{data.message}</p>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-600">
        Here's what I can answer
      </p>
      <div className="space-y-2">
        {data.supported_query_types.map((t) => (
          <button
            key={t.type}
            onClick={() => onPick(t.example)}
            className="block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-left text-sm text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-700"
          >
            <span className="mr-2 font-mono text-xs uppercase text-amber-600">
              {t.type.replace(/_/g, " ")}
            </span>
            {t.example}
          </button>
        ))}
      </div>
    </div>
  );
}
