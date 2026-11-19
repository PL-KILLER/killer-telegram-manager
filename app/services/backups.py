import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone


class Backups:
    def __init__(self, data, cipher):
        self.database = data / "metadata.sqlite3"
        self.directory = data / "backups"
        self.cipher = cipher

    def list(self):
        return [{"name": path.name, "bytes": path.stat().st_size}
                for path in sorted(self.directory.glob("killer-*.fernet"), reverse=True)
                if path.is_file() and not path.is_symlink()]

    def path(self, name):
        if not re.fullmatch(r"killer-[0-9T]+Z\.fernet", name):
            raise ValueError("Invalid backup name")
        path = self.directory / name
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError
        return path

    def create(self, keep=10):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("killer-%Y%m%dT%H%M%S%fZ.fernet")
        with closing(sqlite3.connect(self.database)) as source, \
                closing(sqlite3.connect(":memory:")) as snapshot:
            source.backup(snapshot)
            blob = snapshot.serialize()
        fd, temp = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(self.cipher.encrypt(blob))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, self.directory / name)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        for item in self.list()[max(1, keep):]:
            self.path(item["name"]).unlink(missing_ok=True)
        return name

    def inspect(self, name, target=None):
        payload = self.cipher.decrypt(self.path(name).read_bytes())
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            from pathlib import Path

            file = Path(tmp) / "snapshot.sqlite3"
            file.write_bytes(payload)
            with closing(sqlite3.connect(file)) as snapshot:
                snapshot.execute("PRAGMA trusted_schema=OFF")
                if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Invalid database integrity")
                version = snapshot.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1, 2, 3, 4, 5):
                    raise ValueError("Unsupported backup schema")
                count = snapshot.execute("SELECT count(*) FROM chats").fetchone()[0]
                if target:
                    with closing(sqlite3.connect(target)) as db:
                        snapshot.backup(db)
        return {"name": name, "schema": version, "chats": count}
