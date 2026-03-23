"use client";

import { useState, useCallback } from "react";
import MarkdownViewer from "./MarkdownViewer";

export interface NoteEditorProps {
  encounterId: string;
  originalNote: string;
  onSave: (editedNote: string) => void;
  onApprove: (editedNote: string) => void;
}

export default function NoteEditor({
  encounterId,
  originalNote,
  onSave,
  onApprove,
}: NoteEditorProps) {
  const [editedNote, setEditedNote] = useState(originalNote);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);

  const isDirty = editedNote !== originalNote;

  const handleSave = useCallback(async () => {
    setSaving(true);
    try { onSave(editedNote); } finally { setSaving(false); }
  }, [editedNote, onSave]);

  const handleApprove = useCallback(async () => {
    setApproving(true);
    try { onApprove(editedNote); } finally { setApproving(false); }
  }, [editedNote, onApprove]);

  const handleReset = useCallback(() => {
    setEditedNote(originalNote);
  }, [originalNote]);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-medium text-gray-700">Note Editor</h3>
          {isDirty && (
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
              Modified
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            disabled={!isDirty}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-100 text-slate-500 transition-colors disabled:opacity-40"
          >
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-3 py-1.5 rounded text-xs font-medium text-white bg-indigo-600 transition-colors disabled:opacity-60"
          >
            {saving ? "Saving\u2026" : "Save"}
          </button>
          <button
            onClick={handleApprove}
            disabled={approving}
            className="px-3 py-1.5 rounded text-xs font-medium text-white bg-green-600 transition-colors disabled:opacity-60"
          >
            {approving ? "Approving\u2026" : "Approve"}
          </button>
        </div>
      </div>

      {/* Editor + Preview split */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-gray-100">
        <div className="p-4">
          <label className="block text-xs text-gray-400 mb-2">Edit</label>
          <textarea
            value={editedNote}
            onChange={(e) => setEditedNote(e.target.value)}
            className="w-full h-[60vh] resize-none rounded-lg border border-gray-200 p-3 text-sm font-mono leading-relaxed text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-gray-50"
            spellCheck
          />
        </div>
        <div className="p-4 overflow-y-auto max-h-[calc(60vh+2rem)]">
          <label className="block text-xs text-gray-400 mb-2">Preview</label>
          <MarkdownViewer content={editedNote} />
        </div>
      </div>
    </div>
  );
}
