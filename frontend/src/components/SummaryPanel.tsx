const NCT_SPLIT = /(NCT\d{8})/g;
const isNct = (s: string) => /^NCT\d{8}$/.test(s);

interface Props {
  summary: string;
}

export function SummaryPanel({ summary }: Props) {
  if (!summary.trim()) return null;
  const parts = summary.split(NCT_SPLIT);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Analysis
      </h2>
      <p className="text-sm leading-relaxed text-slate-700">
        {parts.map((part, i) =>
          isNct(part) ? (
            <a
              key={i}
              href={`https://clinicaltrials.gov/study/${part}`}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-xs text-brand-600 hover:underline"
            >
              {part}
            </a>
          ) : (
            <span key={i}>{part}</span>
          ),
        )}
      </p>
    </div>
  );
}
