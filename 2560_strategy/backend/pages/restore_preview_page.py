"""Page: restore preview (two-step confirm)."""

import json

from backend.ui.html_helpers import esc, layout_page, render_nav


def render_restore_preview_page(meta: dict, message=''):
    msg_html = f"<div class='card' style='background:#eff6ff;border:1px solid #bfdbfe'>{esc(message)}</div>" if message else ''
    meta_pretty = json.dumps(meta or {}, ensure_ascii=False, indent=2)
    body = f"""
<div class='topline'><div><h1>恢复预览</h1><div class='muted'>确认备份信息后，再点击“确认恢复”。</div></div><div><a class='btn' href='/restore'>返回上传页</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>关键信息</h2>
  <div class='muted'>创建时间：{esc((meta or {}).get('created_at','-'))} · 创建者：{esc(str((meta or {}).get('actor',{})))} · 文件：{esc(', '.join((meta or {}).get('files',[]) or []))}</div>
  <div class='muted' style='margin-top:6px'>picks.db：size={esc(str(((meta or {}).get('picks_db') or {}).get('size','-')))} sha256={esc(str(((meta or {}).get('picks_db') or {}).get('sha256','-')))}</div>
</div>
<div class='section card'>
  <h2>meta.json</h2>
  <textarea style='width:100%;min-height:220px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace' onclick='this.select()'>{esc(meta_pretty)}</textarea>
</div>
<div class='section card'>
  <h2>确认恢复</h2>
  <div class='muted'>确认后会覆盖当前数据库；系统会先自动备份当前数据。</div>
  <form method='post' action='/restore/confirm'>
    <input type='hidden' name='tmp_key' value='{esc((meta or {}).get('_tmp_key',''))}'>
    <button type='submit' onclick="return confirm('确认恢复？这会覆盖当前数据。')">确认恢复</button>
  </form>
</div>
"""
    return layout_page('恢复预览', body)
