"""Authentication / secret helpers."""

import secrets
from pathlib import Path


def ensure_secret(data_dir: Path, secret_path: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding='utf-8').strip()
    secret = secrets.token_urlsafe(8)
    secret_path.write_text(secret, encoding='utf-8')
    return secret
