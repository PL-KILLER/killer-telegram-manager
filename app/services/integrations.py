from dataclasses import dataclass


@dataclass(frozen=True)
class Plugin:
    key: str
    version: str
    api_version: int
    permissions: tuple[str, ...]


INACTIVITY = Plugin("inactivity", "1.0", 1, ("local_dialog_metadata:read",))
BUILTINS = {INACTIVITY.key: INACTIVITY}


def organizer_import_rows(payload):
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Invalid organizer export")
    rows = payload.get("organizer")
    if not isinstance(rows, list) or len(rows) > 100_000:
        raise ValueError("Invalid organizer list")
    normalized = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("favorite")) is not bool:
            raise ValueError("Invalid organizer entry")
        tag = row.get("tag")
        peer = row.get("peer")
        if (not isinstance(tag, str) or len(tag) > 64 or not isinstance(peer, str)
                or len(peer) > 20 or not peer.removeprefix("-").isascii()
                or not peer.removeprefix("-").isdecimal()):
            raise ValueError("Invalid organizer fields")
        peer = int(peer)
        if not -(2**63) <= peer < 2**63 or peer in normalized:
            raise ValueError("Invalid or duplicate peer")
        normalized[peer] = (peer, row["favorite"], tag)
    return tuple(normalized.values())
