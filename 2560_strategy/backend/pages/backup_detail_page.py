"""Page: backup detail (meta)."""

import json

from backend.ui.html_helpers import esc, layout_page, render_nav


def render_backup_detail_page(name: str, meta: dict):
    meta_pretty = json.dumps(meta or {}, ensure_ascii=False, indent=2)
    body = f"""
<div class='topline'><div><h1>备份详情</h1><div class='muted'>文件：{esc(name)}</div></div><div><a class='btn' href='/backups'>返回备份管理</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
<div class='section card'>
  <h2>关键信息</h2>
  <div class='muted'>创建时间：{esc((meta or {}).get('created_at','-'))} · 创建者：{esc(str((meta or {}).get('actor',{})))} · 文件数：{len((meta or {}).get('files',[]) or [])}</div>
  <div class='muted' style='margin-top:6px'>包含文件：{esc(', '.join((meta or {}).get('files',[]) or []))}</div>
  <h2 style='margin-top:16px'>meta.json</h2>
  <textarea style='width:100%;min-height:260px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace' onclick='this.select()'>{esc(meta_pretty)}</textarea>
  <div class='muted'>点击文本框可一键全选复制</div>
</div>
"""
    return layout_page('备份详情', body)
