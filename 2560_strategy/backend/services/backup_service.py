"""Backup and restore helpers (方案B).

Backup includes:
- SQLite DB file (picks.db)
- Optional legacy secret file (web_panel_secret.txt) if present
- A small metadata json

Restore supports replacing picks.db (with an auto-backup of current state).
"""

import io
import hashlib
import hmac
import secrets
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
            db_bytes = DB_PATH.read_bytes()
            z.writestr('data/picks.db', db_bytes)
            meta['files'].append('data/picks.db')
            meta['picks_db'] = {'size': len(db_bytes), 'sha256': _sha256_bytes(db_bytes)}

        if LEGACY_SECRET.exists():
            z.write(LEGACY_SECRET, arcname='data/web_panel_secret.txt')
            meta['files'].append('data/web_panel_secret.txt')

        # HMAC key (needed to verify old backups after migration)
        key_file = DATA_DIR / 'backup_hmac_key.txt'
        if key_file.exists():
            z.write(key_file, arcname='data/backup_hmac_key.txt')
            meta['files'].append('data/backup_hmac_key.txt')

        meta['signature'] = _sign_meta(meta)
        z.writestr('meta.json', json.dumps(meta, ensure_ascii=False, indent=2))

    return buf.getvalue()


def save_backup_zip_to_disk(zip_bytes: bytes, prefix='backup', actor_username=''):
    actor_username = (actor_username or '').strip()
    """Save zip to data/backups and enforce retention."""
    bdir = backup_dir()
    safe_user = ''.join([c for c in actor_username if c.isalnum() or c in ('-','_')])[:20]
    user_part = f'_{safe_user}' if safe_user else ''
    path = bdir / f"{prefix}{user_part}_{_now_stamp()}.zip"
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



def list_backups(limit=50):
    bdir = backup_dir()
    items = []
    for z in sorted(bdir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)[: int(limit)]:
        st = z.stat()
        items.append({
            'name': z.name,
            'path': str(z),
            'size': st.st_size,
            'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })
    return items


def read_backup_zip_bytes(name: str):
    name = (name or '').strip()
    if not name or '/' in name or '..' in name:
        raise ValueError('invalid backup name')
    path = backup_dir() / name
    if not path.exists():
        raise FileNotFoundError(name)
    return path.read_bytes()



def validate_backup_zip_bytes(zip_bytes: bytes):
    """Basic validation: zip readable, contains data/picks.db and meta.json."""
    import zipfile
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
            names = set(z.namelist())
            if 'data/picks.db' not in names:
                return False, '备份包缺少 data/picks.db'
            if 'meta.json' not in names:
                return False, '备份包缺少 meta.json'
            try:
                import json
                meta = json.loads(z.read('meta.json').decode('utf-8'))
                if not isinstance(meta, dict):
                    return False, 'meta.json 格式不正确'
                # signature verification (optional)
                sig = meta.get('signature')
                if sig:
                    try:
                        ok_any = False
                        for k in _get_all_hmac_keys():
                            meta2 = dict(meta)
                            meta2.pop('signature', None)
                            payload = json.dumps(meta2, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
                            expect = hmac.new(k, payload, hashlib.sha256).hexdigest()
                            if str(sig) == str(expect):
                                ok_any = True
                                break
                        if not ok_any:
                            return False, '备份包签名校验失败（可能被篡改）'
                    except Exception:
                        return False, '备份包签名校验失败'
                # integrity check (optional)
                try:
                    pdb = meta.get('picks_db') or {}
                    if isinstance(pdb, dict) and pdb.get('sha256') and pdb.get('size') is not None:
                        db_bytes = z.read('data/picks.db')
                        if len(db_bytes) != int(pdb.get('size')):
                            return False, 'picks.db 大小不匹配（可能损坏）'
                        if _sha256_bytes(db_bytes) != str(pdb.get('sha256')):
                            return False, 'picks.db 哈希不匹配（可能损坏）'
                except Exception:
                    return False, '完整性校验失败'
            except Exception:
                return False, 'meta.json 无法解析'
        return True, 'ok'
    except Exception as e:
        return False, f'无效zip：{e}'



def read_backup_meta(zip_bytes: bytes):
    import zipfile
    import io
    import json
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
        meta_raw = z.read('meta.json')
    return json.loads(meta_raw.decode('utf-8'))



def cached_validate_backup(name: str):
    """Validate a backup file with a small cache in ui_settings.

    Cache key: backup_validate::<name>
    Value: <mtime>|OK or <mtime>|FAIL::<reason>
    """
    from backend.repositories.settings_repo import q1, execute
    from pathlib import Path
    path = backup_dir() / name
    st = path.stat()
    mtime = int(st.st_mtime)
    key = f'backup_validate::{name}'
    row = q1('SELECT setting_value FROM ui_settings WHERE setting_key=?', (key,))
    if row and row.get('setting_value'):
        val = row['setting_value']
        if val.startswith(str(mtime) + '|'):
            parts = val.split('|', 1)[1]
            if parts.startswith('OK'):
                return True, 'OK'
            return False, 'FAIL'
    try:
        zip_bytes = read_backup_zip_bytes(name)
        ok, msg = validate_backup_zip_bytes(zip_bytes)
        stored = f"{mtime}|{'OK' if ok else 'FAIL'}"
        execute(
            "INSERT INTO ui_settings (setting_key, setting_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP",
            (key, stored),
        )
        return ok, ('OK' if ok else 'FAIL')
    except Exception:
        stored = f"{mtime}|FAIL"
        execute(
            "INSERT INTO ui_settings (setting_key, setting_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP",
            (key, stored),
        )
        return False, 'FAIL'



def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()



def _get_hmac_key():
    """Return current HMAC key bytes."""
    return _get_all_hmac_keys()[0]



def _sign_meta(meta: dict) -> str:
    key = _get_hmac_key()
    # sign canonical JSON without signature field
    import json
    meta2 = dict(meta)
    meta2.pop('signature', None)
    payload = json.dumps(meta2, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hmac.new(key, payload, hashlib.sha256).hexdigest()



def save_restore_upload(zip_bytes: bytes):
    """Store uploaded restore zip temporarily and return a key."""
    import secrets
    tmp_dir = DATA_DIR / 'restore_uploads'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(16)
    path = tmp_dir / f'{key}.zip'
    path.write_bytes(zip_bytes)
    return key



def load_restore_upload(key: str) -> bytes:
    key = (key or '').strip()
    if not key or '/' in key or '..' in key:
        raise ValueError('invalid key')
    path = (DATA_DIR / 'restore_uploads') / f'{key}.zip'
    if not path.exists():
        raise FileNotFoundError(key)
    return path.read_bytes()



def delete_restore_upload(key: str):
    try:
        path = (DATA_DIR / 'restore_uploads') / f'{key}.zip'
        if path.exists():
            path.unlink()
    except Exception:
        pass



def _key_file_paths():
    from backend.app_config import BACKUP_HMAC_KEY_PATH
    key_path = DATA_DIR / 'backup_hmac_key.txt'
    legacy_path = DATA_DIR / 'backup_hmac_keys.txt'
    return key_path, legacy_path



def _get_all_hmac_keys():
    """Return list of keys (current first), creating current if missing."""
    key_path, legacy_path = _key_file_paths()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    if key_path.exists():
        k = key_path.read_text(encoding='utf-8').strip()
        if k:
            keys.append(k.encode('utf-8'))
    if legacy_path.exists():
        for line in legacy_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and line not in ('#',):
                keys.append(line.encode('utf-8'))
    if not keys:
        k = secrets.token_urlsafe(32)
        key_path.write_text(k, encoding='utf-8')
        keys = [k.encode('utf-8')]
    return keys



def rotate_hmac_key():
    """Rotate current key, keeping old key in legacy file for verification."""
    key_path, legacy_path = _key_file_paths()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    old = key_path.read_text(encoding='utf-8').strip() if key_path.exists() else ''
    new = secrets.token_urlsafe(32)
    key_path.write_text(new, encoding='utf-8')
    if old:
        prev = legacy_path.read_text(encoding='utf-8') if legacy_path.exists() else ''
        if prev and not prev.endswith('\n'):
            prev += '\n'
        legacy_path.write_text(prev + old + '\n', encoding='utf-8')
    return True





def backup_stats():
    """Return basic backup observability stats."""
    bdir = backup_dir()
    zips = sorted(bdir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
    total = len(zips)
    latest_time = None
    latest_name = ''
    if zips:
        latest_time = datetime.fromtimestamp(zips[0].stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        latest_name = zips[0].name
    # count fail among latest 50 (cached)
    fail = 0
    checked = 0
    for p in zips[:50]:
        try:
            ok, status = cached_validate_backup(p.name)
            checked += 1
            if not ok:
                fail += 1
        except Exception:
            checked += 1
            fail += 1
    return {
        'total': total,
        'latest_time': latest_time or '-',
        'latest_name': latest_name or '-',
        'checked': checked,
        'fail': fail,
    }
