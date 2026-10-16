import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { classLabel, displayValue, FIELD_LABELS } from "../format.js";
import HighlightedText from "./HighlightedText.jsx";
import { StatusBadge } from "./ResultsTable.jsx";

// Modal with the full note, its extracted fields, and the evidence highlighted in the text.
export default function NoteDetail({ noteId, version, onClose }) {
  const [note, setNote] = useState(null);
  const [active, setActive] = useState(null);
  const dialogRef = useRef(null);
  const textRef = useRef(null);

  useEffect(() => { api.note(noteId).then(setNote); }, [noteId, version]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function focusEvidence(e) {
    setActive(e.id);
    // Scroll the highlighted quote into view inside the note text.
    requestAnimationFrame(() =>
      textRef.current?.querySelector(`mark[data-span="${e.id}"], mark.active`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
  }

  const spans = note
    ? note.extractions.filter((e) => e.span).map((e) => ({
        start: e.span[0], end: e.span[1], key: e.id, flagged: e.flagged, active: e.id === active }))
    : [];

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="note-title" tabIndex={-1}
           ref={dialogRef} onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {!note ? <p>Loading…</p> : (
          <>
            <h2 id="note-title">{note.sample_name || "(untitled)"} <StatusBadge status={note.status} /></h2>
            <p className="muted small">
              Note {note.external_id} · {note.source === "mtsamples" ? "MTSamples" : "uploaded"}
              {note.model_name && <> · {note.model_name}, prompt {note.prompt_version}, {note.attempts} attempt{note.attempts === 1 ? "" : "s"}</>}
            </p>
            {note.answer_key.length > 0 && (
              <p className="small">Answer key (approximate): {note.answer_key.map(classLabel).join(", ")}</p>
            )}
            {note.extraction_status === "failed" && (
              <div className="error">
                Extraction failed: {note.extraction_error}. Every field is in the review queue.
                {note.raw_outputs.length > 0 && (
                  <details>
                    <summary>Show the model's raw replies ({note.raw_outputs.length})</summary>
                    {note.raw_outputs.map((r, i) => <pre key={i} className="raw">{r}</pre>)}
                  </details>
                )}
              </div>
            )}

            <div className="detail-grid">
              <div>
                <h3>Extracted fields</h3>
                <ul className="fields">
                  {note.extractions.map((e) => (
                    <li key={e.id} className={e.id === active ? "active" : ""}>
                      <button className="linklike" onClick={() => focusEvidence(e)} disabled={!e.span}
                              title={e.span ? "Show evidence in the note" : "No matching quote in the note"}>
                        <span className="field-name">{FIELD_LABELS[e.field]}</span>{" "}
                        <strong>{displayValue(e.field, e.value)}</strong>
                      </button>
                      {e.review && (
                        <div className="small success-text">
                          Corrected to: {e.field === "procedure"
                            ? (e.review.corrected_value ? e.review.corrected_value.split("|").map(classLabel).join(", ") : "not performed")
                            : e.review.corrected_value}
                        </div>
                      )}
                      {e.flagged && <div className="small flag-text">⚑ {e.flag_reason}</div>}
                      {e.evidence_quote && <q className="small quote">{e.evidence_quote}</q>}
                      {e.match_type === "near" && <span className="small muted"> (near-verbatim match)</span>}
                    </li>
                  ))}
                </ul>
              </div>
              <div ref={textRef}>
                <h3>Note text</h3>
                <HighlightedText text={note.transcription} spans={spans} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
