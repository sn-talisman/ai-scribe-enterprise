/**
 * Correction Diff Engine
 *
 * Computes structured diffs between AI-generated and provider-edited notes.
 * Saves as JSON for training data.
 *
 * Feature: provider-server-deployment
 * Requirements: 13.3, 13.4
 */

export interface DiffChange {
  type: "addition" | "deletion" | "modification";
  section: string; // SOAP section (Subjective, Objective, Assessment, Plan, Unknown)
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

/**
 * Header patterns that identify SOAP sections:
 *  - ## Subjective, # Subjective
 *  - **Subjective**, **Subjective:**
 *  - Subjective:
 */
const SECTION_PATTERNS: RegExp[] = SOAP_SECTIONS.map(
  (s) => new RegExp(`^(?:#{1,3}\\s*${s}|\\*\\*${s}\\*\\*:?|${s}:)\\s*$`, "i"),
);

/**
 * Scans backwards from the given line number to find the nearest SOAP section header.
 * Returns "Subjective", "Objective", "Assessment", "Plan", or "Unknown".
 */
export function identifySection(text: string, lineNumber: number): string {
  const lines = text.split("\n");
  const start = Math.min(lineNumber, lines.length - 1);

  for (let i = start; i >= 0; i--) {
    const trimmed = lines[i].trim();
    for (let s = 0; s < SOAP_SECTIONS.length; s++) {
      if (SECTION_PATTERNS[s].test(trimmed)) {
        return SOAP_SECTIONS[s];
      }
    }
  }
  return "Unknown";
}

/**
 * Compute a SHA-256 hex digest of the given string using the Web Crypto API.
 */
async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Compute a structured diff between the original and edited note content.
 *
 * Uses a simple line-by-line comparison. Consecutive changed lines are grouped
 * into a single DiffChange entry. Each change is tagged with the SOAP section
 * it belongs to.
 */
export async function computeDiff(
  encounterId: string,
  original: string,
  edited: string,
): Promise<CorrectionDiff> {
  const [originalHash, editedHash] = await Promise.all([
    sha256(original),
    sha256(edited),
  ]);

  const origLines = original.split("\n");
  const editLines = edited.split("\n");
  const maxLen = Math.max(origLines.length, editLines.length);

  const changes: DiffChange[] = [];
  let i = 0;

  while (i < maxLen) {
    const origLine = i < origLines.length ? origLines[i] : undefined;
    const editLine = i < editLines.length ? editLines[i] : undefined;

    // Lines match — skip
    if (origLine === editLine) {
      i++;
      continue;
    }

    // Start of a changed region — collect consecutive differing lines
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

    let type: DiffChange["type"];
    if (hasOrig && hasEdit) {
      type = "modification";
    } else if (hasOrig) {
      type = "deletion";
    } else {
      type = "addition";
    }

    // Identify section using the original text for deletions/modifications,
    // or the edited text for additions
    const contextText = hasOrig ? original : edited;
    const section = identifySection(contextText, regionStart);

    changes.push({
      type,
      section,
      original_text: origChunk.join("\n"),
      edited_text: editChunk.join("\n"),
      line_start: regionStart,
      line_end: i - 1,
    });
  }

  return {
    encounter_id: encounterId,
    original_hash: originalHash,
    edited_hash: editedHash,
    timestamp: new Date().toISOString(),
    changes,
  };
}

/**
 * Serialize a CorrectionDiff to a JSON string with 2-space indentation.
 */
export function serializeDiff(diff: CorrectionDiff): string {
  return JSON.stringify(diff, null, 2);
}

/**
 * Deserialize a JSON string back into a CorrectionDiff object.
 */
export function deserializeDiff(json: string): CorrectionDiff {
  return JSON.parse(json) as CorrectionDiff;
}
