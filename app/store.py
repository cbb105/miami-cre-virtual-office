import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .domain import Settings, now


class Store:
    def __init__(self, path=None):
        self.path = path or os.getenv('DATABASE_PATH', 'data/office.sqlite')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY, created TEXT, status TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, cycle TEXT, agent TEXT, status TEXT, detail TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY, cycle TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, created TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS companies(domain TEXT PRIMARY KEY, name TEXT, first_seen TEXT, last_seen TEXT, fingerprint TEXT, data TEXT);
            ''')

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            yield db

    def settings(self):
        with self.db() as db:
            row = db.execute('SELECT data FROM settings WHERE id=1').fetchone()
        return Settings.model_validate_json(row[0]) if row else Settings()

    def save_settings(self, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (value.model_dump_json(),))

    def event(self, cycle, agent, status, detail):
        with self.db() as db:
            db.execute('INSERT INTO events(cycle,agent,status,detail,created) VALUES(?,?,?,?,?)', (cycle, agent, status, detail, now()))

    def events(self, cycle):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE cycle=? ORDER BY id', (cycle,))]

    def cycle(self, id, status, data):
        with self.db() as db:
            db.execute('INSERT INTO cycles VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data', (id, now(), status, json.dumps(data)))

    def cycles(self):
        with self.db() as db:
            return [dict(r) | {'data': json.loads(r['data'])} for r in db.execute('SELECT * FROM cycles ORDER BY created DESC LIMIT 30')]

    def source(self, source):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?)', (source.id, source.model_dump_json()))

    def finding(self, cycle, finding):
        with self.db() as db:
            db.execute('INSERT INTO findings(cycle,data) VALUES(?,?)', (cycle, finding.model_dump_json()))

    def memory(self):
        with self.db() as db:
            return [dict(r) | {'data': json.loads(r['data'])} for r in db.execute('SELECT * FROM companies ORDER BY last_seen DESC LIMIT 150')]

    def reports(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM reports ORDER BY created DESC LIMIT 90')]

    def save_report(self, report):
        with self.db() as db:
            db.execute('INSERT INTO reports VALUES(?,?,?)', (report['id'], report['created'], json.dumps(report)))
            for p in report['prospects']:
                db.execute('INSERT INTO companies VALUES(?,?,?,?,?,?) ON CONFLICT(domain) DO UPDATE SET last_seen=excluded.last_seen,fingerprint=excluded.fingerprint,data=excluded.data', (p['domain'], p['company'], now(), now(), p['fingerprint'], json.dumps(p)))


def fingerprint(prospect, findings, sources):
    # Stable evidence identity: ignores retrieval timestamps, quotation wording and model prose.
    evidence = sorted({(str(sources[s].url), sources[s].source_date) for f in findings for s in f.source_ids})
    value = {'evidence': evidence, 'priority': prospect['priority'], 'timing': prospect['timing']}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
