"""Page: restore from backup."""

from backend.ui.html_helpers import esc, layout_page, render_nav


def render_restore_page(message=''):
    msg_html = f"<div class='card' style='background:#fff7ed;border:1px solid #fed7aa'>{esc(message)}</div>" if message else ''
    body = f"""
<div class='topline'><div><h1>恢复备份</h1><div class='muted'>上传备份 zip 后会覆盖当前数据库。系统会先自动备份一次当前数据。</div></div><div><a class='btn' href='/'>返回面板</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>上传备份包（zip）</h2>
  <form method='post' action='/restore' enctype='multipart/form-data'>
    <div style='margin-top:12px'><input type='file' name='backup_zip' accept='.zip' required></div>
    <div style='margin-top:12px'><button type='submit' onclick="return confirm('确认恢复？这会覆盖当前数据。')">开始恢复</button></div>
  </form>
</div>
"""
    return layout_page('恢复备份', body)
