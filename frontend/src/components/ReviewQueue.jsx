import { useEffect, useState } from "react";
import { api } from "../api.js";
import { displayValue, FIELD_LABELS } from "../format.js";
import CorrectionInput, { initialValue } from "./CorrectionInput.jsx";
import HighlightedText from "./HighlightedText.jsx";

function ReviewCard({ item, config, onSaved, onOpenNote }) {
  const [value, setValue] = useState(() => initialValue(item, config));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ex = item.excerpt;

  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.submitReview(item.id, value);
      onSaved(item.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="panel review-card">
      <header className="row spread">
        <h2>
          {FIELD_LABELS[item.field]} · <button className="linklike" onClick={() => onOpenNote(item.note.id)}>
            {item.note.sample_name || item.note.external_id}</button>
          <span className="muted small"> (note {item.note.external_id})</span>
        </h2>
        {item.review && <span className="badge ok">Reviewed</span>}
      </header>

      <dl className="facts">
        <dt>AI answer</dt>
        <dd><strong>{displayValue(item.field, item.value)}</strong></dd>
        <dt>Why flagged</dt>
        <dd className="flag-text">⚑ {item.flag_reason}</dd>
        {item.evidence_quote && (<><dt>Quoted evidence</dt><dd><q className="quote">{item.evidence_quote}</q></dd></>)}
      </dl>

      <div className="excerpt">
        {ex.truncated_start && "… "}
        <HighlightedText text={ex.text}
                         spans={ex.highlight ? [{ start: ex.highlight[0], end: ex.highlight[1], key: item.id, active: true }] : []} />
        {ex.truncated_end && " …"}
      </div>

      <CorrectionInput item={item} config={config} value={value} onChange={setValue} />
      <div className="row">
        <button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save correction"}</button>
        {error && <span className="error-text" role="alert">{error}</span>}
      </div>
    </article>
  );
}

export default function ReviewQueue({ config, version, onChange, onOpenNote }) {
  const [data, setData] = useState(null);
  const [showReviewed, setShowReviewed] = useState(false);
  const [savedCount, setSavedCount] = useState(0);

  useEffect(() => { api.reviewQueue(showReviewed).then(setData); }, [version, showReviewed]);

  function onSaved(id) {
    setSavedCount((n) => n + 1);
    if (!showReviewed) {
      // Drop the card right away; refresh in the background updates counts elsewhere.
      setData((d) => ({ ...d, items: d.items.filter((i) => i.id !== id), open: d.open - 1, reviewed: d.reviewed + 1 }));
    }
    onChange();
  }

  if (!data) return <p>Loading…</p>;

  return (
    <section>
      <h1>Review queue</h1>
      <p className="lead">
        Only flagged answers appear here: {data.open} open, {data.reviewed} reviewed. Pick the correct value
        and save. Corrections go into the registry and exports; the accuracy metrics still score the model's
        original answers.
      </p>
      <label className="row">
        <input type="checkbox" checked={showReviewed} onChange={(e) => setShowReviewed(e.target.checked)} />
        Also show items already reviewed
      </label>
      {savedCount > 0 && <p className="success" role="status">Saved {savedCount} correction{savedCount > 1 ? "s" : ""} this session.</p>}
      {data.items.length === 0
        ? <p className="panel">Nothing left to review.</p>
        : data.items.map((item) => (
            <ReviewCard key={item.id} item={item} config={config} onSaved={onSaved} onOpenNote={onOpenNote} />
          ))}
    </section>
  );
}
