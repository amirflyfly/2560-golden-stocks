#!/bin/sh
set -eu

DUMP_PATH="${1:-/tmp/picks_dump.sql}"
RESTORE_DB="${2:-restore_check}"

case "$RESTORE_DB" in
  *[!A-Za-z0-9_]*|"")
    echo "unsafe restore database name: $RESTORE_DB" >&2
    exit 2
    ;;
esac

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "DROP DATABASE IF EXISTS \`$RESTORE_DB\`; CREATE DATABASE \`$RESTORE_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$RESTORE_DB" < "$DUMP_PATH"
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$RESTORE_DB" -N -e "SELECT COUNT(*) AS picks_count FROM picks; SELECT COUNT(*) AS picks_with_legacy_payload FROM picks WHERE legacy_payload_json IS NOT NULL;"
