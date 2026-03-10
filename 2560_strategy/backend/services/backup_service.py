"""Backup and restore helpers (方案B).

Backup includes:
- SQLite DB file (picks.db)
- Optional legacy secret file (web_panel_secret.txt) if present
- A small metadata json

Restore supports replacing picks.db (with an auto-backup of current state).
"""

import io
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from backend.repositories.db import DATA_DIR, DB_PATH
from backend.app_config import BACKUP_RETENTION


LEGACY_SECRET = DATA_DIR / 'web_panel_secret.txt'


def _now_stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_dir():
    d = DATA_DIR / 'backups'
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_backup_zip_bytes(actor=None):
    """Create an in-memory zip for download."""
    actor = actor or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        meta = {
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'actor': {k: actor.get(k) for k in ['user_id', 'username', 'role']},
            'files': [],
        }

        if DB_PATH.exists():
            z.write(DB_PATH, arcname='data/picks.db')
            meta['files'].append('data/picks.db')

        if LEGACY_SECRET.exists():
            z.write(LEGACY_SECRET, arcname='data/web_panel_secret.txt')
            meta['files'].append('data/web_panel_secret.txt')

        z.writestr('meta.json', json.dumps(meta, ensure_ascii=False, indent=2))

    return buf.getvalue()


def save_backup_zip_to_disk(zip_bytes: bytes, prefix='backup'):
    """Save zip to data/backups and enforce retention."""
    bdir = backup_dir()
    path = bdir / f"{prefix}_{_now_stamp()}.zip"
    path.write_bytes(zip_bytes)

    # retention cleanup
    zips = sorted(bdir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in zips[BACKUP_RETENTION:]:
        try:
            p.unlink()
        except Exception:
            pass
    return path


def restore_from_backup_zip_bytes(zip_bytes: bytes):
    """Restore picks.db from a backup zip. Auto-backup current DB first."""
    # auto-backup current
    if DB_PATH.exists():
        cur_bytes = make_backup_zip_bytes(actor={'username': 'system', 'role': 'system'})
        save_backup_zip_to_disk(cur_bytes, prefix='auto_before_restore')

    # extract into temp
    tmp = DATA_DIR / f".restore_tmp_{_now_stamp()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
            z.extractall(tmp)

        src_db = tmp / 'data' / 'picks.db'
        if not src_db.exists():
            raise ValueError('备份包中未找到 data/picks.db')

        # replace DB atomically
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        dst = DB_PATH
        tmp_dst = DATA_DIR / f"picks.db.restoring.{os.getpid()}"
        shutil.copy2(src_db, tmp_dst)
        os.replace(tmp_dst, dst)

        # optional legacy secret
        src_secret = tmp / 'data' / 'web_panel_secret.txt'
        if src_secret.exists():
            shutil.copy2(src_secret, LEGACY_SECRET)

        return True, '恢复完成'
    finally:
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass
