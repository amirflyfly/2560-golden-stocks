"""Page: backup HMAC key management (admin).

This page allows exporting the current key for migration.
Rotation is dangerous (old backups won't validate), so we only provide export.
"""

from backend.repositories.db import DATA_DIR
from backend.ui.html_helpers import esc, layout_page, render_nav


def render_backup_key_page(message=''):
    msg_html = f"<div class='card' style='background:#eff6ff;border:1px solid #bfdbfe'>{esc(message)}</div>" if message else ''
    body = f"""
<div class='topline'><div><h1>备份签名密钥</h1><div class='muted'>仅管理员可见。用于跨机器迁移后继续验证旧备份的签名。</div></div><div><a class='btn' href='/backups'>返回备份管理</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>导出密钥</h2>
  <div class='muted'>下载后请妥善保管。泄露会影响备份防篡改能力。</div>
  <p style='margin-top:12px'><a class='btn' href='/backup-key/download'>下载 backup_hmac_key.txt</a> <form method='post' action='/backup-key/rotate' class='inline-form' onsubmit="return confirm('确认轮换密钥？轮换后新备份将使用新签名，系统会保留旧密钥用于验证旧备份。')"><button type='submit' class='linkbtn danger'>轮换密钥</button></form></p>
</div>
"""
    return layout_page('备份签名密钥', body)
