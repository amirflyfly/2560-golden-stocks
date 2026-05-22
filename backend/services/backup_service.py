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

from backend.app_config import BACKUP_RETENTION, DATA_DIR_NAME
from backend.core.config import get_settings


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / DATA_DIR_NAME
DB_PATH = DATA_DIR / 'picks.db'


LEGACY_SECRET = DATA_DIR / 'web_panel_secret.txt'
ALLOWED_RESTORE_MEMBERS = {'data/picks.db', 'data/web_panel_secret.txt', 'data/backup_hmac_key.txt', 'meta.json'}


def _production_sqlite_backup_blocked() -> bool:
    return (get_settings().environment or '').strip().lower() in {'prod', 'production'}


def _ensure_legacy_sqlite_backup_allowed():
    if _production_sqlite_backup_blocked():
        raise RuntimeError('Legacy SQLite backup/restore is disabled in production; use MySQL backup tooling.')


def _now_stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_dir():
    d = DATA_DIR / 'backups'
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_backup_zip_bytes(actor=None):
    """Create an in-memory zip for download."""
    _ensure_legacy_sqlite_backup_allowed()
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
    _ensure_legacy_sqlite_backup_allowed()
    valid, message = validate_backup_zip_bytes(zip_bytes)
    if not valid:
        return False, message
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
            (tmp / 'data').mkdir(parents=True, exist_ok=True)
            (tmp / 'data' / 'picks.db').write_bytes(z.read('data/picks.db'))
            if 'data/web_panel_secret.txt' in z.namelist():
                (tmp / 'data' / 'web_panel_secret.txt').write_bytes(z.read('data/web_panel_secret.txt'))

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
    if _production_sqlite_backup_blocked():
        return []
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
    _ensure_legacy_sqlite_backup_allowed()
    name = (name or '').strip()
    if not name or '/' in name or '..' in name:
        raise ValueError('invalid backup name')
    path = backup_dir() / name
    if not path.exists():
        raise FileNotFoundError(name)
    return path.read_bytes()



def validate_backup_zip_bytes(zip_bytes: bytes):
    """Basic validation: zip readable, contains data/picks.db and meta.json."""
    _ensure_legacy_sqlite_backup_allowed()
    import zipfile
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
            names = set(z.namelist())
            unsafe = _unsafe_zip_members(z.infolist())
            if unsafe:
                return False, f'备份包包含不安全路径：{unsafe[0]}'
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


def _unsafe_zip_members(infos: list[zipfile.ZipInfo]) -> list[str]:
    unsafe = []
    for info in infos:
        name = str(info.filename or '').replace('\\', '/')
        parts = [part for part in name.split('/') if part]
        if (
            not name
            or name.startswith('/')
            or ':' in name
            or '..' in parts
            or name not in ALLOWED_RESTORE_MEMBERS
        ):
            unsafe.append(name)
    return unsafe



def read_backup_meta(zip_bytes: bytes):
    _ensure_legacy_sqlite_backup_allowed()
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
    if _production_sqlite_backup_blocked():
        return False, 'DISABLED'
    from backend.repositories.settings_repo import get_ui_setting, set_ui_setting
    from pathlib import Path
    path = backup_dir() / name
    st = path.stat()
    mtime = int(st.st_mtime)
    key = f'backup_validate::{name}'
    val = get_ui_setting(key, '')
    if val:
        if val.startswith(str(mtime) + '|'):
            parts = val.split('|', 1)[1]
            if parts.startswith('OK'):
                return True, 'OK'
            return False, 'FAIL'
    try:
        zip_bytes = read_backup_zip_bytes(name)
        ok, msg = validate_backup_zip_bytes(zip_bytes)
        stored = f"{mtime}|{'OK' if ok else 'FAIL'}"
        set_ui_setting(key, stored)
        return ok, ('OK' if ok else 'FAIL')
    except Exception:
        stored = f"{mtime}|FAIL"
        set_ui_setting(key, stored)
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
    _ensure_legacy_sqlite_backup_allowed()
    import secrets
    tmp_dir = DATA_DIR / 'restore_uploads'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(16)
    path = tmp_dir / f'{key}.zip'
    path.write_bytes(zip_bytes)
    return key



def load_restore_upload(key: str) -> bytes:
    _ensure_legacy_sqlite_backup_allowed()
    key = (key or '').strip()
    if not key or '/' in key or '..' in key:
        raise ValueError('invalid key')
    path = (DATA_DIR / 'restore_uploads') / f'{key}.zip'
    if not path.exists():
        raise FileNotFoundError(key)
    return path.read_bytes()



def delete_restore_upload(key: str):
    if _production_sqlite_backup_blocked():
        return
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
    if _production_sqlite_backup_blocked():
        return {
            'total': 0,
            'latest_time': '-',
            'latest_name': '-',
            'checked': 0,
            'fail': 0,
            'disabled': True,
            'message': 'Legacy SQLite backup/restore is disabled in production.',
        }
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
