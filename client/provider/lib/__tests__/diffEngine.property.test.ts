/**
 * Property-based tests for diffEngine (Property 21: Correction diff round trip)
 *
 * Uses fast-check to verify:
 * - serialize → deserialize produces equivalent diff
 * - changes are non-empty when strings differ
 * - changes are empty when strings are identical
 */
import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import {
  computeDiff,
  serializeDiff,
  deserializeDiff,
  identifySection,
  type CorrectionDiff,
} from "../diffEngine";

// Polyfill crypto.subtle for Node (vitest runs in Node)
import { webcrypto } from "node:crypto";
if (!globalThis.crypto?.subtle) {
  // @ts-expect-error — Node webcrypto is compatible
  globalThis.crypto = webcrypto;
}

const encounterId = fc.stringMatching(/^[a-z_]+_[0-9]{4,8}_[0-9]{8}$/);
const noteText = fc.string({ minLength: 1, maxLength: 300 });

describe("Property 21: Correction diff round trip", () => {
  it("serialize → deserialize preserves all fields", async () => {
    await fc.assert(
      fc.asyncProperty(encounterId, noteText, noteText, async (eid, original, edited) => {
        const diff = await computeDiff(eid, original, edited);
        const json = serializeDiff(diff);
        const restored = deserializeDiff(json);

        expect(restored.encounter_id).toBe(diff.encounter_id);
        expect(restored.original_hash).toBe(diff.original_hash);
        expect(restored.edited_hash).toBe(diff.edited_hash);
        expect(restored.changes.length).toBe(diff.changes.length);

        for (let i = 0; i < diff.changes.length; i++) {
          expect(restored.changes[i].type).toBe(diff.changes[i].type);
          expect(restored.changes[i].section).toBe(diff.changes[i].section);
          expect(restored.changes[i].original_text).toBe(diff.changes[i].original_text);
          expect(restored.changes[i].edited_text).toBe(diff.changes[i].edited_text);
        }
      }),
      { numRuns: 100 },
    );
  });

  it("identical strings produce zero changes", async () => {
    await fc.assert(
      fc.asyncProperty(encounterId, noteText, async (eid, text) => {
        const diff = await computeDiff(eid, text, text);
        expect(diff.changes.length).toBe(0);
        expect(diff.original_hash).toBe(diff.edited_hash);
      }),
      { numRuns: 100 },
    );
  });

  it("different strings produce non-empty changes", async () => {
    await fc.assert(
      fc.asyncProperty(
        encounterId,
        noteText,
        noteText.filter((t) => t.length > 0),
        async (eid, original, edited) => {
          fc.pre(original !== edited);
          const diff = await computeDiff(eid, original, edited);
          expect(diff.changes.length).toBeGreaterThan(0);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("encounter_id is preserved through round trip", async () => {
    await fc.assert(
      fc.asyncProperty(encounterId, noteText, async (eid, text) => {
        const diff = await computeDiff(eid, text, text);
        const json = serializeDiff(diff);
        const restored = deserializeDiff(json);
        expect(restored.encounter_id).toBe(eid);
      }),
      { numRuns: 100 },
    );
  });

  it("section identification returns valid SOAP section or Unknown", () => {
    const soapNote = `## Subjective
Patient reports pain.
## Objective
Vitals normal.
## Assessment
Mild strain.
## Plan
Follow up in 2 weeks.`;

    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: soapNote.split("\n").length - 1 }),
        (lineNum) => {
          const section = identifySection(soapNote, lineNum);
          expect(["Subjective", "Objective", "Assessment", "Plan", "Unknown"]).toContain(section);
        },
      ),
      { numRuns: 100 },
    );
  });
});
