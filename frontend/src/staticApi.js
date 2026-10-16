// The static demo's stand-in for the Django API (GitHub Pages has no server).
// Reads the JSON exported by `python manage.py export_static` and keeps the visitor's corrections in
// localStorage, so they survive a reload but never leave the browser.
import { redcapCsv, registryCsv, reviewQueue, summarize, validateCorrection, withReviews } from "./registryLogic.js";

const DATA = `${import.meta.env.BASE_URL}demo-data/`;
let loaded = null;

async function getJson(name) {
  const res = await fetch(DATA + name);
  if (!res.ok) throw new Error(`Could not load ${name} (${res.status})`);
  return res.json();
}

function load() {
  if (!loaded) {
    loaded = Promise.all([getJson("config.json"), getJson("notes.json"), getJson("metrics.json")])
      .then(([config, notes, metrics]) => ({ config, notes, metrics, classIds: Object.keys(config.procedure_options) }));
  }
  return loaded;
}

// Reviews are stored per data version: a new export (new results) starts with a clean slate instead of
// attaching old corrections to the wrong answers.
const storageKey = (config) => `registry-reviews:${config.data_version}`;

function readReviews(config) {
  try {
    return JSON.parse(localStorage.getItem(storageKey(config))) || {};
  } catch {
    return {}; // storage blocked or corrupt: behave as if nothing was reviewed
  }
}

function writeReviews(config, reviews) {
  try {
    localStorage.setItem(storageKey(config), JSON.stringify(reviews));
  } catch {
    throw new Error("Your browser blocked local storage, so corrections can't be saved.");
  }
}

async function reviewedNotes() {
  const d = await load();
  const reviews = readReviews(d.config);
  return { ...d, reviews, notes: d.notes.map((n) => summarize(withReviews(n, reviews), d.classIds)) };
}

function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const staticApi = {
  config: async () => (await load()).config,
  notes: async () => (await reviewedNotes()).notes,
  note: async (id) => (await reviewedNotes()).notes.find((n) => n.id === id),
  reviewQueue: async (includeReviewed) => reviewQueue((await reviewedNotes()).notes, includeReviewed),
  metrics: async () => {
    const { metrics, notes } = await reviewedNotes();
    // Everything else is review-independent (scores use the model's answers); only this count changes.
    const flagsReviewed = notes.reduce((n, note) => n + note.extractions.filter((e) => e.flagged && e.review).length, 0);
    return { ...metrics, flags_reviewed: flagsReviewed };
  },
  submitReview: async (extractionId, correctedValue) => {
    const d = await load();
    const extraction = d.notes.flatMap((n) => n.extractions).find((e) => e.id === extractionId);
    if (!extraction) throw new Error("Unknown item");
    const value = validateCorrection(extraction.field, correctedValue, d.classIds, d.config.laterality_options);
    const reviews = readReviews(d.config);
    reviews[extractionId] = { corrected_value: value, timestamp: new Date().toISOString() };
    writeReviews(d.config, reviews);
    return { id: extractionId, review: reviews[extractionId] };
  },
  resetReviews: async () => writeReviews((await load()).config, {}),
  download: async (kind) => {
    const { notes, classIds } = await reviewedNotes();
    if (kind === "registry") download("registry.csv", registryCsv(notes, classIds));
    else if (kind === "redcap") download("redcap_import.csv", redcapCsv(notes, classIds));
    else window.location.href = `${DATA}redcap-dictionary.csv`; // static file, same for everyone
  },
};
