import { useEffect, useRef, useState } from "react";
import { Eye, HelpCircle, ListChecks, MessagesSquare, Send, Square, Wand2 } from "lucide-react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import type { EngineJob } from "../lib/engine";
import ErrorPanel from "./ErrorPanel";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import { MAX_CHAT } from "../lib/defaults";
import type { ChatMessage, ChatPlan } from "../lib/types";

type Props = {
  /** The project folder; null while no clip has been added yet. */
  dir: string | null;
  /** Files are still being copied: no turn can start yet. */
  busy: boolean;
  /** Called before every turn: waits for the project sync and saves the voiceover; null = do not send. */
  prepare: () => Promise<string | null>;
  /** Shows a "Bắt đầu edit" button on the latest plan. Leave out when the screen has its own start button. */
  onStart?: (plan: ChatPlan) => void;
  /** Reports the latest plan (null = none yet) and whether a turn is running, for a start button outside the chat. */
  onState?: (s: { plan: ChatPlan | null; sending: boolean }) => void;
  onSettings: () => void;
  onSetup: () => void;
};

/** Chat with the editing assistant: it asks what is unclear, then gives a plan the customer starts with "Bắt đầu edit". */
export default function ChatPanel({ dir, busy, prepare, onStart, onState, onSettings, onSetup }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [step, setStep] = useState("");
  const [err, setErr] = useState<AnyEngineError | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const job = useRef<EngineJob | null>(null);
  const stopped = useRef(false);
  const opened = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // A turn must not keep burning Claude after the screen is gone.
  useEffect(() => () => { void job.current?.cancel(); }, []);

  useEffect(() => {
    if (!dir) return;
    let alive = true;
    (async () => {
      let saved: ChatMessage[] = [];
      try { saved = (await api.readChat(dir)) ?? []; } catch { /* no chat yet */ }
      if (!alive) return;
      setMessages(saved); setLoadedFor(dir);
    })();
    return () => { alive = false; };
  }, [dir]);

  // First time a project with clips has no chat: the assistant opens with what it sees in the clips.
  useEffect(() => {
    if (!dir || loadedFor !== dir || busy || sending || messages.length > 0 || opened.current === dir) return;
    opened.current = dir;
    void send("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dir, loadedFor, busy, messages.length]);

  useEffect(() => { bottom.current?.scrollIntoView?.({ block: "end" }); }, [messages.length, sending]);

  async function send(raw: string) {
    const text = raw.trim();
    if (sending || text.length > MAX_CHAT) return;
    if (!text && messages.length > 0) return;
    setErr(null); setFailed(null);
    const d = await prepare();
    if (!d) return;
    const mine: ChatMessage | null = text ? { role: "user", text, ts: Date.now() / 1000 } : null;
    if (mine) setMessages((m) => [...m, mine]);
    setDraft(""); setSending(true); setStep(""); stopped.current = false;
    try {
      const reply = await engine.chat(d, text, (e) => { if (e.type === "step") setStep(e.label); }, (j) => { job.current = j; });
      setMessages((m) => [...m, reply]);
    } catch (e) {
      // Nothing was saved for a failed turn: take the message back into the box so it can be sent again.
      if (mine) setMessages((m) => m.filter((x) => x !== mine));
      setDraft(text);
      if (!stopped.current) { setErr(toEngineError(e)); setFailed(text); }
    } finally {
      job.current = null; setSending(false); setStep("");
    }
  }

  function stop() {
    stopped.current = true;
    void job.current?.cancel();
  }

  const lastAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  })();
  const latestPlan = lastAssistant >= 0 ? (messages[lastAssistant] as Extract<ChatMessage, { role: "assistant" }>).plan ?? null : null;
  const onStateRef = useRef(onState);
  onStateRef.current = onState;
  useEffect(() => { onStateRef.current?.({ plan: latestPlan, sending }); }, [latestPlan, sending]);
  const canSend = !!dir && !busy && !sending && draft.trim() !== "" && draft.length <= MAX_CHAT;

  return (
    <div className="chat">
      <div className="chatlog" role="log" aria-label="Trò chuyện với AI">
        {!dir && <ChatEmpty />}
        {dir && busy && messages.length === 0 && <div className="sc-empty"><span className="spin" /> Đang chép file…</div>}
        {messages.map((m, i) => (
          <div key={i} className={"msg " + (m.role === "user" ? "me" : "ai")}>
            <div className="bubble">{m.text}</div>
            {m.role === "assistant" && m.plan && (
              <PlanCard plan={m.plan} latest={i === lastAssistant} disabled={sending || busy}
                onStart={onStart ? () => onStart(m.plan!) : undefined} />
            )}
            {m.role === "assistant" && i === lastAssistant && !sending && m.suggestions.length > 0 && (
              <div className="sugg">
                {m.suggestions.map((s) => (
                  <button key={s} className="chip" disabled={busy} onClick={() => void send(s)}>{s}</button>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="msg ai" aria-live="polite">
            <div className="bubble typing"><span className="spin" /> {step || "AI đang trả lời…"}
              <button className="linkbtn" onClick={stop}><Square size={12} aria-hidden />Dừng</button>
            </div>
          </div>
        )}
        <div ref={bottom} />
      </div>
      {err && (
        <div style={{ margin: "8px 0" }}>
          <ErrorPanel compact error={err} onSettings={onSettings} onSetup={onSetup} retryLabel="Gửi lại"
            onRetry={failed !== null ? () => void send(failed) : undefined} />
        </div>
      )}
      <div className="chatin">
        <textarea aria-label="Tin nhắn cho AI" value={draft} disabled={!dir} maxLength={MAX_CHAT}
          placeholder={dir ? "Nhắn cho AI: độ dài, hook, đoạn nào giữ/bỏ… (Enter để gửi, Shift+Enter xuống dòng)" : "Thêm clip trước"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // isComposing: Vietnamese input methods use Enter to finish a word
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (canSend) void send(draft);
            }
          }} />
        <button className="btn primary" aria-label="Gửi" disabled={!canSend} onClick={() => void send(draft)}><Send size={16} aria-hidden /></button>
      </div>
    </div>
  );
}

const TILES = [
  { icon: Eye, title: "Hiểu clip", text: "Đọc lời nói và cảnh trong từng clip" },
  { icon: HelpCircle, title: "Hỏi lại", text: "Hỏi 1–2 câu nếu còn thiếu thông tin" },
  { icon: ListChecks, title: "Ra kế hoạch", text: "Độ dài, hook, đoạn giữ/bỏ, CTA" },
];

function ChatEmpty() {
  return (
    <div className="chatempty">
      <div className="ic"><MessagesSquare aria-hidden /></div>
      <b>Thêm clip để trò chuyện với AI về cách dựng</b>
      <p>Sau khi thêm clip ở bước 1, AI xem nội dung, hỏi thêm cách bạn muốn rồi đưa kế hoạch dựng.</p>
      <div className="tiles">
        {TILES.map(({ icon: I, title, text }) => (
          <div className="tile" key={title}><I aria-hidden /><b>{title}</b><small>{text}</small></div>
        ))}
      </div>
    </div>
  );
}

function PlanCard({ plan, latest, disabled, onStart }: { plan: ChatPlan; latest: boolean; disabled: boolean; onStart?: () => void }) {
  return (
    <div className={"plan" + (latest ? " on" : "")}>
      <b>Kế hoạch dựng</b>
      <ul>{plan.summary.map((s, k) => <li key={k}>{s}</li>)}</ul>
      {latest && !onStart ? <div className="hint">Bấm “Bắt đầu edit” ở trên, hoặc nhắn tiếp để sửa kế hoạch</div>
      : latest && onStart ? (
        <div className="planrow">
          <button className="btn primary" disabled={disabled} onClick={onStart}><Wand2 size={16} aria-hidden />Bắt đầu edit</button>
          <span className="hint">hoặc nhắn tiếp để sửa kế hoạch</span>
        </div>
      ) : <div className="hint">Kế hoạch cũ</div>}
    </div>
  );
}
