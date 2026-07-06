// Mirrors the backend response schema (app/schemas/visualization.py).

export type ChartType = "line" | "bar" | "grouped_bar" | "network" | "scatter";

export interface AxisEncoding {
  field: string;
  type: string;
}

export interface Encoding {
  x?: AxisEncoding | null;
  y?: AxisEncoding | null;
  color?: AxisEncoding | null;
}

export interface ChartConfig {
  x_label: string;
  y_label: string;
  x_axis_rotation: number;
  time_format?: string | null;
}

export interface VizMetadata {
  total_records: number;
  sampled: number;
  bucket_set_complete: boolean;
  data_caveat?: string | null;
  filters_applied: string;
  source: string;
  timestamp: string;
  chart_config: ChartConfig;
}

export interface NetworkNode {
  id: string;
  name: string;
  category: string;
  value: number;
  nct_ids: string[];
}

export interface NetworkLink {
  source: string;
  target: string;
  value: number;
  nct_ids: string[];
}

export interface NetworkData {
  nodes: NetworkNode[];
  links: NetworkLink[];
  categories: { name: string }[];
}

export type ChartPoint = {
  x: string | number;
  y: number;
  projected?: boolean;
  partial?: boolean;
};
export type GroupedRow = Record<string, string | number>;
export interface ScatterPoint {
  nct_id: string;
  title: string;
  phase: string;
  x: number;
  y: number;
}

// Discriminated union on `type` so `data` is correctly typed per chart (mirrors the backend
// validator). Lets consumers narrow without `as` casts.
interface VizBase {
  title: string;
  encoding: Encoding;
  metadata: VizMetadata;
}
export type Visualization =
  | (VizBase & { type: "line" | "bar"; data: ChartPoint[] })
  | (VizBase & { type: "grouped_bar"; data: GroupedRow[] })
  | (VizBase & { type: "scatter"; data: ScatterPoint[] })
  | (VizBase & { type: "network"; data: NetworkData });

export interface TrialRef {
  nct_id: string;
  title: string;
  url: string;
  excerpt?: string | null;
}

export interface Citation {
  bucket: string;
  value: number;
  nct_ids: string[];
  trials: TrialRef[];
}

export interface AlternativeViz {
  query_type: string;
  chart: string;
}

export interface Interpretation {
  query_type: string;
  parameters: Record<string, unknown>;
  reasoning: string;
  confidence: number;
  alternatives: AlternativeViz[];
}

export interface QueryResponse {
  event_id: string;
  query: string;
  interpretation: Interpretation;
  visualization: Visualization;
  citations: Citation[];
  summary: string;
  trace_id?: string | null;
}

export interface SupportedQueryType {
  type: string;
  example: string;
}

// Optional structured filters (mirrors the backend QueryRequest's optional fields). When set,
// each overrides whatever the agent would infer from the prose.
export interface QueryFilters {
  condition?: string;
  drug_name?: string;
  sponsor?: string;
  country?: string;
  trial_phase?: string;
  study_type?: string;
  status?: string[];
  start_year?: number;
  end_year?: number;
}

export interface UnsupportedResponse {
  error: string;
  message: string;
  supported_query_types: SupportedQueryType[];
  // The 422 handler may omit `query` and can return a null `event_id` (it's only set once the
  // rejected query is persisted as an event); the saved-event payload includes both.
  event_id?: string | null;
  query?: string;
}
