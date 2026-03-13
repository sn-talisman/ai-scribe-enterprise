const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SampleSummary {
  sample_id: string;
  mode: "dictation" | "ambient";
  versions: string[];
  latest_version: string | null;
  has_gold: boolean;
  quality: QualityScore | null;
}

export interface SampleDetail extends SampleSummary {
  patient_context: PatientContext | null;
}

export interface QualityScore {
  overall: number | null;
  accuracy: number | null;
  completeness: number | null;
  no_hallucination: number | null;
  structure: number | null;
  language: number | null;
  overlap: string | null;
}

export interface AggregateQuality {
  version: string;
  sample_count: number;
  average: number;
  min: number;
  max: number;
  dimensions: Record<string, number | null>;
}

export interface DimensionScore {
  dimension: string;
  score: number | null;
}

export interface ProviderSummary {
  id: string;
  name: string | null;
  credentials: string | null;
  specialty: string | null;
  latest_score: number | null;
  quality_scores: Record<string, number>;
}

export interface PatientContext {
  patient?: {
    name?: string;
    date_of_birth?: string;
    age?: number;
    sex?: string;
    mrn?: string;
  };
  encounter?: {
    date_of_service?: string;
    visit_type?: string;
    date_of_injury?: string;
    mechanism_of_injury?: string;
  };
  provider?: {
    name?: string;
    credentials?: string;
    specialty?: string;
  };
  facility?: { name?: string; location?: string };
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// Encounters
export const fetchSamples = (mode?: string) =>
  get<SampleSummary[]>("/encounters", mode ? { mode } : undefined);

export const fetchSample = (id: string) =>
  get<SampleDetail>(`/encounters/${id}`);

export const fetchNote = (id: string, version = "v6") =>
  get<{ content: string }>(`/encounters/${id}/note`, { version });

export const fetchComparison = (id: string, version = "v6") =>
  get<{ content: string }>(`/encounters/${id}/comparison`, { version });

export const fetchGoldNote = (id: string) =>
  get<{ content: string }>(`/encounters/${id}/gold`);

export const fetchSampleQuality = (id: string, version = "v6") =>
  get<QualityScore & { sample_id: string }>(`/encounters/${id}/quality`, { version });

export const fetchTranscript = (id: string, version = "v6") =>
  get<{ content: string; versions: string[] }>(`/encounters/${id}/transcript`, { version });

export const fetchAudioUrl = (id: string): string =>
  `${BASE}/encounters/${id}/audio`;

// Quality
export const fetchAggregate = (version = "v5") =>
  get<AggregateQuality>("/quality/aggregate", { version });

export const fetchTrend = () =>
  get<{ trend: AggregateQuality[] }>("/quality/trend");

export const fetchDimensions = (version = "v5") =>
  get<DimensionScore[]>("/quality/dimensions", { version });

export const fetchSampleScores = (version = "v5", mode?: string) =>
  get<Array<QualityScore & { sample_id: string; mode: string; version: string }>>(
    "/quality/samples",
    mode ? { version, mode } : { version }
  );

// Providers
export const fetchProviders = () => get<ProviderSummary[]>("/providers");
export const fetchProvider = (id: string) => get<Record<string, unknown>>(`/providers/${id}`);
export const fetchProviderTrend = (id: string) =>
  get<{ trend: Array<{ version: string; score: number; date: string | null; samples: number | null }> }>(
    `/providers/${id}/quality-trend`
  );
