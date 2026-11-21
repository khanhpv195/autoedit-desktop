export type KeyRow = {
  key: string; name: string; note: string; created_at: string;
  machine: string | null; activated_at: string | null; last_seen_at: string | null;
  app_version: string | null; status: "active" | "revoked";
};

export interface Db {
  get(key: string): Promise<KeyRow | null>;
  insert(row: KeyRow): Promise<void>;
  update(key: string, patch: Partial<KeyRow>): Promise<void>;
  list(): Promise<KeyRow[]>;
  /** Atomic bind/refresh for activation. Returns the number of rows changed (0 = lost the race, revoked, or bound elsewhere). */
  claim(key: string, machine: string, now: string, version: string | null): Promise<number>;
}

const COLS = ["name", "note", "machine", "activated_at", "last_seen_at", "app_version", "status"] as const;

export class D1Db implements Db {
  constructor(private d1: D1Database) {}
  async get(key: string) {
    return (await this.d1.prepare("SELECT * FROM keys WHERE key = ?").bind(key).first<KeyRow>()) ?? null;
  }
  async insert(r: KeyRow) {
    await this.d1.prepare("INSERT INTO keys (key,name,note,created_at,machine,activated_at,last_seen_at,app_version,status) VALUES (?,?,?,?,?,?,?,?,?)")
      .bind(r.key, r.name, r.note, r.created_at, r.machine, r.activated_at, r.last_seen_at, r.app_version, r.status).run();
  }
  async update(key: string, patch: Partial<KeyRow>) {
    const cols = COLS.filter((c) => c in patch);
    if (!cols.length) return;
    await this.d1.prepare(`UPDATE keys SET ${cols.map((c) => `${c} = ?`).join(", ")} WHERE key = ?`)
      .bind(...cols.map((c) => patch[c] ?? null), key).run();
  }
  async claim(key: string, machine: string, now: string, version: string | null) {
    const r = await this.d1.prepare(
      "UPDATE keys SET machine = ?, activated_at = COALESCE(activated_at, ?), last_seen_at = ?, app_version = ? WHERE key = ? AND status = 'active' AND (machine IS NULL OR machine = ?)")
      .bind(machine, now, now, version, key, machine).run();
    return r.meta.changes ?? 0;
  }
  async list() {
    return (await this.d1.prepare("SELECT * FROM keys ORDER BY created_at DESC").all<KeyRow>()).results;
  }
}

export class MemoryDb implements Db {
  rows = new Map<string, KeyRow>();
  async get(key: string) { const r = this.rows.get(key); return r ? { ...r } : null; }
  async insert(r: KeyRow) { this.rows.set(r.key, { ...r }); }
  async update(key: string, patch: Partial<KeyRow>) { const r = this.rows.get(key); if (r) Object.assign(r, patch); }
  async list() { return [...this.rows.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)); }
  async claim(key: string, machine: string, now: string, version: string | null) {
    const r = this.rows.get(key);
    if (!r || r.status !== "active" || (r.machine !== null && r.machine !== machine)) return 0;
    r.machine = machine; r.activated_at = r.activated_at ?? now; r.last_seen_at = now; r.app_version = version;
    return 1;
  }
}
