# Test Data

This folder contains medical audio samples and reference SOAP notes for testing the AI Scribe pipeline.

**⚠️ This folder is gitignored. It contains PHI and must never be committed to version control.**

## Expected Structure

```
data/
├── dictation/                   # Single-speaker physician dictations
│   ├── sample_001/
│   │   ├── audio.mp3            # Original dictation audio
│   │   ├── transcript_medasr.txt    # MedASR transcript (if available)
│   │   ├── transcript_whisper.txt   # Whisper transcript (if available)
│   │   ├── transcript_cleaned.txt   # Post-processor output (generated)
│   │   └── soap_note.txt           # Gold-standard SOAP note (for evaluation)
│   ├── sample_002/
│   └── ...
│
├── conversation/                # Multi-speaker ambient encounters
│   ├── sample_001/
│   │   ├── audio.mp3            # Doctor-patient conversation
│   │   ├── transcript.txt       # Reference transcript (if available)
│   │   └── soap_note.txt        # Gold-standard SOAP note
│   ├── sample_002/
│   └── ...
│
└── README.md                    # This file
```

## Usage

Place your audio files and reference transcripts/notes in the appropriate subfolders.
The pipeline will read from here during testing and benchmarking.

Generated outputs (cleaned transcripts, AI-generated notes) will be written alongside
the source files for easy comparison.
