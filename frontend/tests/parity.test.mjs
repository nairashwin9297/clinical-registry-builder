// The static demo re-implements a few backend rules in src/registryLogic.js. These tests check them
// against the Django output exported by `python manage.py export_static` (run that first).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { noteStatus, redcapCsv, registryCsv, reviewQueue, summarize, validateCorrection, withReviews }
  from "../src/registryLogic.js";

const dir = new URL("../public/demo-data/", import.meta.url);
const read = (name) => readFileSync(new URL(name, dir), "utf8");
const config = JSON.parse(read("config.json"));
const notes = JSON.parse(read("notes.json"));
const classIds = Object.keys(config.procedure_options);
const metrics = JSON.parse(read("metrics.json"));

test("registry CSV matches Django's export", () => {
  assert.equal(registryCsv(notes, classIds), read("registry.csv"));
});

test("REDCap CSV matches Django's export", () => {
  assert.equal(redcapCsv(notes, classIds), read("redcap.csv"));
});

test("status and review queue match Django's numbers", () => {
  const flaggedNotes = notes.filter((n) => noteStatus(n) === "review").length;
  assert.equal(flaggedNotes, metrics.notes_flagged);
  const q = reviewQueue(notes, false);
  assert.equal(q.open, metrics.fields_flagged);
  assert.equal(q.items.length, metrics.fields_flagged);
  assert.equal(q.reviewed, 0);
});

test("a correction is applied to the registry and leaves the queue", () => {
  const failed = notes.find((n) => n.extraction_status === "failed");
  const proc = failed.extractions.find((e) => e.field === "procedure");
  const reviews = { [proc.id]: { corrected_value: "arthroscopy", timestamp: "t" } };
  const all = notes.map((n) => withReviews(n, reviews));
  const note = summarize(all.find((n) => n.id === failed.id), classIds);
  assert.deepEqual(note.values.procedure, ["arthroscopy"]);
  assert.equal(note.open_flags, 3);
  const q = reviewQueue(all, false);
  assert.equal(q.open, metrics.fields_flagged - 1);
  assert.equal(q.reviewed, 1);
});

test("correction validation mirrors the backend", () => {
  const lat = config.laterality_options;
  assert.equal(validateCorrection("procedure", ["spinal_fusion", "arthroplasty"], classIds, lat), "arthroplasty|spinal_fusion");
  assert.equal(validateCorrection("procedure", [], classIds, lat), "");
  assert.equal(validateCorrection("patient_age", " 045 ", classIds, lat), "45");
  assert.equal(validateCorrection("patient_age", "Not mentioned", classIds, lat), "not mentioned");
  assert.equal(validateCorrection("body_part", " Knee ", classIds, lat), "knee");
  for (const [field, value] of [["procedure", ["made_up"]], ["procedure", "arthroscopy"], ["laterality", "anterior"],
                                ["patient_age", "old"], ["patient_age", "200"], ["body_part", ""]]) {
    assert.throws(() => validateCorrection(field, value, classIds, lat), `${field}=${value}`);
  }
});
