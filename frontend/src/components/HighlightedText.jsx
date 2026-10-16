// Render note text with evidence spans highlighted.
// spans: [{start, end, key, flagged, active}] in character offsets. Spans can overlap (two fields
// quoting the same sentence), so we cut the text at every span boundary and mark each piece with
// the spans covering it.
export default function HighlightedText({ text, spans }) {
  const valid = spans.filter((s) => s && s.end > s.start);
  const cuts = new Set([0, text.length]);
  valid.forEach((s) => { cuts.add(s.start); cuts.add(s.end); });
  const points = [...cuts].sort((a, b) => a - b);

  const pieces = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    const covering = valid.filter((s) => s.start <= a && s.end >= b);
    const chunk = text.slice(a, b);
    if (covering.length === 0) {
      pieces.push(chunk);
    } else {
      const cls = ["evidence",
        covering.some((s) => s.flagged) ? "flagged" : "",
        covering.some((s) => s.active) ? "active" : ""].join(" ").trim();
      pieces.push(
        <mark key={a} className={cls} data-span={covering[0].key}>{chunk}</mark>
      );
    }
  }
  return <div className="note-text">{pieces}</div>;
}
