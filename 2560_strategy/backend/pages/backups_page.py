"""Page: backups management."""

from backend.services import backup_service
from backend.ui.html_helpers import esc, layout_page, render_nav


def _fmt_size(n):
    n = int(n or 0)
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{n/1024:.1f} KB'
    return f'{n/1024/1024:.1f} MB'


def render_backups_page(message=''):
    backups = backup_service.list_backups(limit=200)
    msg_html = f"<div class='card' style='background:#eff6ff;border:1px solid #bfdbfe'>{esc(message)}</div>" if message else ''

    rows_list = []
    for b in backups:
        try:
            ok, _ = backup_service.validate_backup_zip_bytes(backup_service.read_backup_zip_bytes(b['name']))
            status = 'OK' if ok else 'FAIL'
        except Exception:
            status = 'FAIL'
        rows_list.append(
            f"<tr><td>{esc(b['mtime'])}</td><td>{esc(b['name'])}</td><td>{esc(_fmt_size(b['size']))}</td><td>{esc(status)}</td>"
            f"<td><a class='txtbtn' href='/backups/detail?name={esc(b['name'])}'>详情</a> "
            f"<a class='txtbtn' href='/backups/download?name={esc(b['name'])}'>下载</a>"
            f"<form method='post' action='/backups/restore' class='inline-form' onsubmit=\"return confirm(\\\"确认回滚到该备份？这会覆盖当前数据。\\\")\">"
            f"<input type='hidden' name='name' value='{esc(b['name'])}'><button type='submit' class='linkbtn danger'>回滚</button></form></td></tr>"
        )

    rows = ''.join(rows_list) or '<tr><td colspan="5">暂无备份</td></tr>'
    body = f"""
<div class='topline'><div><h1>备份管理</h1><div class='muted'>查看历史备份、下载备份、以及一键回滚。</div></div><div><a class='btn' href='/'>返回面板</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>手动备份</h2>
  <div class='muted'>点击后会生成一份备份并保存到 data/backups/，同时会下载一份 zip。</div>
  <p style='margin-top:12px'><a class='btn' href='/backup.zip'>立即生成并下载备份</a></p>
</div>
<div class='section card'>
  <h2>历史备份（最近200份）</h2>
  <div class='tablewrap'>
    <table>
      <thead><tr><th>时间</th><th>文件名</th><th>大小</th><th>校验</th><th>操作</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>
"""
    return layout_page('备份管理', body)
