import { describeError, type AnyEngineError, type ErrorContext } from "../lib/errors";

type Props = {
  error: AnyEngineError;
  onRetry?: () => void;
  onSettings?: () => void;
  onSetup?: () => void;
  compact?: boolean;
  context?: ErrorContext;
};

export default function ErrorPanel({ error, onRetry, onSettings, onSetup, compact, context }: Props) {
  const d = describeError(error, context);
  return (
    <div className="err" role="alert" style={compact ? { padding: 12, fontSize: 13 } : undefined}>
      <b>{d.title}</b>
      {d.detail && <div>{d.detail}</div>}
      <div style={{ marginTop: 10 }}>
        {d.action === "retry" && onRetry && <button className="btn ghost" onClick={onRetry}>Dựng lại</button>}
        {d.action === "settings" && onSettings && <button className="btn ghost" onClick={onSettings}>Mở Cài đặt</button>}
        {d.action === "setup" && onSetup && <button className="btn ghost" onClick={onSetup}>Tải lại Claude</button>}
      </div>
    </div>
  );
}
