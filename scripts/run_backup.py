#!/usr/bin/env python3
"""Run a manual scheduled-style backup.

Use on home server with cron/systemd timers.
"""

import sys

# allow running from repo root
sys.path.insert(0, '2560_strategy')

from backend.repositories.db import ensure_schema
from backend.services import backup_service


def main():
    try:
        ensure_schema()
        zip_bytes = backup_service.make_backup_zip_bytes(actor={'username': 'system', 'role': 'system'})
        path = backup_service.save_backup_zip_to_disk(zip_bytes, prefix='scheduled', actor_username='system')
        print(f'backup saved: {path}')
        return 0
    except Exception as e:
        print(f'backup failed: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
