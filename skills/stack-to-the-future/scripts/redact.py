"""Find and scrub secret values. Runs on everything the skill stores, shows Claude, or renders."""
import fnmatch
import re
from pathlib import Path

SECRET_FILES = (
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "secrets.*", "credentials*",
    ".npmrc", ".pypirc", ".netrc", ".htpasswd",
)

_NAME = r"\w*(?:key|secret|token|passw(?:or)?d|pwd|credential|dsn)\w*"
_NOT_DONE = r"(?!\[REDACTED)"

# (kind, pattern, group to replace; 0 = whole match)
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), 0),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"), 0),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), 0),
    ("stripe_key", re.compile(r"\b[srp]k_(?:live|test)_[A-Za-z0-9]{10,}"), 0),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), 0),
    ("ai_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), 0),
    ("url_password", re.compile(rf"\b[a-z][a-z0-9+.-]*://[^:/\s@]+:{_NOT_DONE}([^@\s]+)@", re.I), 1),
    ("assigned_secret", re.compile(rf"\b{_NAME}\b[^=\n]{{0,40}}?[=:]\s*(['\"]){_NOT_DONE}([^'\"\n]{{8,}})\1", re.I), 2),
    ("env_secret", re.compile(rf"(?m)^\s*(?:export\s+)?{_NAME}\s*=\s*{_NOT_DONE}([^\s'\"#][^\s#]{{7,}})", re.I), 1),
]


def is_secret_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_FILES)


def redact(text: str) -> tuple[str, int]:
    """Return the text with secret values replaced by [REDACTED:<kind>], and how many were replaced."""
    hits = 0
    for kind, pattern, group in PATTERNS:
        def replace(m, kind=kind, group=group):
            nonlocal hits
            hits += 1
            start, end = m.start(group) - m.start(), m.end(group) - m.start()
            kept_lines = "\n" * m.group(0)[start:end].count("\n")  # keep line numbers stable for cited excerpts
            return m.group(0)[:start] + f"[REDACTED:{kind}]" + kept_lines + m.group(0)[end:]
        text = pattern.sub(replace, text)
    return text, hits


def read_redacted(root: Path, path: str) -> list[str]:
    """Source lines of a repo file, redacted, for showing to Claude. Refuses secrets files and paths outside root."""
    root = Path(root).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"{path} is not a file inside {root}")
    if is_secret_file(path):
        raise ValueError(f"{path} is a secrets file; it is never read.")
    return redact(target.read_text(errors="replace"))[0].splitlines()


def redact_obj(obj):
    """Redact every string in a JSON-like structure. Returns (clean copy, hit count)."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        pairs = [redact_obj(v) for v in obj]
        return [v for v, _ in pairs], sum(h for _, h in pairs)
    if isinstance(obj, dict):
        pairs = {k: redact_obj(v) for k, v in obj.items()}
        return {k: v for k, (v, _) in pairs.items()}, sum(h for _, h in pairs.values())
    return obj, 0
