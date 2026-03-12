"use client";

import { useState } from "react";
import MarkdownViewer from "./MarkdownViewer";
import QualityPanel from "./QualityPanel";
import type { QualityScore } from "@/lib/api";

interface Props {
  sampleId: string;
  version: string;
  note: string | null;
  comparison: string | null;
  gold: string | null;
  quality: (QualityScore & { sample_id: string }) | null;
}

const TABS = [
  { id: "note", label: "Clinical Note" },
  { id: "comparison", label: "Comparison" },
  { id: "gold", label: "Gold Standard" },
  { id: "quality", label: "Quality Scores" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SampleDetailTabs({
  note,
  comparison,
  gold,
  quality,
}: Props) {
  const [active, setActive] = useState<TabId>("note");

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100">
      {/* Tab bar */}
      <div className="flex border-b border-gray-100 px-6">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setActive(id)}
            className="py-3 px-4 text-sm font-medium transition-colors border-b-2 -mb-px"
            style={{
              borderColor: active === id ? "var(--brand-green)" : "transparent",
              color: active === id ? "var(--brand-green)" : "#94A3B8",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-6">
        {active === "note" && (
          note
            ? <MarkdownViewer content={note} />
            : <Empty msg="Generated note not available for this sample/version." />
        )}
        {active === "comparison" && (
          comparison
            ? <MarkdownViewer content={comparison} />
            : <Empty msg="Comparison document not available for this sample/version." />
        )}
        {active === "gold" && (
          gold
            ? <MarkdownViewer content={gold} />
            : <Empty msg="Gold-standard note not available for this sample." />
        )}
        {active === "quality" && (
          quality
            ? <QualityPanel quality={quality} />
            : <Empty msg="Quality scores not available for this sample/version." />
        )}
      </div>
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="text-center py-12 text-gray-400 text-sm">{msg}</div>
  );
}
