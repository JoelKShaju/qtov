interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (q: string) => void;
  loading: boolean;
}

export function QueryBar({ value, onChange, onSubmit, loading }: Props) {
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSubmit(value.trim());
      }}
    >
      <input
        className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-800 shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        placeholder="Ask about clinical trials — e.g. How have trials for pembrolizumab changed per year since 2015?"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="rounded-lg bg-brand-600 px-5 py-3 font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Running…" : "Run"}
      </button>
    </form>
  );
}
