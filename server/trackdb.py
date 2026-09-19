"""轨迹/会话存储（开发与联调用；正式部署可整体换成裁判平台的数据库）。"""
import json
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  id         TEXT PRIMARY KEY,
  callsign   TEXT NOT NULL,
  started_at REAL,
  ended_at   REAL,
  closed     INTEGER DEFAULT 0,
  last_seen  REAL,
  challenge  TEXT
);
CREATE TABLE IF NOT EXISTS track(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  sid      TEXT,
  ts       REAL,
  lat      REAL, lon      REAL,
  alt_ft   REAL, agl_ft   REAL,
  hdg      REAL, pitch    REAL, roll REAL,
  vcas_kt  REAL, vs_fps   REAL,
  wow      INTEGER,
  source   TEXT,
  raw      TEXT
);
CREATE INDEX IF NOT EXISTS idx_track_sid ON track(sid, ts);
"""


class TrackDB:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    # ---- sessions ----
    def open_session(self, callsign: str) -> str:
        sid = uuid.uuid4().hex[:16]
        now = time.time()
        self.conn.execute(
            "INSERT INTO sessions(id, callsign, started_at, last_seen) VALUES(?,?,?,?)",
            (sid, callsign, now, now))
        self.conn.commit()
        return sid

    def touch(self, sid: str, ts: float):
        self.conn.execute("UPDATE sessions SET last_seen=? WHERE id=?", (ts, sid))
        self.conn.commit()

    def close_session(self, sid: str):
        self.conn.execute(
            "UPDATE sessions SET closed=1, ended_at=? WHERE id=?", (time.time(), sid))
        self.conn.commit()

    def get_session(self, sid: str):
        cur = self.conn.execute("SELECT * FROM sessions WHERE id=?", (sid,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    # ---- track rows ----
    def insert_row(self, sid: str, r, source: str = "mp"):
        self.conn.execute(
            "INSERT INTO track(sid, ts, lat, lon, alt_ft, agl_ft, hdg, pitch, roll,"
            " vcas_kt, vs_fps, wow, source, raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, r.ts, r.lat, r.lon, r.alt_ft, r.agl_ft, r.hdg, r.pitch, r.roll,
             r.vcas_kt, r.vs_fps, int(r.wow or 0), source,
             json.dumps(getattr(r, "extra", {}), ensure_ascii=False)))
        self.conn.commit()

    def rows(self, sid: str):
        from server.trackrow import TrackRow
        cur = self.conn.execute(
            "SELECT ts, lat, lon, alt_ft, agl_ft, hdg, pitch, roll, vcas_kt, vs_fps,"
            " wow FROM track WHERE sid=? ORDER BY ts", (sid,))
        return [TrackRow(*row) for row in cur.fetchall()]

    def active_sessions(self):
        cur = self.conn.execute("SELECT id, callsign FROM sessions WHERE closed=0")
        return cur.fetchall()
