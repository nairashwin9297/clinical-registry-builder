export const FIELD_LABELS = {
  procedure: "Procedure",
  body_part: "Body part",
  laterality: "Laterality",
  patient_age: "Patient age",
};

// "fracture_fixation" -> "Fracture fixation"
export function classLabel(id) {
  if (!id) return "";
  const s = id.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function pct(x, digits = 0) {
  return x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`;
}

export function score(x) {
  return x === null || x === undefined ? "–" : x.toFixed(2);
}

// Display an extracted value; procedure rows hold class IDs.
export function displayValue(field, value) {
  if (value === "" || value === null || value === undefined) return "—";
  return field === "procedure" ? classLabel(value) : String(value);
}
