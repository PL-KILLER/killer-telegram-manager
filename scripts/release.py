import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
FILES = (".env.example", ".gitignore", "README.md", "LICENSE", "SECURITY.md", "requirements.txt")
ROOTS = ("app", "miniapp", "deploy", "docs", "tests", "scripts", ".github")
EXTENSIONS = {".py", ".txt", ".html", ".css", ".js", ".php", ".md", ".yml"}
PUBLIC_EXCLUDE = {"app/shared.py", "app/shared_gateway.py", "tests/test_shared.py"}
SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9])\d{6,}:[A-Za-z0-9_-]{30,}"),
    re.compile(rb"tg://login\?token=[A-Za-z0-9_-]{24,}"),
    re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"(?m)^(?:TELEGRAM_(?:API_ID|API_HASH|BOT_TOKEN|OWNER_ID)|KILLER_SESSION_KEY)=[^\r\n]+"),
)


def source_files():
    files = [ROOT / name for name in FILES]
    for directory in ROOTS:
        files.extend(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and not path.is_symlink() and path.suffix in EXTENSIONS
                     and not any(part.startswith(".") and part != ".github"
                                 for part in path.relative_to(ROOT).parts))
    return sorted(files)


def main():
    sources = []
    for path in source_files():
        if path.is_symlink():
            raise SystemExit(f"Unexpected symlink: {path.name}")
        relative = path.relative_to(ROOT).as_posix()
        if relative in PUBLIC_EXCLUDE:
            continue
        content = path.read_bytes()
        if relative == ".env.example":
            lines = content.decode("utf-8").splitlines()
            content = ("\n".join(line for line in lines
                                if not line.startswith(("KILLER_SHARED_", "# Enable separate", "# Send guests")))
                       + "\n").encode("utf-8")
        if relative == "README.md":
            content = content.split("### مینی‌اپ چندکاربره".encode("utf-8"), 1)[0].rstrip() + b"\n"
        if path.resolve() != Path(__file__).resolve() and any(
            pattern.search(content) for pattern in SECRET_PATTERNS
        ):
            raise SystemExit(f"Credential-like data in {path.relative_to(ROOT)}")
        sources.append((relative, content))
    sources.append(("PUBLIC_EDITION.txt", b"KILLER Telegram Manager - single-owner edition\n"))
    output = ROOT / "dist" / "killer-allplus-source.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as package:
        for name, content in sources:
            package.writestr(f"killer-allplus/{name}", content)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"{len(sources)} files · SHA-256 {digest}")


if __name__ == "__main__":
    main()
