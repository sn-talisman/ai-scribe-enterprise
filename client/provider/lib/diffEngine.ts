/**
 * Correction Diff Engine
 *
 * Computes structured diffs between AI-generated and provider-edited notes.
 * Saves as JSON for training data.
 */

export interface DiffChange {
  type: "addition" | "deletion" | "modification";
  section: string;
  original_text: string;
  edited_text: string;
  line_start: number;
  line_end: number;
}

export interface CorrectionDiff {
  encounter_id: string;
  original_hash: string;
  edited_hash: string;
  timestamp: string;
  changes: DiffChange[];
}

const SOAP_SECTIONS = ["Subjective", "Objective", "Assessment", "Plan"] as const;

const SECTION_PATTERNS: RegExp[] = SOAP_SECTIONS.map(
  (s) => new RegExp(`^(?:#{1,3}\\s*${s}|\\*\\*${s}\\*\\*:?|${s}:)\\s*`, "i"),
);

export function identifySection(text: string, lineNumber: number): string {
  const lines = text.split("\n");
  const start = Math.min(lineNumber, lines.length - 1);
  for (let i = start; i >= 0; i--) {
    const trimmed = lines[i].trim();
    for (let s = 0; s < SOAP_SECTIONS.length; s++) {
      if (SECTION_PATTERNS[s].test(trimmed)) return SOAP_SECTIONS[s];
    }
  }
  return "Unknown";
}

async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function computeDiff(
  encounterId: string,
  original: string,
  edited: string,
): Promise<CorrectionDiff> {
  const [originalHash, editedHash] = await Promise.all([sha256(original), sha256(edited)]);
  const origLines = original.split("\n");
  const editLines = edited.split("\n");
  const maxLen = Math.max(origLines.length, editLines.length);
  const changes: DiffChange[] = [];
  let i = 0;

  while (i < maxLen) {
    const origLine = i < origLines.length ? origLines[i] : undefined;
    const editLine = i < editLines.length ? editLines[i] : undefined;
    if (origLine === editLine) { i++; continue; }

    const regionStart = i;
    const origChunk: string[] = [];
    const editChunk: string[] = [];
    while (i < maxLen) {
      const oLine = i < origLines.length ? origLines[i] : undefined;
      const eLine = i < editLines.length ? editLines[i] : undefined;
      if (oLine === eLine) break;
      if (oLine !== undefined) origChunk.push(oLine);
      if (eLine !== undefined) editChunk.push(eLine);
      i++;
    }

    const hasOrig = origChunk.length > 0;
    const hasEdit = editChunk.length > 0;
    const type: DiffChange["type"] = hasOrig && hasEdit ? "modification" : hasOrig ? "deletion" : "addition";
    const contextText = hasOrig ? original : edited;
    const section = identifySection(contextText, regionStart);

    changes.push({ type, section, original_text: origChunk.join("\n"), edited_text: editChunk.join("\n"), line_start: regionStart, line_end: i - 1 });
  }

  return { encounter_id: encounterId, original_hash: originalHash, edited_hash: editedHash, timestamp: new Date().toISOString(), changes };
}

export function serializeDiff(diff: CorrectionDiff): string {
  return JSON.stringify(diff, null, 2);
}

export function deserializeDiff(json: string): CorrectionDiff {
  return JSON.parse(json) as CorrectionDiff;
}
