import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def verified_user(data, bot_token, *, now=None, max_age=3600):
    if not data or len(data) > 8192:
        return None
    try:
        pairs = parse_qsl(data, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return None
        digest = fields.pop("hash")
        signed = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, signed.encode(), hashlib.sha256).hexdigest()
        if len(digest) != 64 or not digest.isascii() or not hmac.compare_digest(digest, expected):
            return None
        user = json.loads(fields["user"])
        auth_date = int(fields["auth_date"])
        age = (time.time() if now is None else now) - auth_date
        if not isinstance(user, dict) or not -30 <= age <= max_age:
            return None
        user_id = user.get("id")
        if type(user_id) is int and 0 < user_id < 2**52:
            return user
    except (KeyError, UnicodeError, ValueError, TypeError):
        return None
    return None


def verified_user_id(data, bot_token, *, now=None, max_age=3600):
    user = verified_user(data, bot_token, now=now, max_age=max_age)
    return user["id"] if user else None


def verify_init_data(data, bot_token, owner_id, *, now=None, max_age=3600):
    user_id = verified_user_id(data, bot_token, now=now, max_age=max_age)
    return user_id is not None and user_id == owner_id
