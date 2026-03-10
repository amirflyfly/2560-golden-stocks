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
    ensure_schema()
    zip_bytes = backup_service.make_backup_zip_bytes(actor={'username': 'system', 'role': 'system'})
    path = backup_service.save_backup_zip_to_disk(zip_bytes, prefix='scheduled', actor_username='system')
    print(f'backup saved: {path}')


if __name__ == '__main__':
    main()
