import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { classLabel } from "../format.js";

export function StatusBadge({ status }) {
  const label = { ok: "OK", review: "Review", pending: "Pending" }[status] || status;
  return <span className={`badge ${status}`}>{label}</span>;
}

export default function ResultsTable({ version, onOpenNote }) {
  const [notes, setNotes] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  useEffect(() => { api.notes().then(setNotes); }, [version]);

  const shown = useMemo(() => {
    if (!notes) return [];
    const q = query.trim().toLowerCase();
    return notes.filter((n) =>
      (filter === "all" || n.status === filter) &&
      (!q || n.sample_name.toLowerCase().includes(q) || n.external_id.includes(q)));
  }, [notes, filter, query]);

  if (!notes) return <p>Loading…</p>;
  const count = (s) => notes.filter((n) => n.status === s).length;

  return (
    <section>
      <h1>Results</h1>
      <p className="lead">
        One row per note. Values include any corrections made in the review queue. Click a row to read the note
        with its evidence highlighted.
      </p>

      <div className="row filters">
        <div role="group" aria-label="Filter by status" className="segmented">
          {[["all", `All (${notes.length})`], ["review", `Review (${count("review")})`], ["ok", `OK (${count("ok")})`],
            ...(count("pending") ? [["pending", `Pending (${count("pending")})`]] : [])].map(([id, label]) => (
            <button key={id} className={filter === id ? "on" : ""} aria-pressed={filter === id}
                    onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
        <input type="search" placeholder="Search by name or ID" value={query} aria-label="Search notes"
               onChange={(e) => setQuery(e.target.value)} />
      </div>

      <div className="table-scroll">
        <table className="data clickable">
          <thead>
            <tr>
              <th>ID</th><th>Note</th><th>Procedures</th><th>Body part</th><th>Laterality</th>
              <th className="num">Age</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((n) => (
              <tr key={n.id} tabIndex={0} onClick={() => onOpenNote(n.id)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpenNote(n.id))}>
                <td className="mono">{n.external_id}</td>
                <td>{n.sample_name || <span className="muted">(untitled)</span>}</td>
                <td>{n.values.procedure.length ? n.values.procedure.map(classLabel).join(", ") : <span className="muted">—</span>}</td>
                <td>{n.values.body_part || "—"}</td>
                <td>{n.values.laterality || "—"}</td>
                <td className="num">{n.values.patient_age || "—"}</td>
                <td>
                  <StatusBadge status={n.status} />
                  {n.open_flags > 0 && <span className="muted small"> {n.open_flags} flag{n.open_flags > 1 ? "s" : ""}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="muted">No notes match.</p>}
      </div>
    </section>
  );
}
