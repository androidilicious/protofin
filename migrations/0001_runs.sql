CREATE TABLE IF NOT EXISTS runs (
  scope TEXT NOT NULL,
  ip    TEXT NOT NULL,
  day   TEXT NOT NULL,
  run   TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (scope, ip, day, run)
);
