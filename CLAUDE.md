# Clinical Notes Registry Builder

## What this project is
An open-source web tool that turns unstructured clinical notes into a structured research registry (a spreadsheet). An LLM reads each note and extracts chosen fields; answers the model is unsure about are flagged for a human to review; results are shown in a dashboard and can be exported.

It is a small portfolio demo inspired by published research on LLM-based procedure extraction from orthopedic operative notes. Keep it modest, honest, and polished. It is NOT a clinical product.

## Hard rules
- Use ONLY public, de-identified data (MTSamples). Never add real patient data.
- Never invent or hardcode metrics. Every number shown in the app or README must be computed from real results.
- Keep scope small: no user accounts, no auth, no multi-user features.
- Build one phase at a time. Before each phase, propose a short plan and wait for approval.
- After each phase: run the tests and the app, confirm it works, then commit with a clear message.
- Explain non-obvious code in short comments. I need to understand and explain this code in interviews.

## Stack
- Backend: Python 3.11+, Django, Django REST Framework, Pytest
- Database: SQLite for local dev, PostgreSQL in production (via DATABASE_URL)
- Frontend: React (Vite, JavaScript, not TypeScript), Chart.js
- LLM extraction: Google Colab notebook using Gemma (small instruction-tuned model, e.g. Gemma 3 4B) via Hugging Face transformers on a free GPU
- Packaging: Docker, GitHub Actions (run tests on push)
- Hosting: one Render service. Django serves the built React files, so there is a single deployed link.

## Folder structure
```
data/           mtsamples.csv (raw, gitignored), notes.csv, results.json
scripts/        prepare_data.py (Phase 1 data prep) + its tests; build_notebook.py (regenerates the
                notebook; pastes in backend/registry/extraction_core.py, the shared prompt/validation/flag rules)
notebooks/      extract.ipynb (runs in Colab)
backend/        Django project + app
frontend/       React app
Dockerfile
.github/workflows/
README.md
```

## Data
- Source: data/mtsamples.csv (Kaggle MTSamples). Columns: description, medical_specialty, sample_name, transcription, keywords.
- Note: medical_specialty values may have leading/trailing spaces; strip them.
- Select ~100 orthopedic notes that are operative notes with clear procedures.
- Fields to extract:
  - procedure (one or more, from a fixed list of ~8-10 common orthopedic procedure classes, chosen in Phase 1 based on what the data actually contains)
  - body_part
  - laterality (left / right / bilateral / not mentioned)
  - patient_age (integer or not mentioned)
- Answer key: derive expected procedure labels from sample_name and keywords. These are approximate ground truth; label them as such everywhere.

## Phases

### Phase 1: Data prep
Script that filters MTSamples, selects ~100 notes, defines the procedure class list, builds answer-key labels, and writes data/notes.csv. Print a summary (counts per class).

### Phase 2: Colab extraction notebook
notebooks/extract.ipynb, fully self-contained:
- First cells install packages and load the model (Hugging Face token needed for Gemma; read it from Colab secrets, never hardcode).
- Reads notes.csv (uploaded via Colab file panel).
- For each note, prompts the model to return ONLY JSON: each field's value plus an exact evidence quote copied from the note.
- Validates and retries malformed JSON once; records failures instead of crashing.
- Saves progress to results.json every 10 notes so a disconnect doesn't lose work.
- Includes a "test on 5 notes" cell before the full run.

### Phase 3: Backend
- Models: Note, Extraction (field, value, evidence_quote, flagged, flag_reason), Review (corrected_value, timestamp).
- Management command to import notes.csv + results.json.
- Flagging rules: evidence quote not found in the note text; value is "not mentioned"; value outside allowed options; JSON failure.
- Metrics: match rate vs answer-key labels (per class precision/recall/F1 and overall), percent flagged.
- REST endpoints: notes list/detail, extractions, review queue, submit correction, metrics, CSV export, REDCap-style CSV export.
- Pytest tests for flagging logic, metrics, and key endpoints.

### Phase 4: Frontend
Four screens:
1. Overview/setup: dataset info and the fields extracted.
2. Results table: one row per note, extracted fields, status (OK / review), click to open note with evidence highlighted.
3. Review queue: flagged items only; show note excerpt, AI answer, flag reason; user picks corrected value and saves.
4. Dashboard: notes processed, % flagged, match rate vs answer key, bar chart of procedure counts, export buttons.
Clean, simple, responsive. Plain readable design, no heavy UI libraries.

### Phase 5: Deploy and polish
- Dockerfile; Django serves React build; production settings via env vars.
- GitHub Actions workflow running Pytest.
- README: what it does, screenshot, how it works, real results, limitations (approximate answer key, small sample, demo only, not for clinical use), how to run locally, "Open in Colab" link for the notebook, credit MTSamples.

## Git
- .gitignore: .env, venv, node_modules, model files, data/mtsamples.csv, build output.
- Small, clear commits after each working step.
