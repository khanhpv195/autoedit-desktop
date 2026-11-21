CREATE TABLE keys (
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  machine TEXT,
  activated_at TEXT,
  last_seen_at TEXT,
  app_version TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked'))
);
