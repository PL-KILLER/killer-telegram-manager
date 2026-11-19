import re
import unicodedata


def search_key(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({"ي": "ی", "ك": "ک", "‌": " "}))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def confirmation_title(value):
    controls = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
    return " ".join(value.translate(dict.fromkeys(map(ord, controls))).split())
