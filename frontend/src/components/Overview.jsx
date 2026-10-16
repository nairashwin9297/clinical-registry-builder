import { classLabel, FIELD_LABELS } from "../format.js";
import LivePanel from "./LivePanel.jsx";

const FIELD_HELP = {
  procedure: "One or more of the procedure classes below",
  body_part: "Short anatomy term, e.g. knee, lumbar spine",
  laterality: "left / right / bilateral / not mentioned",
  patient_age: "Whole number of years, or not mentioned",
};

export default function Overview({ config, version, onChange }) {
  const imported = config.notes_by_source.mtsamples || 0;
  const uploaded = config.notes_by_source.upload || 0;

  return (
    <section>
      <h1>Overview</h1>
      <p className="lead">
        An LLM reads each orthopedic operative note and fills in a research registry row. Every answer comes
        with an evidence quote copied from the note. Answers that look doubtful are flagged for a person to
        review.
      </p>

      {config.demo_mode ? (
        <div className="panel info">
          <h2>Extraction is precomputed</h2>
          <p>
            This hosted demo shows results computed ahead of time in a Google Colab notebook
            {config.models_used.length > 0 && <> with <code>{config.models_used.join(", ")}</code></>} (prompt{" "}
            {config.prompt_version}). You can browse the results, review flagged answers and export the registry,
            but you can't run new extractions here.
          </p>
          {config.static && (
            <p>
              There is no server behind this page: corrections you make in the review queue are saved only in this
              browser (local storage) and are included in your CSV exports.
            </p>
          )}
          <p>
            To run extraction yourself on your own notes with a local model, see the{" "}
            <a href={config.readme_url} target="_blank" rel="noreferrer">README</a>.
          </p>
        </div>
      ) : (
        <LivePanel config={config} version={version} onChange={onChange} />
      )}

      <div className="grid-2">
        <div className="panel">
          <h2>Dataset</h2>
          <dl className="facts">
            <dt>Notes</dt>
            <dd>{config.notes_total}</dd>
            <dt>Imported from MTSamples</dt>
            <dd>{imported}</dd>
            {uploaded > 0 && (
              <>
                <dt>Uploaded</dt>
                <dd>{uploaded}</dd>
              </>
            )}
          </dl>
          <p className="muted">
            Orthopedic operative notes from MTSamples, a public collection of de-identified sample medical
            transcriptions. The answer key for procedures was derived from each note's title and keywords, so it
            is <strong>approximate</strong>.
          </p>
        </div>

        <div className="panel">
          <h2>Fields extracted</h2>
          <table className="simple">
            <tbody>
              {config.fields.map((f) => (
                <tr key={f}>
                  <th scope="row">{FIELD_LABELS[f]}</th>
                  <td>{FIELD_HELP[f]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h2>Procedure classes</h2>
        <div className="table-scroll">
          <table className="simple">
            <tbody>
              {Object.entries(config.procedure_options).map(([id, desc]) => (
                <tr key={id}>
                  <th scope="row">{classLabel(id)}</th>
                  <td>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h2>When is an answer flagged?</h2>
        <ul>
          <li>The evidence quote isn't found in the note (case, punctuation and spacing are ignored).</li>
          <li>No evidence quote was given.</li>
          <li>The value isn't one of the allowed options.</li>
          <li>
            The answer is "not mentioned" but the note seems to contain it (an age like "45-year-old", or the
            words left/right/bilateral). A missing body part is always flagged.
          </li>
          <li>The model's reply couldn't be parsed even after one retry (every field of that note is flagged).</li>
        </ul>
      </div>
    </section>
  );
}
