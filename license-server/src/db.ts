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
}
