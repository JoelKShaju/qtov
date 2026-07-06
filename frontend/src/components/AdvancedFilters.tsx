import { useState } from "react";

import type { QueryFilters } from "../lib/types";

const PHASES = ["Early Phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Not Applicable"];
const STUDY_TYPES = ["Interventional", "Observational"];
const STATUSES = [
  "RECRUITING",
  "NOT_YET_RECRUITING",
  "ACTIVE_NOT_RECRUITING",
  "COMPLETED",
  "TERMINATED",
  "WITHDRAWN",
];

interface Props {
  value: QueryFilters;
  onChange: (filters: QueryFilters) => void;
  disabled?: boolean;
}

function activeCount(f: QueryFilters): number {
  return Object.values(f).filter(
    (v) => v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
  ).length;
}

const inputCls =
  "w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:opacity-50";

export function AdvancedFilters({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const set = (patch: Partial<QueryFilters>) => onChange({ ...value, ...patch });
  const count = activeCount(value);

  const text = (key: keyof QueryFilters, label: string, placeholder = "") => (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <input
        className={inputCls}
        placeholder={placeholder}
        disabled={disabled}
        value={(value[key] as string) ?? ""}
        onChange={(e) => set({ [key]: e.target.value } as Partial<QueryFilters>)}
      />
    </label>
  );

  const year = (key: "start_year" | "end_year", label: string) => (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <input
        type="number"
        className={inputCls}
        disabled={disabled}
        value={value[key] ?? ""}
        onChange={(e) =>
          set({ [key]: e.target.value === "" ? undefined : Number(e.target.value) })
        }
      />
    </label>
  );

  const toggleStatus = (s: string) => {
    const current = value.status ?? [];
    set({ status: current.includes(s) ? current.filter((x) => x !== s) : [...current, s] });
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm text-slate-600 hover:text-slate-900"
      >
        <span className="font-medium">
          Advanced filters
          {count > 0 && (
            <span className="ml-2 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700">
              {count}
            </span>
          )}
        </span>
        <span className="text-slate-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-slate-100 p-4">
          <p className="text-xs text-slate-400">
            Optional. Anything set here overrides what the agent infers from your question.
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {text("condition", "Condition", "diabetes")}
            {text("drug_name", "Drug / intervention", "metformin")}
            {text("sponsor", "Sponsor", "Mayo Clinic")}
            {text("country", "Country", "United States")}
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-500">Phase</span>
              <select
                className={inputCls}
                disabled={disabled}
                value={value.trial_phase ?? ""}
                onChange={(e) => set({ trial_phase: e.target.value || undefined })}
              >
                <option value="">Any</option>
                {PHASES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-500">Study type</span>
              <select
                className={inputCls}
                disabled={disabled}
                value={value.study_type ?? ""}
                onChange={(e) => set({ study_type: e.target.value || undefined })}
              >
                <option value="">Any</option>
                {STUDY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            {year("start_year", "Start year ≥")}
            {year("end_year", "Start year ≤")}
          </div>

          <div>
            <span className="mb-1 block text-xs font-medium text-slate-500">Status</span>
            <div className="flex flex-wrap gap-1.5">
              {STATUSES.map((s) => {
                const on = (value.status ?? []).includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggleStatus(s)}
                    className={`rounded-full border px-2.5 py-1 text-xs transition ${
                      on
                        ? "border-brand-300 bg-brand-50 text-brand-700"
                        : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"
                    }`}
                  >
                    {s.replace(/_/g, " ").toLowerCase()}
                  </button>
                );
              })}
            </div>
          </div>

          {count > 0 && (
            <button
              type="button"
              onClick={() => onChange({})}
              disabled={disabled}
              className="text-xs text-slate-500 underline hover:text-slate-700"
            >
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
