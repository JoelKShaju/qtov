import type { Citation } from "../lib/types";

interface Props {
  label: string | null;
  citations: Citation[];
  sampled: number;
  onClose: () => void;
}

export function CitationsDrawer({ label, citations, sampled, onClose }: Props) {
  if (!label) return null;
  const total = citations.reduce((sum, c) => sum + c.nct_ids.length, 0);
  const grounding =
    sampled > 0
      ? `grounded in ${total.toLocaleString()} of the first ${sampled.toLocaleString()} trials examined`
      : `grounded in ${total.toLocaleString()} trial${total === 1 ? "" : "s"}`;
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Source trail</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✕
          </button>
        </div>
        <p className="mb-4 text-sm text-slate-500">
          <span className="font-medium text-slate-700">{label}</span> — {grounding}.
        </p>
        {citations.map((c) => (
          <div key={c.bucket} className="mb-4">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {c.bucket} · {c.value}
            </div>
            <ul className="space-y-1.5">
              {c.trials.map((t) => (
                <li key={t.nct_id} className="text-sm">
                  <a
                    href={t.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-xs text-brand-600 hover:underline"
                  >
                    {t.nct_id}
                  </a>
                  <span className="ml-2 text-slate-600">{t.title}</span>
                  {t.excerpt && (
                    <div className="ml-0 mt-0.5 border-l-2 border-slate-200 pl-2 text-xs italic text-slate-500">
                      {t.excerpt}
                    </div>
                  )}
                </li>
              ))}
              {c.trials.length < c.nct_ids.length && (
                <li className="text-xs text-slate-400">
                  + {c.nct_ids.length - c.trials.length} more…
                </li>
              )}
            </ul>
          </div>
        ))}
      </aside>
    </div>
  );
}
