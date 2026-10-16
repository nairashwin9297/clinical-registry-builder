import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Overview from "./components/Overview.jsx";
import ResultsTable from "./components/ResultsTable.jsx";
import ReviewQueue from "./components/ReviewQueue.jsx";
import Dashboard from "./components/Dashboard.jsx";
import NoteDetail from "./components/NoteDetail.jsx";

const SCREENS = [
  { id: "overview", label: "Overview" },
  { id: "results", label: "Results" },
  { id: "review", label: "Review queue" },
  { id: "dashboard", label: "Dashboard" },
];

// The current screen lives in the URL hash (#results etc.) so reload and the back button work,
// without pulling in a router library.
function screenFromHash() {
  const id = window.location.hash.replace("#", "");
  return SCREENS.some((s) => s.id === id) ? id : "overview";
}

export default function App() {
  const [screen, setScreen] = useState(screenFromHash);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [openNoteId, setOpenNoteId] = useState(null);
  // Bumped after any change (review saved, extraction run) so screens refetch their data.
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    const onHash = () => setScreen(screenFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message));
  }, [version]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Clinical Notes Registry Builder</strong>
          <span className="tag">{config ? (config.demo_mode ? "Demo" : "Live mode") : ""}</span>
        </div>
        <nav aria-label="Screens">
          {SCREENS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className={screen === s.id ? "active" : ""}
               aria-current={screen === s.id ? "page" : undefined}>
              {s.label}
            </a>
          ))}
        </nav>
      </header>

      <main>
        {error && <p className="error">Could not reach the API: {error}</p>}
        {config && screen === "overview" && <Overview config={config} version={version} onChange={refresh} />}
        {config && screen === "results" && <ResultsTable version={version} onOpenNote={setOpenNoteId} />}
        {config && screen === "review" && (
          <ReviewQueue config={config} version={version} onChange={refresh} onOpenNote={setOpenNoteId} />
        )}
        {config && screen === "dashboard" && <Dashboard version={version} />}
      </main>

      {openNoteId !== null && (
        <NoteDetail noteId={openNoteId} version={version} onClose={() => setOpenNoteId(null)} />
      )}

      <footer>
        Demo only, not for clinical use. Notes are public, de-identified samples from MTSamples.
      </footer>
    </div>
  );
}
