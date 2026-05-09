# 备份恢复演练 Runbook

## 范围

覆盖两类恢复场景：

1. 本地/开发默认 SQLite 与 `data/` 目录备份恢复。
2. 生产 MySQL dump 与 `data/` 目录文件备份恢复。

## 安全边界

- 演练脚本默认只操作项目目录下的 `data/` 和临时目录。
- 不扫描、不移动、不删除用户个人目录文件。
- 恢复前必须先生成当前状态的自动备份。
- 生产恢复必须先在隔离环境验证 dump 可用。

## SQLite / data 目录演练

推荐命令：

```bash
python scripts/backup_restore_drill.py --json
```

脚本会执行：

1. 确认 SQLite schema 可创建。
2. 生成 zip 备份。
3. 校验 `meta.json`、`data/picks.db`、签名和 sha256。
4. 在隔离临时 data 目录内恢复备份。
5. 重新校验恢复后的 DB 可连接、核心表可查询。
6. 输出 JSON 摘要。

## MySQL 生产备份命令清单

> 生产执行前请替换环境变量，确认目标目录在项目或受控备份目录中。

```bash
mysqldump --single-transaction --routines --triggers --default-character-set=utf8mb4 \
  --no-tablespaces \
  -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
  > "backups/mysql_${MYSQL_DATABASE}_$(date +%Y%m%d_%H%M%S).sql"
```

恢复预检：

```bash
mysql --default-character-set=utf8mb4 -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  -e "CREATE DATABASE IF NOT EXISTS restore_check CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql --default-character-set=utf8mb4 -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" restore_check \
  < backups/mysql_dump.sql
```

Docker Compose staging restore check:

```powershell
docker compose cp scripts\maintenance\mysql_restore_check.sh mysql:/tmp/mysql_restore_check.sh
docker compose exec mysql sh -lc "sed -i 's/\r$//' /tmp/mysql_restore_check.sh && sh /tmp/mysql_restore_check.sh /tmp/picks_dump.sql restore_check"
```

恢复验证：

```bash
python scripts/validate_mysql_schema.py
python scripts/bootstrap_mysql_seed.py --check-only
```

## data 目录备份建议

```bash
tar -czf "backups/data_$(date +%Y%m%d_%H%M%S).tar.gz" data
```

验证：

```bash
tar -tzf backups/data_YYYYMMDD_HHMMSS.tar.gz | head
```

## 恢复验收清单

- [ ] 数据库 schema 校验通过。
- [ ] 租户、用户、策略、扫描任务核心表可查询。
- [ ] 备份包签名与 sha256 校验通过。
- [ ] 恢复过程生成自动回滚备份。
- [ ] 恢复操作写入审计日志或运维记录。
- [ ] 前端健康检查、策略列表、扫描创建、任务列表可用。

## 事故回滚

1. 停止写入入口。
2. 保存事故现场备份。
3. 使用最近一次通过校验的备份恢复。
4. 运行 schema 与核心 API 验证。
5. 记录恢复时间、操作者、备份文件名、校验结果。
