import { classLabel } from "../format.js";

const BODY_PARTS = ["knee", "hip", "shoulder", "elbow", "wrist", "hand", "finger", "thumb", "foot", "ankle",
  "cervical spine", "thoracic spine", "lumbar spine"];

// The right input for each field. `value` is what the reviewer is editing:
// procedure -> array of class IDs; others -> string.
export default function CorrectionInput({ item, config, value, onChange }) {
  const id = `fix-${item.id}`;

  if (item.field === "procedure") {
    const toggle = (cid) => onChange(value.includes(cid) ? value.filter((c) => c !== cid) : [...value, cid]);
    return (
      <fieldset className="checks">
        <legend>Correct procedure classes for this item (none selected = not performed)</legend>
        {Object.keys(config.procedure_options).map((cid) => (
          <label key={cid}>
            <input type="checkbox" checked={value.includes(cid)} onChange={() => toggle(cid)} /> {classLabel(cid)}
          </label>
        ))}
      </fieldset>
    );
  }

  if (item.field === "laterality") {
    return (
      <fieldset className="checks inline">
        <legend>Correct laterality</legend>
        {config.laterality_options.map((opt) => (
          <label key={opt}>
            <input type="radio" name={id} checked={value === opt} onChange={() => onChange(opt)} /> {opt}
          </label>
        ))}
      </fieldset>
    );
  }

  if (item.field === "patient_age") {
    const notMentioned = value === "not mentioned";
    return (
      <div className="row">
        <label htmlFor={id}>Correct age</label>
        <input id={id} type="number" min="0" max="120" inputMode="numeric" disabled={notMentioned}
               value={notMentioned ? "" : value} onChange={(e) => onChange(e.target.value)} />
        <label>
          <input type="checkbox" checked={notMentioned} onChange={(e) => onChange(e.target.checked ? "not mentioned" : "")} />
          {" "}not mentioned
        </label>
      </div>
    );
  }

  return (
    <div className="row">
      <label htmlFor={id}>Correct body part</label>
      <input id={id} list={`${id}-list`} value={value} onChange={(e) => onChange(e.target.value)} />
      <datalist id={`${id}-list`}>{BODY_PARTS.map((b) => <option key={b} value={b} />)}</datalist>
    </div>
  );
}

// Starting value for the editor: the current correction if any, else the model's answer when usable.
export function initialValue(item, config) {
  const reviewed = item.review?.corrected_value;
  if (item.field === "procedure") {
    if (reviewed !== undefined) return reviewed ? reviewed.split("|") : [];
    return item.value in config.procedure_options ? [item.value] : [];
  }
  if (reviewed !== undefined) return reviewed;
  if (item.field === "laterality") return config.laterality_options.includes(item.value) ? item.value : "";
  if (item.field === "patient_age") return /^\d+$/.test(item.value) || item.value === "not mentioned" ? item.value : "";
  return item.value;
}
