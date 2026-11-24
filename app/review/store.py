import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT, kind TEXT NOT NULL DEFAULT 'SOURCE',
    base_id TEXT, rows TEXT
);"""

REVISIONS = """CREATE TABLE IF NOT EXISTS revisions (
    base_id TEXT NOT NULL, digest TEXT NOT NULL, outcome TEXT NOT NULL,
    successor_id TEXT, detail TEXT NOT NULL, created TEXT NOT NULL,
    PRIMARY KEY (base_id, digest)
);"""

ADDED = {
    "kind": "TEXT NOT NULL DEFAULT 'SOURCE'",
    "base_id": "TEXT",
    "rows": "TEXT",
}


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute(SCHEMA)
            db.execute(REVISIONS)
            present = {row["name"] for row in db.execute("PRAGMA table_info(runs)")}
            for name, definition in ADDED.items():
                if name not in present:
                    db.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")
            yield db

    def register(self, run_id, report, rows=None, kind="SOURCE", base_id=None):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,report,created,kind,base_id,rows)"
                " VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (
                    run_id,
                    json.dumps(report, ensure_ascii=False),
                    report["manifest"]["created"],
                    kind,
                    base_id,
                    None if rows is None else json.dumps(rows, ensure_ascii=False),
                ),
            )
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise DomainIssue("RUN_NOT_FOUND")
        result = dict(row)
        result["report"] = json.loads(result["report"])
        result["rows"] = None if result["rows"] is None else json.loads(result["rows"])
        return result

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,created,status,revision,note,kind,base_id FROM runs"
                    " ORDER BY created DESC,id LIMIT 50"
                )
            ]

    def revise(self, run_id, revision, status, note, now):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?",
                (status, note, now, run_id, revision),
            )
            if cursor.rowcount != 1:
                raise DomainIssue("STALE_REVIEW")
        return self.load(run_id)

    def record_revision(
        self, base_id, digest, outcome, successor_id, detail, created
    ):
        """Register one revision file once; replays never rewrite the record."""
        with self.connect() as db:
            db.execute(
                "INSERT INTO revisions(base_id,digest,outcome,successor_id,detail,created)"
                " VALUES (?,?,?,?,?,?) ON CONFLICT(base_id,digest) DO NOTHING",
                (
                    base_id,
                    digest,
                    outcome,
                    successor_id,
                    json.dumps(detail, ensure_ascii=False),
                    created,
                ),
            )
        return self.revision(base_id, digest)

    def revision(self, base_id, digest):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM revisions WHERE base_id=? AND digest=?",
                (base_id, digest),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["detail"] = json.loads(result["detail"])
        return result

    def revisions(self, base_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM revisions WHERE base_id=? ORDER BY created,digest",
                (base_id,),
            ).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]
