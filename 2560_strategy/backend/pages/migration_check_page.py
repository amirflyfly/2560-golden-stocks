"""Page: migration/health checklist for backup verification (admin)."""

from backend.services import backup_service
from backend.ui.html_helpers import esc, layout_page, render_nav


def render_migration_check_page():
    key_path, legacy_path = backup_service._key_file_paths()
    backups = backup_service.list_backups(limit=5)

    checks = []
    checks.append(('当前 key 存在', key_path.exists(), str(key_path)))
    checks.append(('旧 key 列表存在（可选）', legacy_path.exists(), str(legacy_path)))

    # validate latest backup if exists
    latest_ok = None
    latest_name = ''
    latest_msg = ''
    if backups:
        latest_name = backups[0]['name']
        try:
            ok, status = backup_service.cached_validate_backup(latest_name)
            latest_ok = ok
            latest_msg = status
        except Exception as e:
            latest_ok = False
            latest_msg = str(e)

    if latest_ok is not None:
        checks.append((f'最近备份可通过校验：{latest_name}', bool(latest_ok), latest_msg))
    else:
        checks.append(('最近备份可通过校验', False, '未找到任何备份文件'))

    items = []
    for name, ok, detail in checks:
        items.append(
            f"<div class='card' style='border:1px solid {'#bbf7d0' if ok else '#fecaca'};background:{'#ecfdf5' if ok else '#fef2f2'}'>"
            f"<div style='font-weight:700'>{esc(name)}</div>"
            f"<div class='muted' style='margin-top:6px'>{esc(detail)}</div>"
            f"</div>"
        )

    checklist = [
        '1) 在旧机器：打开 /backup-key 下载 backup_hmac_key.txt（以及如有 backup_hmac_keys.txt 也导出）',
        '2) 在旧机器：打开 /backups 下载最近一份备份 zip',
        '3) 在新机器：先导入密钥（/backup-key/import），再上传恢复备份（/restore）',
        '4) 在新机器：打开本页面确认“最近备份校验 OK”',
    ]

    body = f"""
<div class='topline'><div><h1>迁移检查 / Checklist</h1><div class='muted'>用于更换家里服务器/迁移机器后确认备份验证链路正常。</div></div><div><a class='btn' href='/backups'>返回备份管理</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
<div class='grid2 section'>
  {''.join(items)}
</div>
<div class='section card'>
  <h2>迁移步骤清单</h2>
  <ol>
    {''.join([f'<li style="margin:6px 0">{esc(x)}</li>' for x in checklist])}
  </ol>
</div>
"""
    return layout_page('迁移检查', body)
