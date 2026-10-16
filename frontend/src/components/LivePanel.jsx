import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Live mode (DEMO_MODE=false): upload a CSV of notes, then run extraction note by note against
// the local Ollama model. Each note is one request, so progress shows as it goes and Stop works
// between notes.
export default function LivePanel({ config, version, onChange }) {
  const [status, setStatus] = useState(null);
  const [pending, setPending] = useState([]);
  const [uploadMsg, setUploadMsg] = useState(null);
  const [run, setRun] = useState(null); // {done, total, failed, current, error}
  const stopRef = useRef(false);

  useEffect(() => {
    api.liveStatus().then(setStatus).catch((e) => setStatus({ reachable: false, error: e.message }));
    api.notes().then((notes) => setPending(notes.filter((n) => n.extraction_status === "pending")));
  }, [version]);

  async function onUpload(e) {
    e.preventDefault();
    const file = e.target.elements.file.files[0];
    if (!file) return;
    setUploadMsg(null);
    try {
      const res = await api.uploadNotes(file);
      setUploadMsg({ ok: true, text: `Added ${res.created} notes.` });
      e.target.reset();
      onChange();
    } catch (err) {
      setUploadMsg({ ok: false, text: err.message, details: err.details });
    }
  }

  async function runAll() {
    stopRef.current = false;
    const todo = [...pending];
    let done = 0;
    let failed = 0;
    for (const note of todo) {
      if (stopRef.current) break;
      setRun({ done, total: todo.length, failed, current: note.sample_name || note.external_id });
      try {
        const result = await api.runExtraction(note.id);
        if (result.extraction_status === "failed") failed++;
        done++;
      } catch (err) {
        // Ollama unreachable etc.: stop rather than burn through every note.
        setRun({ done, total: todo.length, failed, error: err.message });
        onChange();
        return;
      }
    }
    setRun({ done, total: todo.length, failed, current: null });
    onChange();
  }

  const running = run && run.current;
  const ready = status?.reachable && status?.model_available;

  return (
    <div className="panel info">
      <h2>Live extraction (local Ollama)</h2>
      {status === null ? (
        <p className="muted">Checking Ollama…</p>
      ) : ready ? (
        <p>
          Connected to Ollama at <code>{status.url}</code>, model <code>{status.model}</code>.
        </p>
      ) : (
        <div className="error">
          {status.reachable
            ? <>Ollama is running, but model <code>{status.model}</code> isn't pulled. Run{" "}
                <code>ollama pull {status.model}</code>.</>
            : <>Can't reach Ollama at <code>{status.url || "the configured URL"}</code>. Start it with{" "}
                <code>ollama serve</code>. ({status.error})</>}
        </div>
      )}

      <form onSubmit={onUpload} className="row">
        <label>
          {/* One span so the label's flex column keeps the description on one wrapped line. */}
          <span>
            Upload notes (CSV with a <code>transcription</code> column; optional <code>note_id</code>,{" "}
            <code>sample_name</code>, <code>answer_key_procedures_approx</code>)
          </span>
          <input type="file" name="file" accept=".csv,text/csv" />
        </label>
        <button type="submit">Upload</button>
      </form>
      {uploadMsg && (
        <div className={uploadMsg.ok ? "success" : "error"} role="status">
          {uploadMsg.text}
          {uploadMsg.details?.length > 0 && <ul>{uploadMsg.details.map((d) => <li key={d}>{d}</li>)}</ul>}
        </div>
      )}

      <div className="row">
        <button onClick={runAll} disabled={!ready || running || pending.length === 0}>
          Run extraction on {pending.length} pending note{pending.length === 1 ? "" : "s"}
        </button>
        {running && <button className="secondary" onClick={() => (stopRef.current = true)}>Stop after this note</button>}
      </div>
      {run && (
        <p role="status">
          {running ? `Extracting ${run.done + 1} of ${run.total}: ${run.current}…` : `Processed ${run.done} of ${run.total}.`}
          {run.failed > 0 && ` ${run.failed} failed (in the review queue).`}
          {run.error && <span className="error-text"> Stopped: {run.error}</span>}
        </p>
      )}
      <p className="muted">
        Uses the same prompt ({config.prompt_version}) and validation as the Colab notebook. A note can take
        from seconds to minutes depending on your machine.
      </p>
    </div>
  );
}
