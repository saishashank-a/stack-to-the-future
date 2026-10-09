"""Redaction: every known secret shape is scrubbed, and secrets in stored scan text never survive."""
from redact import is_secret_file, redact
from scan import scan

# Built at runtime so this file never contains a real-looking token.
TOKENS = {
    "aws_key": "AKIA" + "Q" * 16,
    "github_token": "ghp_" + "a1" * 18,
    "slack_token": "xoxb-" + "1234567890-abc",
    "stripe_key": "sk_" + "live_" + "Z" * 24,
    "google_key": "AIza" + "B" * 35,
    "ai_key": "sk-ant-" + "c" * 30,
    "jwt": "eyJ" + "h" * 10 + ".eyJ" + "p" * 10 + "." + "s" * 12,
}


def test_known_formats():
    for kind, token in TOKENS.items():
        text, hits = redact(f"value = {token} end")
        assert token not in text and f"[REDACTED:{kind}]" in text and hits >= 1, kind


def test_contextual_secrets():
    cases = [
        ('smtp_password: str = "hunter2-hunter2"', "hunter2-hunter2"),
        ("API_TOKEN=abcdefgh12345", "abcdefgh12345"),
        ("postgresql://app:s3cr3t-pw@db:5432/x", "s3cr3t-pw"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----", "MIIabc"),
    ]
    for source, secret in cases:
        text, _ = redact(source)
        assert secret not in text, source
    assert redact('name = "leave-desk"') == ('name = "leave-desk"', 0)
    once, _ = redact('token = "abcdefgh12345"')
    assert redact(once) == (once, 0)


def test_secret_files():
    assert all(is_secret_file(p) for p in [".env", "app/.env.production", "deploy/server.pem", "id_ed25519", "secrets.yaml"])
    assert not any(is_secret_file(p) for p in ["env.py", "app/keys.py", "README.md"])


def test_scan_output_is_redacted(tmp_path):
    (tmp_path / ".env").write_text("STRIPE=" + TOKENS["stripe_key"] + "\n")
    (tmp_path / "app.py").write_text(
        f"# TODO: rotate {TOKENS['github_token']}\n"
        f"def check(user, api_key):\n"
        f"    if user.role == 'admin' and api_key == '{TOKENS['aws_key']}':\n"
        f"        return True\n"
    )
    result = scan(tmp_path)
    text = str(result)
    assert all(t not in text for t in TOKENS.values())
    assert result["redactions"] == 2 and result["permission_branches"] and result["incomplete"]
