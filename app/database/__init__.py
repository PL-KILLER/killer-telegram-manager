import sqlite3
from contextlib import closing
from dataclasses import astuple, dataclass
from datetime import datetime, timezone

from app.utils import search_key


@dataclass(frozen=True)
class Chat:
    peer: int
    entity_id: int
    kind: str
    subtype: str
    title: str
    username: str | None


class Store:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value INTEGER);
                CREATE TABLE IF NOT EXISTS chats (
                    peer INTEGER PRIMARY KEY, entity_id INTEGER, kind TEXT,
                    subtype TEXT, title TEXT, username TEXT, search TEXT
                );
                CREATE INDEX IF NOT EXISTS chats_kind_search ON chats(kind, search, peer);
            """)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                db.execute("ALTER TABLE chats ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
                db.execute("CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("""CREATE TABLE activity (
                    id INTEGER PRIMARY KEY, time TEXT NOT NULL,
                    operation TEXT NOT NULL, outcome TEXT NOT NULL
                )""")
                db.execute("PRAGMA user_version=1")
            if version < 2:
                db.execute("""CREATE TABLE organizer (
                    peer INTEGER PRIMARY KEY, favorite INTEGER NOT NULL DEFAULT 0,
                    tag TEXT NOT NULL DEFAULT '', viewed TEXT
                )""")
                db.execute("""CREATE TABLE snapshots (
                    time TEXT PRIMARY KEY, dialogs INTEGER NOT NULL, channels INTEGER NOT NULL,
                    groups INTEGER NOT NULL, archived INTEGER NOT NULL
                )""")
                db.execute("PRAGMA user_version=2")
            if version < 3:
                db.execute("ALTER TABLE chats ADD COLUMN last_message TEXT")
                db.execute("""CREATE TABLE search_history (
                    id INTEGER PRIMARY KEY, ciphertext BLOB NOT NULL
                )""")
                db.execute("PRAGMA user_version=3")
            if version < 4:
                db.execute("""CREATE TABLE media_index (
                    peer INTEGER NOT NULL, message INTEGER NOT NULL, kind TEXT NOT NULL,
                    bytes INTEGER NOT NULL, PRIMARY KEY (peer,message)
                )""")
                db.execute("PRAGMA user_version=4")
            if version < 5:
                db.execute("ALTER TABLE chats ADD COLUMN unread INTEGER")
                db.execute("ALTER TABLE chats ADD COLUMN unread_mark INTEGER NOT NULL DEFAULT 0")
                db.execute("ALTER TABLE chats ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
                db.execute("ALTER TABLE chats ADD COLUMN muted_until TEXT")
                db.execute("PRAGMA user_version=5")
            elif version != 5:
                raise ValueError(f"Unsupported database schema: {version}")

    def connect(self):
        return sqlite3.connect(self.path)

    def replace(self, chats, total, archived=(), last_messages=None, flags=None):
        archived = set(archived)
        last_messages = last_messages or {}
        flags = flags or {}
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM chats")
            db.executemany("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (astuple(chat) + (search_key(chat.title), chat.peer in archived,
                                              last_messages.get(chat.peer)) +
                            flags.get(chat.peer, (None, 0, 0, None))
                            for chat in chats))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('dialogs', ?)", (total,))
            db.execute("""INSERT OR REPLACE INTO snapshots
                           SELECT ?, ?, count(CASE WHEN kind='c' THEN 1 END),
                           count(CASE WHEN kind='g' THEN 1 END), coalesce(sum(archived),0) FROM chats""",
                       (datetime.now(timezone.utc).isoformat(timespec="microseconds"), total))
            db.execute("DELETE FROM snapshots WHERE time < datetime('now','-90 days')")

    def counts(self):
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            counts = dict(db.execute("SELECT kind, count(*) FROM chats GROUP BY kind"))
            row = db.execute("SELECT value FROM settings WHERE key='dialogs'").fetchone()
        return counts.get("c", 0), counts.get("g", 0), row[0] if row else None

    def page(self, kind, query, page, size, privacy="all", sort="name", tag=None, state=""):
        value = search_key(query).lstrip("@")
        args = [value, value, value]
        condition = ("FROM chats WHERE (instr(search || ' ' || coalesce(lower(username),''), ?) > 0 "
                     "OR CAST(entity_id AS TEXT)=? OR CAST(peer AS TEXT)=?)")
        if kind == "a":
            condition += " AND archived=1"
        elif kind == "favorites":
            condition += " AND EXISTS (SELECT 1 FROM organizer o WHERE o.peer=chats.peer AND o.favorite=1)"
        elif kind == "tagged":
            condition += " AND EXISTS (SELECT 1 FROM organizer o WHERE o.peer=chats.peer AND o.tag<>'')"
        elif kind != "all":
            condition += " AND kind=?"
            args.append(kind)
        if tag:
            condition += " AND EXISTS (SELECT 1 FROM organizer o WHERE o.peer=chats.peer AND o.tag=?)"
            args.append(tag)
        if privacy == "public":
            condition += " AND nullif(username, '') IS NOT NULL"
        elif privacy == "private":
            condition += " AND nullif(username, '') IS NULL"
        condition += {"unread": " AND (unread>0 OR unread_mark=1)",
                      "pinned": " AND pinned=1",
                      "muted": " AND julianday(muted_until)>julianday('now')"}.get(state, "")
        order = {
            "recent": "(SELECT viewed FROM organizer o WHERE o.peer=chats.peer) DESC, search, peer",
            "latest": "last_message DESC, search, peer",
            "unread": "coalesce(unread, 0) DESC, unread_mark DESC, search, peer",
            "type": "kind, search, peer",
        }.get(sort, "search, peer")
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            total = db.execute(f"SELECT count(*) {condition}", args).fetchone()[0]
            pages = max(1, (total + size - 1) // size)
            page = max(0, min(page, pages - 1))
            rows = db.execute(
                f"SELECT peer, entity_id, kind, subtype, title, username {condition} "
                f"ORDER BY {order} LIMIT ? OFFSET ?", (*args, size, page * size)
            ).fetchall()
        return [Chat(*row) for row in rows], page, pages, total

    def dialog_stats(self):
        with closing(self.connect()) as db:
            row = db.execute("""SELECT count(unread), sum(unread), sum(unread>0 OR unread_mark=1),
                                       coalesce(sum(pinned),0), coalesce(sum(archived),0)
                                FROM chats""").fetchone()
        tracked, unread, unread_chats, pinned, archived = row
        return {"unread_messages": unread if tracked else None,
                "unread_chats": unread_chats if tracked else None,
                "pinned": pinned if tracked else None, "archived": archived}

    def preference(self, key, fallback):
        with closing(self.connect()) as db:
            row = db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return row[0] if row else fallback

    def set_archived(self, peer, value):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE chats SET archived=? WHERE peer=?", (bool(value), peer))

    def set_pinned(self, peer, value):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE chats SET pinned=? WHERE peer=?", (bool(value), peer))

    def set_preference(self, key, value):
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (key, value))

    def record(self, operation, outcome):
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO activity (time,operation,outcome) VALUES (?,?,?)",
                       (when, operation, outcome))
            db.execute("DELETE FROM activity WHERE id <= (SELECT max(id)-1000 FROM activity)")

    def activity(self, offset, limit):
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT time,operation,outcome FROM activity ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()

    def analytics(self):
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            kinds = dict(db.execute("SELECT kind,count(*) FROM chats GROUP BY kind"))
            archived = db.execute("SELECT count(*) FROM chats WHERE archived=1").fetchone()[0]
            rows = db.execute("""SELECT time,dialogs,channels,groups,archived FROM snapshots
                                 ORDER BY time DESC LIMIT 40""").fetchall()
            storage = db.execute("PRAGMA page_count").fetchone()[0]
            storage *= db.execute("PRAGMA page_size").fetchone()[0]
            media = db.execute("SELECT kind,count(*),sum(bytes) FROM media_index GROUP BY kind").fetchall()
        return {"kinds": kinds, "archived": archived, "history": rows[::-1],
                "database_bytes": storage, "observed_media": media}

    def observe_media(self, observations):
        with closing(self.connect()) as db, db:
            db.executemany("INSERT OR REPLACE INTO media_index VALUES (?,?,?,?)", observations)

    def collections(self):
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT o.tag,count(*) FROM organizer o JOIN chats c ON c.peer=o.peer
                                 WHERE o.tag<>'' GROUP BY o.tag ORDER BY o.tag""").fetchall()
        return rows

    def organize(self, peer, *, favorite=None, tag=None, viewed=False):
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR IGNORE INTO organizer (peer) VALUES (?)", (peer,))
            if favorite is not None:
                db.execute("UPDATE organizer SET favorite=? WHERE peer=?", (favorite, peer))
            if tag is not None:
                db.execute("UPDATE organizer SET tag=? WHERE peer=?", (tag, peer))
            if viewed:
                db.execute("UPDATE organizer SET viewed=? WHERE peer=?",
                           (datetime.now(timezone.utc).isoformat(), peer))
            favorite, tag, viewed_at = db.execute(
                "SELECT favorite,tag,viewed FROM organizer WHERE peer=?", (peer,)).fetchone()
        return {"favorite": bool(favorite), "tag": tag, "viewed": viewed_at}

    def searches(self, ciphertext=None, *, clear=False):
        with closing(self.connect()) as db, db:
            if clear:
                db.execute("DELETE FROM search_history")
            if ciphertext:
                db.execute("INSERT INTO search_history (ciphertext) VALUES (?)", (ciphertext,))
                db.execute("DELETE FROM search_history WHERE id <= (SELECT max(id)-30 FROM search_history)")
            return [row[0] for row in db.execute(
                "SELECT ciphertext FROM search_history ORDER BY id DESC LIMIT 30")]

    def inactive(self, days=90):
        with closing(self.connect()) as db:
            return db.execute("""SELECT title,last_message FROM chats
                                WHERE last_message IS NOT NULL
                                  AND julianday(last_message) < julianday('now',?)
                                ORDER BY last_message LIMIT 30""", (f"-{days} days",)).fetchall()

    def organizer_export(self):
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT peer,favorite,tag FROM organizer
                                 WHERE favorite=1 OR tag<>'' ORDER BY peer""").fetchall()
        return {"version": 1, "organizer": [{"peer": str(peer), "favorite": bool(favorite), "tag": tag}
                                            for peer, favorite, tag in rows]}

    def organizer_import(self, rows):
        with closing(self.connect()) as db, db:
            peers = {item[0] for item in db.execute("SELECT peer FROM chats")}
            applicable = [(peer, favorite, tag) for peer, favorite, tag in rows if peer in peers]
            db.executemany("""INSERT INTO organizer (peer,favorite,tag) VALUES (?,?,?)
                           ON CONFLICT(peer) DO UPDATE SET favorite=excluded.favorite, tag=excluded.tag""",
                           applicable)
        return len(applicable)
