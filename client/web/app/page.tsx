import { fetchAggregate, fetchTrend, fetchDimensions, fetchSamples } from "@/lib/api";
import DashboardCharts from "@/components/DashboardCharts";
import ScoreBadge from "@/components/ScoreBadge";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const [agg, trendData, dims, samples] = await Promise.all([
    fetchAggregate("v5").catch(() => null),
    fetchTrend().catch(() => ({ trend: [] })),
    fetchDimensions("v5").catch(() => []),
    fetchSamples().catch(() => []),
  ]);

  const kpis = [
    {
      label: "Total Samples",
      value: samples.length,
      sub: `${samples.filter((s) => s.mode === "dictation").length} dictation · ${samples.filter((s) => s.mode === "ambient").length} ambient`,
      color: "var(--brand-green)",
    },
    {
      label: "Avg Quality Score",
      value: agg ? `${agg.average.toFixed(2)} / 5.0` : "—",
      sub: `${agg?.sample_count ?? 0} samples evaluated`,
      color: "var(--brand-indigo)",
    },
    {
      label: "Best Sample Score",
      value: agg ? `${agg.max.toFixed(2)} / 5.0` : "—",
      sub: "v5 pipeline",
      color: "#F59E0B",
    },
    {
      label: "Latest Version",
      value: "v5",
      sub: "Session 10 — ASR inference knobs",
      color: "#10B981",
    },
  ];

  // Recent samples (top 8 by quality score descending)
  const recent = [...samples]
    .filter((s) => s.quality?.overall != null)
    .sort((a, b) => (b.quality!.overall ?? 0) - (a.quality!.overall ?? 0))
    .slice(0, 8);

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">
          AI Scribe pipeline quality overview · Dr. Faraz Rahman · Orthopedic
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-5">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="bg-white rounded-xl p-5 shadow-sm border border-gray-100"
          >
            <div
              className="w-2 h-2 rounded-full mb-3"
              style={{ background: k.color }}
            />
            <div className="text-2xl font-bold text-gray-900">{k.value}</div>
            <div className="text-xs font-medium text-gray-600 mt-1">{k.label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <DashboardCharts trend={trendData.trend} dimensions={dims} />

      {/* Recent samples table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-800 text-sm">Top Samples by Quality</h2>
          <Link
            href="/samples"
            className="text-xs font-medium"
            style={{ color: "var(--brand-green)" }}
          >
            View all →
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-50">
                <th className="px-6 py-3 font-medium">Sample ID</th>
                <th className="px-4 py-3 font-medium">Mode</th>
                <th className="px-4 py-3 font-medium">Overall</th>
                <th className="px-4 py-3 font-medium">Accuracy</th>
                <th className="px-4 py-3 font-medium">Completeness</th>
                <th className="px-4 py-3 font-medium">Structure</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {recent.map((s) => (
                <tr
                  key={s.sample_id}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-6 py-3 font-mono text-xs text-gray-700">
                    {s.sample_id}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{
                        background:
                          s.mode === "dictation" ? "#EEF2FF" : "#E6F7F2",
                        color:
                          s.mode === "dictation"
                            ? "var(--brand-indigo)"
                            : "var(--brand-green-dark)",
                      }}
                    >
                      {s.mode}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ScoreBadge score={s.quality?.overall} />
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {s.quality?.accuracy?.toFixed(1) ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {s.quality?.completeness?.toFixed(1) ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {s.quality?.structure?.toFixed(1) ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/samples/${s.sample_id}`}
                      className="text-xs font-medium hover:underline"
                      style={{ color: "var(--brand-green)" }}
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
