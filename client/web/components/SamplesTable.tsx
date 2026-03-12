"use client";

import { useState } from "react";
import Link from "next/link";
import type { SampleSummary } from "@/lib/api";
import ScoreBadge from "./ScoreBadge";

export default function SamplesTable({ samples }: { samples: SampleSummary[] }) {
  const [mode, setMode] = useState<"all" | "dictation" | "ambient">("all");
  const [sort, setSort] = useState<"id" | "score">("score");

  const filtered = samples
    .filter((s) => mode === "all" || s.mode === mode)
    .sort((a, b) => {
      if (sort === "score") {
        return (b.quality?.overall ?? 0) - (a.quality?.overall ?? 0);
      }
      return a.sample_id.localeCompare(b.sample_id);
    });

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100">
      {/* Filters */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3">
        {(["all", "dictation", "ambient"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{
              background:
                mode === m ? "var(--brand-green)" : "#F1F5F9",
              color: mode === m ? "white" : "#64748B",
            }}
          >
            {m.charAt(0).toUpperCase() + m.slice(1)}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          Sort:
          <button
            onClick={() => setSort("score")}
            className={`px-2 py-1 rounded ${sort === "score" ? "text-indigo-600 font-semibold" : ""}`}
          >
            Score
          </button>
          <button
            onClick={() => setSort("id")}
            className={`px-2 py-1 rounded ${sort === "id" ? "text-indigo-600 font-semibold" : ""}`}
          >
            ID
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b border-gray-50">
              <th className="px-6 py-3 font-medium">Sample ID</th>
              <th className="px-4 py-3 font-medium">Mode</th>
              <th className="px-4 py-3 font-medium">Versions</th>
              <th className="px-4 py-3 font-medium">Overall</th>
              <th className="px-4 py-3 font-medium">Accuracy</th>
              <th className="px-4 py-3 font-medium">Completeness</th>
              <th className="px-4 py-3 font-medium">No Halluc.</th>
              <th className="px-4 py-3 font-medium">Structure</th>
              <th className="px-4 py-3 font-medium">Gold</th>
              <th className="px-4 py-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr
                key={s.sample_id}
                className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
              >
                <td className="px-6 py-3 font-mono text-xs text-gray-700 max-w-[180px] truncate">
                  {s.sample_id}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{
                      background: s.mode === "dictation" ? "#EEF2FF" : "#E6F7F2",
                      color:
                        s.mode === "dictation"
                          ? "var(--brand-indigo)"
                          : "var(--brand-green-dark, #008F62)",
                    }}
                  >
                    {s.mode}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-400">
                  {s.versions.join(", ")}
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
                  {s.quality?.no_hallucination?.toFixed(1) ?? "—"}
                </td>
                <td className="px-4 py-3 text-gray-600">
                  {s.quality?.structure?.toFixed(1) ?? "—"}
                </td>
                <td className="px-4 py-3">
                  {s.has_gold ? (
                    <span className="text-green-600 text-xs">✓</span>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
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
      <div className="px-6 py-3 text-xs text-gray-400 border-t border-gray-50">
        {filtered.length} of {samples.length} samples
      </div>
    </div>
  );
}
