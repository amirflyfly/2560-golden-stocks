"""Page: backup key import (admin)."""

from backend.ui.html_helpers import esc, layout_page, render_nav


def render_backup_key_import_page(message=''):
    msg_html = f"<div class='card' style='background:#eff6ff;border:1px solid #bfdbfe'>{esc(message)}</div>" if message else ''
    body = f"""
<div class='topline'><div><h1>导入备份签名密钥</h1><div class='muted'>仅管理员可见。用于迁移到新机器后继续验证旧备份。</div></div><div><a class='btn' href='/backup-key'>返回</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>导入当前 key（backup_hmac_key.txt）</h2>
  <form method='post' action='/backup-key/import-current' enctype='multipart/form-data'>
    <input type='file' name='key_file' accept='.txt' required>
    <button type='submit' style='margin-top:12px'>导入当前 key</button>
  </form>
</div>
<div class='section card'>
  <h2>导入旧 key 列表（backup_hmac_keys.txt，可选）</h2>
  <div class='muted'>用于验证更早的历史备份签名（多次轮换后）。</div>
  <form method='post' action='/backup-key/import-legacy' enctype='multipart/form-data'>
    <input type='file' name='legacy_file' accept='.txt' required>
    <button type='submit' style='margin-top:12px'>导入旧 key 列表</button>
  </form>
</div>
"""
    return layout_page('导入备份签名密钥', body)
