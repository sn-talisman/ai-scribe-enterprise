import { fetchProvider, fetchProviderTrend } from "@/lib/api";
import ProviderTrendChart from "@/components/ProviderTrendChart";

export const dynamic = "force-dynamic";

interface ProviderProfile {
  id: string;
  name?: string;
  credentials?: string;
  specialty?: string;
  style_directives?: string[];
  custom_vocabulary?: string[];
  template_routing?: Record<string, string>;
  quality_scores?: Record<string, number>;
  quality_history?: Array<{ date?: string; version?: string; score?: number; samples?: number }>;
}

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ProviderDetailPage({ params }: Props) {
  const { id } = await params;
  const [rawProvider, trendData] = await Promise.all([
    fetchProvider(id).catch(() => null),
    fetchProviderTrend(id).catch(() => ({ trend: [] })),
  ]);

  if (!rawProvider) {
    return <div className="p-8 text-gray-400">Provider not found.</div>;
  }

  const p = rawProvider as unknown as ProviderProfile;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3 mb-1">
        <a href="/providers" className="text-sm text-gray-400 hover:text-gray-600">
          ← Providers
        </a>
      </div>

      {/* Header */}
      <div className="flex items-start gap-5">
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-lg flex-shrink-0"
          style={{ background: "var(--brand-indigo)" }}
        >
          {(p.name ?? p.id ?? "?").charAt(0).toUpperCase()}
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {p.name ?? p.id}{" "}
            {p.credentials && (
              <span className="text-gray-400 font-normal text-lg">{p.credentials}</span>
            )}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5 capitalize">{p.specialty ?? ""}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Style directives */}
        {p.style_directives && p.style_directives.length > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              Style Directives
            </h2>
            <ul className="space-y-2">
              {p.style_directives.map((d, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                  <span
                    className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                    style={{ background: "var(--brand-green)" }}
                  />
                  {d}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Custom vocabulary */}
        {p.custom_vocabulary && p.custom_vocabulary.length > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              Custom Vocabulary ({p.custom_vocabulary.length} terms)
            </h2>
            <div className="flex flex-wrap gap-2">
              {p.custom_vocabulary.map((t) => (
                <span
                  key={t}
                  className="text-xs px-2.5 py-1 rounded-full font-mono"
                  style={{ background: "#EEF2FF", color: "var(--brand-indigo)" }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Quality trend chart */}
      {trendData.trend.length > 0 && (
        <ProviderTrendChart trend={trendData.trend} />
      )}

      {/* Template routing */}
      {p.template_routing && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">Template Routing</h2>
          <div className="grid grid-cols-3 gap-3">
            {Object.entries(p.template_routing).map(([visit, tpl]) => (
              <div key={visit} className="text-sm">
                <div className="text-xs text-gray-400 capitalize">
                  {visit.replace(/_/g, " ")}
                </div>
                <div className="font-mono text-gray-700 text-xs mt-0.5">{tpl}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
