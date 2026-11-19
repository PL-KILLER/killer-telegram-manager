import os
import tempfile
from pathlib import Path

from telethon.sessions import StringSession


class EncryptedSession(StringSession):
    def __init__(self, path: Path, cipher):
        self.path = path
        self.cipher = cipher
        self.enabled = False
        self.persisted = None
        try:
            self.persisted = cipher.decrypt(path.read_bytes()).decode("ascii")
        except FileNotFoundError:
            pass
        super().__init__(self.persisted)

    def enable(self):
        self.enabled = True
        self.save()

    def save(self):
        payload = super().save()
        if self.enabled and payload and payload != self.persisted:
            fd, name = tempfile.mkstemp(dir=self.path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(self.cipher.encrypt(payload.encode("ascii")))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
                self.persisted = payload
            finally:
                Path(name).unlink(missing_ok=True)
        return payload

    def invalidate(self):
        self.enabled = False
        self.path.unlink(missing_ok=True)

    def delete(self):
        self.invalidate()
