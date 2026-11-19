from pathlib import Path


LANGUAGES = {"fa": "فارسی", "en": "English"}

KEYS = """
home channels groups dialogs sync syncing all public private prev next search refresh clear
leave language page results empty expired query_prompt page_prompt page_invalid username link
members id peer about unavailable partial photo open copy confirm cancel kind expires left
already refresh_failed unknown still_member cancelled busy changed bad_confirm creator failed
sign_in expired_session wait seconds channel group supergroup
""".split()

CATALOGS = {}
for line in Path(__file__).with_name("catalog.txt").read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    language, *values = line.split("|")
    if language in CATALOGS or len(values) != len(KEYS) or not all(values):
        raise ValueError(f"Invalid translation catalog row: {language}")
    CATALOGS[language] = dict(zip(KEYS, values, strict=True))

if CATALOGS.keys() != LANGUAGES.keys():
    raise ValueError("The catalogs and supported languages do not match")


def translate(language, key):
    return CATALOGS.get(language, CATALOGS["en"])[key]
