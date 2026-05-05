"""Run a safe backup/restore drill inside an isolated project data directory.

The drill never touches user personal directories. It temporarily redirects the
repository data paths to a temp directory, creates a SQLite backup zip, validates
it, restores it, and prints a machine-readable summary.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_drill() -> dict:
    from backend.repositories import db as db_module
    from backend.services import backup_service

    original_data_dir = db_module.DATA_DIR
    original_db_path = db_module.DB_PATH
    original_service_data_dir = backup_service.DATA_DIR
    original_service_db_path = backup_service.DB_PATH
    original_legacy_secret = backup_service.LEGACY_SECRET

    with tempfile.TemporaryDirectory(prefix="strategy_backup_drill_", ignore_cleanup_errors=True) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        data_dir = tmp_dir / "data"
        db_path = data_dir / "picks.db"
        data_dir.mkdir(parents=True, exist_ok=True)

        db_module.DATA_DIR = data_dir
        db_module.DB_PATH = db_path
        backup_service.DATA_DIR = data_dir
        backup_service.DB_PATH = db_path
        backup_service.LEGACY_SECRET = data_dir / "web_panel_secret.txt"

        try:
            db_module.ensure_schema()
            db_module.execute(
                "INSERT OR IGNORE INTO picks (pick_date, code, name, source) VALUES (?, ?, ?, ?)",
                ("2026-05-03", "000001", "平安银行", "drill"),
            )
            zip_bytes = backup_service.make_backup_zip_bytes(actor={"username": "drill", "role": "system"})
            valid, message = backup_service.validate_backup_zip_bytes(zip_bytes)
            if not valid:
                raise RuntimeError(f"backup validation failed: {message}")

            db_module.execute("DELETE FROM picks WHERE source=?", ("drill",))
            restored, restore_message = backup_service.restore_from_backup_zip_bytes(zip_bytes)
            if not restored:
                raise RuntimeError(restore_message)

            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM picks WHERE source='drill'").fetchone()[0]

            return {
                "ok": count == 1,
                "backup_bytes": len(zip_bytes),
                "validation": message,
                "restore": restore_message,
                "restored_drill_rows": count,
                "data_dir": str(data_dir),
            }
        finally:
            db_module.DATA_DIR = original_data_dir
            db_module.DB_PATH = original_db_path
            backup_service.DATA_DIR = original_service_data_dir
            backup_service.DB_PATH = original_service_db_path
            backup_service.LEGACY_SECRET = original_legacy_secret


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backup/restore drill in an isolated temp directory.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON output.")
    args = parser.parse_args()

    result = run_drill()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
