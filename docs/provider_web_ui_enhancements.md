# Provider Web UI Enhancements

## Note Editor (`client/web/components/NoteEditor.tsx`)

A split-pane editor for reviewing and editing AI-generated clinical notes.

- Left pane: editable textarea with the note content
- Right pane: live markdown preview (uses existing MarkdownViewer)
- "Modified" badge when content differs from original
- Save: persists edited version alongside original via `POST /encounters/{id}/note/edit`
- Approve: marks note as approved for EHR push-back via `POST /encounters/{id}/note/approve`
- Reset: reverts to original content

### Usage

```tsx
import NoteEditor from "@/components/NoteEditor";

<NoteEditor
  encounterId="james_dotson_224938_20260224"
  originalNote={noteContent}
  onSave={(edited) => saveEditedNote(encounterId, edited)}
  onApprove={(edited) => approveNote(encounterId, edited)}
/>
```

## Correction Diff Engine (`client/web/lib/diffEngine.ts`)

Computes structured diffs between AI-generated and provider-edited notes for training data.

- `computeDiff(encounterId, original, edited)` — async, returns `CorrectionDiff` with SHA-256 hashes and grouped changes
- `identifySection(text, lineNumber)` — identifies SOAP section (Subjective, Objective, Assessment, Plan) by scanning backwards for headers
- `serializeDiff(diff)` / `deserializeDiff(json)` — JSON round-trip

Output is saved as `correction_diff.json` in the encounter's output directory.

## Practice Branding (`client/web/lib/branding.ts`, `client/provider/lib/branding.ts`)

Both the admin web UI and the provider portal fetch branding config from the API (`GET /config/branding`) and apply practice-specific labels. Each has its own copy of the branding loader.

Configure in `config/deployment.yaml`:

```yaml
branding:
  practice_name: "Orthopedic Associates"
  logo_url: "/branding/logo.png"
  primary_color: "#1a5276"
```

Falls back to "AI Scribe" when no branding is configured.
