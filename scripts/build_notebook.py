"""Generate notebooks/extract.ipynb.

The notebook must stay self-contained for Colab, so instead of importing the backend we paste
backend/registry/extraction_core.py into one cell verbatim. Re-run this after editing that module:

    python scripts/build_notebook.py

backend/tests/test_notebook_sync.py fails if the notebook copy is out of date.
"""

import json
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "backend" / "registry" / "extraction_core.py"
OUT = REPO / "notebooks" / "extract.ipynb"

cells = []


def md(src):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": textwrap.dedent(src).strip("\n")})


def code(src, tag, verbatim=False):
    # "tag" lets tests find cells (e.g. the core cell) without depending on cell order.
    source = src if verbatim else textwrap.dedent(src).strip("\n")
    cells.append({"cell_type": "code", "metadata": {"tag": tag}, "execution_count": None,
                  "outputs": [], "source": source})


md("""
# Clinical Notes Registry Builder: LLM extraction

This notebook reads de-identified orthopedic operative notes (`notes.csv`, built from the public
MTSamples dataset) and asks **Gemma 3 4B (instruction-tuned)** to extract four fields per note,
each with an exact evidence quote copied from the note:

| Field | Values |
|---|---|
| `procedure` | one or more of 9 fixed procedure classes |
| `body_part` | short anatomy term, e.g. `knee`, `lumbar spine` |
| `laterality` | `left` / `right` / `bilateral` / `not mentioned` |
| `patient_age` | integer, or `not mentioned` |

Output is `results.json`, which the Django backend imports. The prompt, validation and flag rules are
the same code the backend uses (cell 3 is a copy of `backend/registry/extraction_core.py`).

**Demo only, not for clinical use.**

### Before you run
1. **Runtime → Change runtime type → T4 GPU** (free tier is fine).
2. Accept the Gemma licence at https://huggingface.co/google/gemma-3-4b-it (logged in to Hugging Face).
3. Create a Hugging Face access token (read scope) and add it as a Colab secret named **`HF_TOKEN`**
   (🔑 icon in the left sidebar), with notebook access switched on.
4. Upload `data/notes.csv` from the repo via the 📁 Files panel so it sits at `/content/notes.csv`.
""")

md("## 1. Install packages")
code("""
# Colab already has torch and pandas. Gemma 3 needs a recent transformers; pin it so runs are reproducible.
%pip install -q "transformers==4.57.1" accelerate
""", "install")

md("## 2. Settings")
code("""
import os

MODEL_ID = "google/gemma-3-4b-it"
NOTES_PATH = "notes.csv"
RESULTS_PATH = "results.json"
TEST_RESULTS_PATH = "results_test.json"
SAVE_EVERY = 10          # checkpoint to disk after this many notes

# Optional: save results to Google Drive so they survive a runtime reset
# (files in /content are deleted when Colab recycles the machine).
USE_DRIVE = False
if USE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    out_dir = "/content/drive/MyDrive/clinical-registry-builder"
    os.makedirs(out_dir, exist_ok=True)
    RESULTS_PATH = os.path.join(out_dir, "results.json")
    TEST_RESULTS_PATH = os.path.join(out_dir, "results_test.json")

print("Results will be written to", RESULTS_PATH)
""", "config")

md("""
## 3. Shared extraction logic (prompt, validation, retry, quote matching, flag rules)

**Generated cell: do not edit here.** This is a verbatim copy of `backend/registry/extraction_core.py`,
so Colab results and the app's live Ollama mode use the identical prompt and rules.

* **Malformed JSON / wrong shape:** ask **once more**, telling the model what was wrong. If the second
  reply is also unusable, the note is recorded as `failed` (raw output kept) and the run continues.
* **Procedure value not a class ID, or an empty evidence quote:** same one-time retry. If still wrong,
  the usable fields are kept; invalid values go to `rejected_procedures` and get flagged.
""")
code(CORE.read_text(), "core", verbatim=True)

md("## 4. Log in to Hugging Face (token from Colab secrets)")
code("""
from google.colab import userdata
from huggingface_hub import login

# The token is read from Colab's secret store. Never paste it into the notebook.
try:
    hf_token = userdata.get("HF_TOKEN")
except Exception as e:
    raise RuntimeError("Add your Hugging Face token as a Colab secret named HF_TOKEN "
                       "and enable notebook access (key icon in the left sidebar).") from e
login(token=hf_token)
""", "login")

md("## 5. Load the model")
code("""
import torch
from transformers import AutoProcessor, Gemma3ForConditionalGeneration

assert torch.cuda.is_available(), "No GPU found: Runtime → Change runtime type → T4 GPU"
print("GPU:", torch.cuda.get_device_name(0))

# Gemma 3 4B is published as an image+text model; we only send text.
# bfloat16 halves memory (~8–9 GB), so it fits on a free T4.
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = Gemma3ForConditionalGeneration.from_pretrained(
    MODEL_ID, device_map="auto", dtype=torch.bfloat16
).eval()
# Gemma ships sampling defaults; we decode greedily, so clear them to silence the "not valid flags" warning.
model.generation_config.top_p = None
model.generation_config.top_k = None


def generate(messages, max_new_tokens=MAX_NEW_TOKENS):
    \"\"\"Run one chat turn and return only the newly generated text.\"\"\"
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt",
    ).to(model.device)
    prompt_len = inputs["input_ids"].shape[-1]
    try:
        with torch.inference_mode():
            # do_sample=False = greedy decoding, so the same note gives the same answer every run.
            out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()  # free memory so the next note can run; extract_note records the failure
        raise
    return processor.decode(out[0][prompt_len:], skip_special_tokens=True)
""", "model")

md("## 6. Load the notes")
code("""
import pandas as pd

if not os.path.exists(NOTES_PATH):
    raise FileNotFoundError("notes.csv not found. Upload data/notes.csv via the Files panel (folder icon).")

notes = pd.read_csv(NOTES_PATH)
required = {"note_id", "sample_name", "transcription", "answer_key_procedures_approx"}
missing = required - set(notes.columns)
assert not missing, f"notes.csv is missing columns: {missing}"
print(f"{len(notes)} notes loaded")
notes[["note_id", "sample_name", "answer_key_procedures_approx"]].head()
""", "notes")

md("""
## 7. Run loop with checkpoints

Results are written to disk every `SAVE_EVERY` notes. If Colab disconnects, just re-run this cell and the
run cell: notes that already succeeded are skipped, and failed notes are retried.
""")
code("""
from datetime import datetime, timezone


def load_results(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    if data.get("model") != MODEL_ID or data.get("prompt_version") != PROMPT_VERSION:
        raise RuntimeError(f"{path} was made with a different model/prompt. Rename or delete it first.")
    return data["results"]


def save_results(path, results):
    data = {"model": MODEL_ID, "prompt_version": PROMPT_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "results": sorted(results, key=lambda r: r["note_id"])}
    # Write to a temp file then rename, so a disconnect mid-write can't leave a half-written results.json.
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def run(df, path, fresh=False):
    if fresh and os.path.exists(path):
        os.remove(path)
    # Keep successes from earlier runs; drop earlier failures so they get retried.
    results = [r for r in load_results(path) if r["status"] == "ok"]
    done = {r["note_id"] for r in results}
    todo = df[~df["note_id"].isin(done)]
    print(f"{len(done)} already done, {len(todo)} to process")

    for i, row in enumerate(todo.itertuples(index=False), start=1):
        # int(): pandas gives numpy ints, which json can't serialize.
        rec = extract_note(int(row.note_id), row.transcription, generate)
        results.append(rec)
        note = f"  ({rec['error']})" if rec["error"] else ""
        print(f"[{i}/{len(todo)}] note {rec['note_id']}: {rec['status']} "
              f"in {rec['seconds']}s, attempts={rec['attempts']}{note}")
        if i % SAVE_EVERY == 0:
            save_results(path, results)
            print(f"  checkpoint saved ({len(results)} results)")
    save_results(path, results)
    print(f"Done. {len(results)} results in {path}")
    return results


def preview(results, df):
    \"\"\"Show each field with the flag the backend will give it.\"\"\"
    by_id = df.set_index("note_id")
    for r in results:
        row = by_id.loc[r["note_id"]]
        print(f"\\n=== note {r['note_id']}: {row['sample_name']} ===")
        print("answer key (approx):", row["answer_key_procedures_approx"])
        for x in build_extractions(r, row["transcription"]):
            status = f"flag: {x['flag_reason']}" if x["flagged"] else f"ok {x['match_type']}".strip()
            print(f"  {x['field']:11} {x['value'] or '-':24} {status}")


def flag_rate(results, df):
    \"\"\"Share of extracted fields that will be flagged (same rows/rules as the backend).\"\"\"
    by_id = df.set_index("note_id")
    rows = [x for r in results for x in build_extractions(r, by_id.loc[r["note_id"]]["transcription"])]
    flagged = sum(x["flagged"] for x in rows)
    print(f"preview: {flagged}/{len(rows)} fields flagged ({flagged / max(len(rows), 1):.0%})")
""", "run")

md("""
## 8. Test on 5 notes

Run this first. Check that the replies parse, the procedure classes look sensible against the
(approximate) answer key, and that the quotes are found in the notes. The per-note seconds also tell you
roughly how long the full run will take. Writes to `results_test.json`, not the main results file.
""")
code("""
test_results = run(notes.head(5), TEST_RESULTS_PATH, fresh=True)
preview(test_results, notes)
print()
flag_rate(test_results, notes)
""", "test5")

md("""
## 9. Full run

Saves to `results.json` every 10 notes. Safe to re-run after a disconnect: it resumes where it stopped.
""")
code("""
results = run(notes, RESULTS_PATH)
""", "full")

md("## 10. Summary and download")
code("""
ok = [r for r in results if r["status"] == "ok"]
failed = [r for r in results if r["status"] == "failed"]
print(f"{len(results)} notes: {len(ok)} ok, {len(failed)} failed (JSON failures after one retry)")
print(f"needed a retry: {sum(1 for r in ok if r['attempts'] == 2)}")
print(f"kept with invalid procedure values after retry: {sum(1 for r in ok if r['rejected_procedures'])}")
for r in failed:
    print(f"  note {r['note_id']}: {r['error']}")
flag_rate(results, notes)

from google.colab import files
files.download(RESULTS_PATH)  # then commit it to the repo as data/results.json
""", "summary")


def main():
    nb = {"cells": cells,
          "metadata": {"accelerator": "GPU",
                       "colab": {"provenance": [], "gpuType": "T4"},
                       "kernelspec": {"display_name": "Python 3", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 0}
    for c in nb["cells"]:
        c["source"] = c["source"].splitlines(keepends=True)  # nbformat stores source as a list of lines
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(cells)} cells)")


if __name__ == "__main__":
    main()
