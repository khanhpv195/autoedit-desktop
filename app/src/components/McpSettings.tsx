import { useCallback, useEffect, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { toEngineError } from "../lib/errors";
import type { McpServer, McpTool } from "../lib/types";
import { useStore } from "../state/store";

const NAME_RE = /^[a-z0-9][a-z0-9-]{0,30}$/;
const MAX = 10;

/**
 * Shell-like split: whitespace separates, "double" and 'single' quotes group (also inside a word,
 * as in --opt="a b"), and a backslash escapes a quote, backslash or space. Any other backslash
 * stays literal so Windows paths survive.
 */
export function splitArgs(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  let started = false;
  let quote: '"' | "'" | null = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    const n = text[i + 1];
    if (c === "\\" && n !== undefined && (quote === "'" ? false : quote === '"' ? n === '"' || n === "\\" : /["'\\\s]/.test(n))) {
      cur += n; started = true; i++;
    } else if (quote) {
      if (c === quote) quote = null; else cur += c;
    } else if (c === '"' || c === "'") {
      quote = c; started = true;
    } else if (/\s/.test(c)) {
      if (started) { out.push(cur); cur = ""; started = false; }
    } else { cur += c; started = true; }
  }
  if (started) out.push(cur);
  return out;
}
/** Inverse of splitArgs: quote only when needed, so save -> edit -> save keeps every argument. */
export function joinArgs(args: string[]): string {
  return args.map((a) => (a !== "" && /^[\w@%+=:,./-]+$/.test(a) ? a : `"${a.replace(/(["\\])/g, "\\$1")}"`)).join(" ");
}

type Row = { key: string; value: string };
type Form = {
  isNew: boolean; name: string; enabled: boolean; transport: "stdio" | "http";
  command: string; args: string; url: string; rows: Row[]; saved: Set<string>;
};
type CheckState = { busy: boolean; tools?: McpTool[]; error?: string };

function blank(): Form {
  return { isNew: true, name: "", enabled: true, transport: "stdio", command: "", args: "", url: "", rows: [], saved: new Set() };
}
function fromServer(s: McpServer): Form {
  const keys = (s.transport === "stdio" ? s.envKeys : s.headerKeys) ?? [];
  return {
    isNew: false, name: s.name, enabled: s.enabled, transport: s.transport, command: s.command ?? "",
    args: joinArgs(s.args ?? []), url: s.url ?? "", rows: keys.map((key) => ({ key, value: "" })), saved: new Set(keys),
  };
}

export default function McpSettings() {
  const { notify } = useStore();
  const [servers, setServers] = useState<McpServer[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, CheckState>>({});

  const reload = useCallback(async () => {
    try { setServers((await api.mcpList()) ?? []); } catch (e) { notify(toEngineError(e).message); }
  }, [notify]);
  useEffect(() => { void reload(); }, [reload]);

  async function toggle(s: McpServer) {
    try { await api.mcpSave({ ...s, enabled: !s.enabled }, {}); await reload(); }
    catch (e) { notify(toEngineError(e).message); }
  }

  async function check(name: string) {
    setChecks((c) => ({ ...c, [name]: { busy: true } }));
    try {
      const tools = await engine.mcpCheck(name);
      setChecks((c) => ({ ...c, [name]: { busy: false, tools } }));
    } catch (e) {
      setChecks((c) => ({ ...c, [name]: { busy: false, error: toEngineError(e).message || "Không kết nối được" } }));
    }
  }

  async function remove(name: string) {
    if (!window.confirm(`Xóa MCP "${name}"? Các khóa đã lưu cũng bị xóa.`)) return;
    try { await api.mcpDelete(name); await reload(); } catch (e) { notify(toEngineError(e).message); }
  }

  async function submit() {
    if (!form) return;
    const name = form.name.trim();
    if (!NAME_RE.test(name) || name === "autoedit") {
      setFormErr("Tên chỉ gồm chữ thường không dấu, số, dấu gạch ngang (tối đa 31 ký tự) và không được là autoedit");
      return;
    }
    if (form.isNew && servers.some((s) => s.name === name)) { setFormErr("Đã có MCP trùng tên"); return; }
    if (form.transport === "stdio" && !form.command.trim()) { setFormErr("Nhập lệnh chạy MCP"); return; }
    if (form.transport === "http" && !/^https?:\/\//.test(form.url.trim())) { setFormErr("URL phải bắt đầu bằng http:// hoặc https://"); return; }
    const rows = form.rows.map((r) => ({ key: r.key.trim(), value: r.value })).filter((r) => r.key);
    if (new Set(rows.map((r) => r.key)).size !== rows.length) { setFormErr("Tên khóa bị trùng"); return; }
    const missing = rows.find((r) => !r.value && !form.saved.has(r.key));
    if (missing) { setFormErr(`Nhập giá trị cho ${missing.key}`); return; }
    const keys = rows.map((r) => r.key);
    const server: McpServer = form.transport === "stdio"
      ? { name, enabled: form.enabled, transport: "stdio", command: form.command.trim(), args: splitArgs(form.args), envKeys: keys }
      : { name, enabled: form.enabled, transport: "http", url: form.url.trim(), headerKeys: keys };
    const secrets: Record<string, string> = {};
    for (const r of rows) if (r.value) secrets[r.key] = r.value;
    try {
      await api.mcpSave(server, secrets);
      setForm(null);
      setFormErr(null);
      await reload();
    } catch (e) { setFormErr(toEngineError(e).message); }
  }

  const setRow = (i: number, patch: Partial<Row>) =>
    setForm((f) => f && { ...f, rows: f.rows.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const rowLabel = form?.transport === "http" ? "Header" : "Biến môi trường";

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>MCP server</h3>
        <button className="btn ghost" disabled={servers.length >= MAX || !!form}
          onClick={() => { setForm(blank()); setFormErr(null); }}>＋ Thêm MCP server</button>
      </div>
      <div className="hint" style={{ marginBottom: 6 }}>Công cụ mở rộng cho AI dựng video (lấy thông tin sản phẩm, thương hiệu…).</div>
      <div className="flag" style={{ marginBottom: 10 }}>MCP server chạy chương trình trên máy bạn. Chỉ thêm server bạn tin tưởng.</div>

      {servers.length === 0 && !form && <div className="hint">Chưa có MCP server nào.</div>}
      {servers.map((s) => {
        const c = checks[s.name];
        return (
          <div key={s.name} className="rt" style={{ alignItems: "flex-start" }}>
            <div className="tx">
              <b>{s.name}</b>
              <small>{s.transport === "stdio" ? "Lệnh" : "URL"} · {s.transport === "stdio" ? s.command : s.url}</small>
              {c?.error && <div className="errline" style={{ marginTop: 6 }}>{c.error}</div>}
              {c?.tools && (
                <ul className="sum" style={{ marginTop: 6 }}>
                  {c.tools.length === 0 && <li>Server không có tool nào</li>}
                  {c.tools.map((t) => <li key={t.name}><b>{t.name}</b>{t.description ? ` — ${t.description}` : ""}</li>)}
                </ul>
              )}
            </div>
            <span className="row">
              <span className={"sw" + (s.enabled ? " on" : "")} role="switch" aria-checked={s.enabled} aria-label={`Bật ${s.name}`}
                tabIndex={0} onClick={() => void toggle(s)} onKeyDown={(e) => { if (e.key === "Enter") void toggle(s); }} />
              <button className="btn ghost" disabled={c?.busy || !s.enabled} title={s.enabled ? "" : "Bật server để kiểm tra"}
                aria-label={`Kiểm tra ${s.name}`} onClick={() => void check(s.name)}>{c?.busy ? "Đang kiểm tra…" : "Kiểm tra"}</button>
              <button className="btn ghost" aria-label={`Sửa ${s.name}`} disabled={!!form}
                onClick={() => { setForm(fromServer(s)); setFormErr(null); }}>Sửa</button>
              <button className="btn ghost" aria-label={`Xóa ${s.name}`} onClick={() => void remove(s.name)}>Xóa</button>
            </span>
          </div>
        );
      })}

      {form && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <div className="fgrid">
            <span className="k">Kiểu</span>
            <span className="seg">
              <button className={form.transport === "stdio" ? "on" : ""} onClick={() => setForm({ ...form, transport: "stdio", rows: [] })}>Lệnh (stdio)</button>
              <button className={form.transport === "http" ? "on" : ""} onClick={() => setForm({ ...form, transport: "http", rows: [] })}>URL (HTTP)</button>
            </span>
            <span className="k">Tên</span>
            <input type="text" aria-label="Tên MCP" value={form.name} readOnly={!form.isNew} placeholder="vd: kho-anh"
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
            {form.transport === "stdio" ? (
              <>
                <span className="k">Lệnh</span>
                <input type="text" aria-label="Lệnh" value={form.command} placeholder="npx" onChange={(e) => setForm({ ...form, command: e.target.value })} />
                <span className="k">Tham số</span>
                <input type="text" aria-label="Tham số" value={form.args} placeholder='-y @shop/product-mcp "--tuỳ chọn có dấu cách"'
                  onChange={(e) => setForm({ ...form, args: e.target.value })} />
              </>
            ) : (
              <>
                <span className="k">URL</span>
                <input type="text" aria-label="URL" value={form.url} placeholder="https://…/mcp" onChange={(e) => setForm({ ...form, url: e.target.value })} />
              </>
            )}
            <span className="k">{rowLabel}</span>
            <div className="stack">
              {form.rows.map((r, i) => (
                <div key={i} className="row">
                  <input type="text" aria-label={`Tên ${rowLabel.toLowerCase()} ${i + 1}`} value={r.key} placeholder={form.transport === "http" ? "Authorization" : "API_KEY"}
                    onChange={(e) => setRow(i, { key: e.target.value })} />
                  <input type="password" aria-label={`Giá trị ${rowLabel.toLowerCase()} ${i + 1}`} value={r.value} autoComplete="off"
                    placeholder={form.saved.has(r.key) ? "•••• đã lưu" : "giá trị"} onChange={(e) => setRow(i, { value: e.target.value })} />
                  <button className="btn ghost" aria-label={`Bỏ ${rowLabel.toLowerCase()} ${i + 1}`}
                    onClick={() => setForm({ ...form, rows: form.rows.filter((_, j) => j !== i) })}>✕</button>
                </div>
              ))}
              <div><button className="btn ghost" onClick={() => setForm({ ...form, rows: [...form.rows, { key: "", value: "" }] })}>＋ Thêm {rowLabel.toLowerCase()}</button></div>
            </div>
          </div>
          {formErr && <div className="errline" style={{ marginTop: 8 }}>{formErr}</div>}
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
            <button className="btn ghost" onClick={() => { setForm(null); setFormErr(null); }}>Hủy</button>
            <button className="btn primary" onClick={() => void submit()}>Lưu</button>
          </div>
        </div>
      )}
    </div>
  );
}
