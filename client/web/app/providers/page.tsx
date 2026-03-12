import { fetchProviders } from "@/lib/api";
import Link from "next/link";
import ScoreBadge from "@/components/ScoreBadge";

export const dynamic = "force-dynamic";

export default async function ProvidersPage() {
  const providers = await fetchProviders().catch(() => []);

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Providers</h1>
        <p className="text-gray-500 text-sm mt-1">
          Provider profiles with specialty configuration and quality history
        </p>
      </div>

      <div className="grid grid-cols-3 gap-5">
        {providers.map((p) => (
          <Link
            key={p.id}
            href={`/providers/${p.id}`}
            className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 hover:border-green-200 hover:shadow-md transition-all block"
          >
            <div className="flex items-start justify-between mb-3">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
                style={{ background: "var(--brand-indigo)" }}
              >
                {(p.name ?? p.id).charAt(0).toUpperCase()}
              </div>
              <ScoreBadge score={p.latest_score} />
            </div>
            <div className="font-semibold text-gray-900 text-sm">
              {p.name ?? p.id}
              {p.credentials && (
                <span className="text-gray-400 font-normal ml-1 text-xs">{p.credentials}</span>
              )}
            </div>
            <div className="text-xs text-gray-500 mt-0.5 capitalize">{p.specialty}</div>
            <div className="mt-3 flex flex-wrap gap-1">
              {Object.entries(p.quality_scores).map(([v, s]) => (
                <span
                  key={v}
                  className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500"
                >
                  {v}: {s.toFixed(2)}
                </span>
              ))}
            </div>
          </Link>
        ))}
        {providers.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400 text-sm">
            No provider profiles found. Add YAML files to config/providers/.
          </div>
        )}
      </div>
    </div>
  );
}
