const STEPS = ["Chuẩn bị clip", "AI đang dựng", "Xuất video", "Xong"];

export function stepIndex(progress: number, done = false): number {
  if (done) return 3;
  if (progress < 0.3) return 0;
  if (progress < 0.9) return 1;
  return 2;
}

export default function ProgressSteps({ progress, label, done = false }: { progress: number; label?: string; done?: boolean }) {
  const cur = stepIndex(progress, done);
  return (
    <ul className="steps">
      {STEPS.map((s, i) => {
        const cls = i < cur || (done && i === 3) ? "done" : i === cur ? "cur" : "";
        return (
          <li key={s} className={cls}>
            <span className="d">{cls === "done" ? "✓" : ""}</span>
            {s}
            {i === cur && label && !done && <small>{label}</small>}
          </li>
        );
      })}
    </ul>
  );
}
