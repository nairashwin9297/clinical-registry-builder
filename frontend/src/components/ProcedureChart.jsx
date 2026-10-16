import { useEffect, useRef } from "react";
import { BarController, BarElement, CategoryScale, Chart, Legend, LinearScale, Tooltip } from "chart.js";
import { classLabel } from "../format.js";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

// Read the chart colors from CSS custom properties so light/dark mode stay in one place (styles.css).
function themeColors(el) {
  const css = getComputedStyle(el);
  const v = (name) => css.getPropertyValue(name).trim();
  return { model: v("--series-1"), key: v("--series-2"), text: v("--text-secondary"),
           muted: v("--text-muted"), grid: v("--grid"), axis: v("--axis") };
}

// Horizontal grouped bars: how often each class was predicted by the model vs how often it is in
// the (approximate) answer key. Horizontal because the class names are long.
export default function ProcedureChart({ counts }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const build = () => {
      const c = themeColors(canvas);
      const bar = { borderRadius: 4, borderSkipped: "start", maxBarThickness: 18, borderWidth: 0 };
      return new Chart(canvas, {
        type: "bar",
        data: {
          labels: counts.map((r) => classLabel(r.class_id)),
          datasets: [
            { label: "Model", data: counts.map((r) => r.model), backgroundColor: c.model, ...bar },
            { label: "Answer key (approx.)", data: counts.map((r) => r.answer_key), backgroundColor: c.key, ...bar },
          ],
        },
        options: {
          indexAxis: "y",
          maintainAspectRatio: false,
          // Hover anywhere in a class's row shows both values in one tooltip.
          interaction: { mode: "index", axis: "y", intersect: false },
          plugins: {
            legend: { position: "top", align: "start", labels: { color: c.text, boxWidth: 12, boxHeight: 12 } },
            tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.x} notes` } },
          },
          scales: {
            x: { beginAtZero: true, ticks: { color: c.muted, precision: 0 },
                 grid: { color: c.grid }, border: { color: c.axis },
                 title: { display: true, text: "Notes", color: c.muted } },
            y: { ticks: { color: c.text }, grid: { display: false }, border: { color: c.axis } },
          },
        },
      });
    };

    let chart = build();
    // Rebuild when the OS switches light/dark so the colors follow.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => { chart.destroy(); chart = build(); };
    mq.addEventListener("change", onScheme);
    return () => { mq.removeEventListener("change", onScheme); chart.destroy(); };
  }, [counts]);

  return (
    <div className="chart-box" style={{ height: `${counts.length * 44 + 70}px` }}>
      <canvas ref={canvasRef} role="img"
              aria-label="Bar chart of procedure counts per class, model versus answer key. The same numbers are in the table above." />
    </div>
  );
}
