import { useEffect, useState } from "react";
import { api } from "../api.js";
import { classLabel, pct, score } from "../format.js";
import ProcedureChart from "./ProcedureChart.jsx";

function Tile({ label, value, sub }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export default function Dashboard({ version }) {
  const [m, setM] = useState(null);
  useEffect(() => { api.metrics().then(setM); }, [version]);
  if (!m) return <p>Loading…</p>;

  const o = m.procedures.overall;
  const counts = Object.fromEntries(m.procedure_counts.map((r) => [r.class_id, r]));

  return (
    <section>
      <h1>Dashboard</h1>
      <p className="lead">
        Every number here is computed from the stored extraction results; none are typed in. Procedure accuracy compares the model's original answers
        (before any review) with an <strong>approximate</strong> answer key derived from each note's title and
        keywords, so treat it as a rough guide on a small sample of {m.notes_scored} notes.
      </p>

      <div className="tiles">
        <Tile label="Notes processed" value={m.notes_processed}
              sub={`${m.notes_failed} failed extraction${m.notes_failed === 1 ? "" : "s"}`} />
        <Tile label="Fields flagged" value={pct(m.flag_rate, 1)} sub={`${m.fields_flagged} of ${m.fields_total} fields`} />
        <Tile label="Notes needing review" value={pct(m.notes_flagged_rate)}
              sub={`${m.notes_flagged} notes · ${m.flags_reviewed} flags reviewed`} />
        <Tile label="Exact match vs answer key" value={pct(o.exact_match_rate)}
              sub={`${o.exact_match} of ${o.notes} notes: same set of classes`} />
        <Tile label="Procedure F1 (micro)" value={score(o.micro_f1)}
              sub={`precision ${score(o.micro_precision)} · recall ${score(o.micro_recall)} · macro F1 ${score(o.macro_f1)}`} />
      </div>

      <div className="panel">
        <h2>Per-class precision, recall and F1</h2>
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Class</th><th className="num">In answer key</th><th className="num">Predicted</th>
                <th className="num">Correct</th><th className="num">Precision</th><th className="num">Recall</th>
                <th className="num">F1</th>
              </tr>
            </thead>
            <tbody>
              {m.procedures.per_class.map((r) => (
                <tr key={r.class_id}>
                  <th scope="row">{classLabel(r.class_id)}</th>
                  <td className="num">{counts[r.class_id].answer_key}</td>
                  <td className="num">{r.predicted}</td>
                  <td className="num">{r.tp}</td>
                  <td className="num">{score(r.precision)}</td>
                  <td className="num">{score(r.recall)}</td>
                  <td className="num">{score(r.f1)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Overall (micro)</th>
                <td className="num">{o.tp + o.fn}</td><td className="num">{o.tp + o.fp}</td><td className="num">{o.tp}</td>
                <td className="num">{score(o.micro_precision)}</td><td className="num">{score(o.micro_recall)}</td>
                <td className="num">{score(o.micro_f1)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="muted small">
          A note can have several classes. A failed extraction counts as predicting no classes. "–" means undefined
          (e.g. precision for a class the model never predicted).
        </p>
      </div>

      <div className="panel">
        <h2>Procedure counts: model vs answer key</h2>
        <ProcedureChart counts={m.procedure_counts} />
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Why fields were flagged</h2>
          {m.flag_reasons.length === 0 ? <p className="muted">No flags.</p> : (
            <table className="simple">
              <tbody>
                {m.flag_reasons.map((r) => (
                  <tr key={r.reason}><th scope="row">{r.reason}</th><td className="num">{r.count}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="panel">
          <h2>Export</h2>
          <p className="muted">Exports use final values, with review corrections applied.</p>
          <div className="row wrap">
            <button onClick={() => api.download("registry")}>Registry CSV</button>
            <button onClick={() => api.download("redcap")}>REDCap import CSV</button>
            <button className="secondary" onClick={() => api.download("redcapDictionary")}>REDCap data dictionary</button>
          </div>
        </div>
      </div>
    </section>
  );
}
