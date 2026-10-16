// Registry rules for the static demo, ported from the Django backend (registry/services.py and
// registry/exports.py). In the static build there is no server, so applying the visitor's corrections,
// note status, the review queue and the CSV exports all happen here.
// tests/parity.test.mjs checks this file produces the same CSVs as Django. Keep the two in sync.
// Pure functions only (no browser APIs), so Node can run the tests.

const NOT_MENTIONED = "not mentioned";
const EXCERPT_CONTEXT = 300;
const LATERALITY_CODES = { left: 1, right: 2, bilateral: 3, "not mentioned": 9 };

// Attach the visitor's reviews ({extractionId: {corrected_value, timestamp}}) to a note's extractions.
export function withReviews(note, reviews) {
  return { ...note, extractions: note.extractions.map((e) => ({ ...e, review: reviews[e.id] || null })) };
}

// services.final_values: model answers with corrections applied.
export function finalValues(note, classIds) {
  const out = { procedure: [], body_part: "", laterality: "", patient_age: "" };
  const procedures = new Set();
  for (const e of note.extractions) {
    if (e.field === "procedure") {
      if (e.review) e.review.corrected_value.split("|").filter(Boolean).forEach((c) => procedures.add(c));
      else if (classIds.includes(e.value)) procedures.add(e.value); // unreviewed invalid values are left out
    } else {
      out[e.field] = e.review ? e.review.corrected_value : e.value;
    }
  }
  out.procedure = classIds.filter((c) => procedures.has(c));
  return out;
}

const needsReview = (e) => e.flagged && !e.review;

// services.note_status
export function noteStatus(note) {
  if (note.extraction_status === "pending") return "pending";
  return note.extractions.some(needsReview) ? "review" : "ok";
}

// Recompute the summary fields that depend on reviews (views.note_summary).
export function summarize(note, classIds) {
  const flagged = note.extractions.filter((e) => e.flagged);
  return { ...note, status: noteStatus(note), values: finalValues(note, classIds),
           flags: flagged.length, open_flags: flagged.filter(needsReview).length };
}

// views.excerpt: a window of the note around the evidence span.
export function excerpt(text, span) {
  if (!span) {
    return { text: text.slice(0, 2 * EXCERPT_CONTEXT), highlight: null,
             truncated_start: false, truncated_end: text.length > 2 * EXCERPT_CONTEXT };
  }
  const start = Math.max(0, span[0] - EXCERPT_CONTEXT);
  const end = Math.min(text.length, span[1] + EXCERPT_CONTEXT);
  return { text: text.slice(start, end), highlight: [span[0] - start, span[1] - start],
           truncated_start: start > 0, truncated_end: end < text.length };
}

// views.review_queue
export function reviewQueue(notes, includeReviewed) {
  const items = [];
  let open = 0;
  let reviewed = 0;
  for (const n of notes) {
    for (const e of n.extractions) {
      if (!e.flagged) continue;
      if (e.review) reviewed++; else open++;
      if (e.review && !includeReviewed) continue;
      items.push({ ...e, note: { id: n.id, external_id: n.external_id, sample_name: n.sample_name,
                                 extraction_status: n.extraction_status },
                   excerpt: excerpt(n.transcription, e.span) });
    }
  }
  return { items, open, reviewed };
}

// services.validate_correction: returns the string to store, or throws Error.
export function validateCorrection(field, value, classIds, lateralityOptions) {
  if (field === "procedure") {
    if (!Array.isArray(value)) throw new Error("procedure correction must be a list of class IDs");
    const bad = value.filter((v) => !classIds.includes(v));
    if (bad.length) throw new Error(`not allowed procedure classes: ${bad.join(", ")}`);
    return classIds.filter((c) => value.includes(c)).join("|");
  }
  const v = String(value ?? "").trim().toLowerCase();
  if (field === "laterality") {
    if (!lateralityOptions.includes(v)) throw new Error(`laterality must be one of ${lateralityOptions.join(", ")}`);
    return v;
  }
  if (field === "patient_age") {
    if (v === NOT_MENTIONED) return v;
    if (!/^\d+$/.test(v) || Number(v) > 120) throw new Error("age must be a whole number from 0 to 120, or 'not mentioned'");
    return String(Number(v));
  }
  if (field === "body_part") {
    if (!v || v.length > 100) throw new Error("body part must be 1-100 characters");
    return v;
  }
  throw new Error(`unknown field ${field}`);
}

// --- CSV exports (exports.py). Matches Python's csv module: quote only when needed, \r\n line ends. ---

function csvCell(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(header, rows) {
  return [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

export function registryCsv(notes, classIds) {
  const header = ["note_id", "sample_name", "procedures", "body_part", "laterality", "patient_age", "status",
                  "answer_key_procedures_approx"];
  const rows = notes.map((n) => {
    const v = finalValues(n, classIds);
    return [n.external_id, n.sample_name, v.procedure.join("|"), v.body_part, v.laterality, v.patient_age,
            noteStatus(n), n.answer_key.join("|")];
  });
  return toCsv(header, rows);
}

export function redcapCsv(notes, classIds) {
  const header = ["record_id", "sample_name", ...classIds.map((_, i) => `procedure___${i + 1}`),
                  "body_part", "laterality", "patient_age", "registry_complete"];
  const rows = notes.map((n) => {
    const v = finalValues(n, classIds);
    const age = String(v.patient_age);
    return [n.external_id, n.sample_name, ...classIds.map((c) => (v.procedure.includes(c) ? 1 : 0)),
            v.body_part, LATERALITY_CODES[v.laterality] ?? "", /^\d+$/.test(age) ? age : "",
            noteStatus(n) === "ok" ? 2 : 1]; // REDCap form status: 2 = Complete, 1 = Unverified
  });
  return toCsv(header, rows);
}
