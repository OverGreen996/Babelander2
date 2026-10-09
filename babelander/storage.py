"""Serialized SQLite access, bounded persistent cache, explicit usage ledger."""
from pathlib import Path
import json
import sqlite3
import threading
import time

from .types import Translation


class Store:
    def __init__(self, root):
        Path(root).mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(Path(root)/'workspace.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value TEXT, touched REAL);
            CREATE INDEX IF NOT EXISTS cache_recency ON cache(touched);
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, at REAL, mode TEXT, source TEXT, target TEXT, provider TEXT, warning TEXT, milliseconds REAL);
            CREATE TABLE IF NOT EXISTS terms(id INTEGER PRIMARY KEY, source TEXT, target TEXT, domain TEXT, UNIQUE(source,domain));
            CREATE TABLE IF NOT EXISTS usage(provider TEXT, month TEXT, attempted INTEGER, confirmed INTEGER, PRIMARY KEY(provider,month));
        ''')
        self.db.commit()

    def get(self, key):
        with self.lock:
            row = self.db.execute('SELECT value FROM cache WHERE key=?', (key,)).fetchone()
            if not row:
                return None
            # The write computes its own order atomically, including other
            # connections. Existing timestamp-based databases need no migration.
            self.db.execute('UPDATE cache SET touched=(SELECT COALESCE(MAX(touched),0)+1 FROM cache) WHERE key=?', (key,))
            self.db.commit()
            return Translation(**json.loads(row[0]), cache_hit=True)

    def put(self, key, translation):
        from dataclasses import asdict
        value = asdict(translation)
        value.pop('cache_hit')
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO cache SELECT ?,?,COALESCE(MAX(touched),0)+1 FROM cache', (key,json.dumps(value,ensure_ascii=False)))
            self.db.execute('DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY touched DESC LIMIT -1 OFFSET 1000)')
            self.db.commit()

    def record(self, mode, translation, milliseconds):
        # Chat input and reply drafts stay in memory for this session.
        if str(mode) in ('chat','reply'):
            return
        with self.lock:
            self.db.execute('INSERT INTO history(at,mode,source,target,provider,warning,milliseconds) VALUES(?,?,?,?,?,?,?)',
                            (time.time(),str(mode),translation.source,translation.target,translation.provider,translation.warning,milliseconds))
            self.db.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 1000)')
            self.db.commit()

    def history(self):
        with self.lock:
            return self.db.execute('SELECT mode,source,target,provider,warning FROM history ORDER BY id DESC LIMIT 100').fetchall()

    def terms(self):
        with self.lock:
            return self.db.execute('SELECT id,source,target,domain FROM terms ORDER BY source').fetchall()

    def save_term(self, source, target, domain):
        if not source.strip() or not target.strip():
            raise ValueError('原文與譯文都必須填寫。')
        with self.lock:
            self.db.execute('INSERT INTO terms(source,target,domain) VALUES(?,?,?) ON CONFLICT(source,domain) DO UPDATE SET target=excluded.target',
                            (source.strip(),target.strip(),domain))
            self.db.execute('DELETE FROM cache')
            self.db.commit()

    def delete_term(self, identifier):
        with self.lock:
            self.db.execute('DELETE FROM terms WHERE id=?',(identifier,))
            self.db.execute('DELETE FROM cache')
            self.db.commit()

    def clear_history(self):
        with self.lock:
            self.db.execute('DELETE FROM history')
            self.db.commit()

    def clear_cache(self):
        with self.lock:
            self.db.execute('DELETE FROM cache')
            self.db.commit()

    def reserve(self, provider, characters, limit):
        month = time.strftime('%Y-%m')
        with self.lock:
            self.db.execute('INSERT OR IGNORE INTO usage VALUES(?,?,0,0)', (provider,month))
            attempted = self.db.execute('SELECT attempted FROM usage WHERE provider=? AND month=?',(provider,month)).fetchone()[0]
            if limit and attempted+characters > limit:
                raise ValueError('本月雲端字數安全上限已達；請調整設定或切回本機。')
            self.db.execute('UPDATE usage SET attempted=attempted+? WHERE provider=? AND month=?',(characters,provider,month))
            self.db.commit()
        return month

    def confirm(self, provider, characters, month):
        with self.lock:
            self.db.execute('UPDATE usage SET confirmed=confirmed+? WHERE provider=? AND month=?',(characters,provider,month))
            self.db.commit()

    def usage(self):
        with self.lock:
            return self.db.execute('SELECT provider,attempted,confirmed FROM usage WHERE month=?',(time.strftime('%Y-%m'),)).fetchall()

    def close(self):
        with self.lock:
            self.db.close()
