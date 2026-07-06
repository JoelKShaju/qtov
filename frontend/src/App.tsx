import { useEffect, useMemo, useRef, useState } from "react";

import { AdvancedFilters } from "./components/AdvancedFilters";
import { ChartView } from "./components/ChartView";
import { CitationsDrawer } from "./components/CitationsDrawer";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ExampleChips } from "./components/ExampleChips";
import { InterpretationPanel } from "./components/InterpretationPanel";
import { QueryBar } from "./components/QueryBar";
import { SummaryPanel } from "./components/SummaryPanel";
import { UnsupportedNotice } from "./components/UnsupportedNotice";
import { getEvent, runQuery, type QueryResult } from "./lib/api";
import type { Citation, QueryFilters, QueryResponse, UnsupportedResponse } from "./lib/types";

const EXAMPLES = [
  {
    label: "Trend (line)",
    query: "How has the number of trials for pembrolizumab changed per year since 2015?",
  },
  { label: "Distribution (bar)", query: "How are diabetes trials distributed across phases?" },
  { label: "Comparison", query: "Compare phases for trials involving metformin vs semaglutide." },
  {
    label: "Geographic",
    query: "Which countries have the most recruiting trials for breast cancer?",
  },
  { label: "Network", query: "Show a network of sponsors and drugs for Alzheimer's trials." },
  {
    label: "Correlation (scatter)",
    query: "Is there a relationship between enrollment size and trial duration for diabetes trials?",
  },
  { label: "Unsupported", query: "What's the weather in Paris today?" },
];

export default function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [unsupported, setUnsupported] = useState<UnsupportedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filters, setFilters] = useState<QueryFilters>({});
  // Monotonic token so a slow earlier request can't overwrite a newer result (last-wins).
  const reqSeq = useRef(0);

  async function submit(q: string, forceQueryType?: string) {
    const seq = ++reqSeq.current;
    setQuery(q);
    setLoading(true);
    setError(null);
    setUnsupported(null);
    setSelected(null);
    const result: QueryResult = await runQuery(q, forceQueryType, filters);
    if (seq !== reqSeq.current) return; // a newer request superseded this one — drop the result
    setLoading(false);
    if (result.ok) {
      setResponse(result.data);
      // Update the URL to a shareable permalink for this result.
      window.history.pushState(null, "", `/${result.data.event_id}`);
    } else if (result.kind === "unsupported") {
      setResponse(null);
      setUnsupported(result.data);
      if (result.data.event_id) {
        window.history.pushState(null, "", `/${result.data.event_id}`);
      }
    } else {
      setResponse(null);
      setError(result.message);
    }
  }

  async function loadEvent(eventId: string) {
    const seq = ++reqSeq.current;
    setLoading(true);
    setError(null);
    setUnsupported(null);
    setSelected(null);
    const result = await getEvent(eventId);
    if (seq !== reqSeq.current) return; // superseded by a newer request
    setLoading(false);
    if (result.ok) {
      setResponse(result.data);
      setQuery(result.data.query);
    } else if (result.kind === "unsupported") {
      setResponse(null);
      setUnsupported(result.data);
      setQuery(result.data.query ?? "");
    } else {
      setResponse(null);
      setError(result.message);
    }
  }

  // On load / back-forward navigation, render the result for /<event_id> if present.
  useEffect(() => {
    const idFromPath = () => window.location.pathname.replace(/^\/+/, "").trim();
    const initial = idFromPath();
    if (initial) void loadEvent(initial);
    const onPop = () => {
      const id = idFromPath();
      if (id) void loadEvent(id);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const selectedCitations = useMemo<Citation[]>(() => {
    if (!response || !selected) return [];
    const exact = response.citations.filter((c) => c.bucket === selected);
    return exact.length ? exact : response.citations.filter((c) => c.bucket.includes(selected));
  }, [response, selected]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-5">
          <h1 className="text-xl font-bold text-slate-900">
            ClinicalTrials.gov Query-to-Visualization Agent
          </h1>
          <p className="text-sm text-slate-500">
            Ask in plain English. The agent classifies your question, queries ClinicalTrials.gov,
            and renders a cited visualization.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-5 px-6 py-8">
        <QueryBar value={query} onChange={setQuery} onSubmit={submit} loading={loading} />
        <AdvancedFilters value={filters} onChange={setFilters} disabled={loading} />
        <ExampleChips examples={EXAMPLES} onPick={setQuery} disabled={loading} />

        {loading && (
          <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-slate-400">
            Querying the agent…
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && unsupported && <UnsupportedNotice data={unsupported} onPick={submit} />}

        {!loading && response && (
          <div className="space-y-4">
            <InterpretationPanel
              interpretation={response.interpretation}
              metadata={response.visualization.metadata}
              onPickAlternative={(qt) => submit(response.query, qt)}
            />
            <ErrorBoundary
              key={response.event_id}
              fallback="This chart couldn't be rendered, but the interpretation and citations below are still available."
            >
              <ChartView viz={response.visualization} onSelect={setSelected} />
            </ErrorBoundary>
            <SummaryPanel summary={response.summary} />
          </div>
        )}

        {!loading && !response && !unsupported && !error && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-400">
            Try an example above to see a cited chart.
          </div>
        )}
      </main>

      <CitationsDrawer
        label={selected}
        citations={selectedCitations}
        sampled={response?.visualization.metadata.sampled ?? 0}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
