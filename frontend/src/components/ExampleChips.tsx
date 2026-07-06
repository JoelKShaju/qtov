interface Example {
  label: string;
  query: string;
}

interface Props {
  examples: Example[];
  onPick: (q: string) => void;
  disabled: boolean;
}

export function ExampleChips({ examples, onPick, disabled }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {examples.map((ex) => (
        <button
          key={ex.query}
          disabled={disabled}
          onClick={() => onPick(ex.query)}
          title={ex.query}
          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 shadow-sm transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
        >
          {ex.label}
        </button>
      ))}
    </div>
  );
}
