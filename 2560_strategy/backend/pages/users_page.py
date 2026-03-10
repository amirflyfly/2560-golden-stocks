"""Page: user management (admin)."""

from backend.repositories.db import q
from backend.ui.html_helpers import esc, layout_page, render_nav


def render_users_page(message=''):
    users = q('SELECT id, username, role, is_active, created_at FROM users ORDER BY id ASC')
    msg_html = f"<div class='card' style='background:#eff6ff;border:1px solid #bfdbfe'>{esc(message)}</div>" if message else ''
    rows = ''.join([
        f"<tr><td>{u['id']}</td><td>{esc(u['username'])}</td><td>{esc(u['role'])}</td><td>{'启用' if int(u['is_active'] or 0)==1 else '停用'}</td><td>{esc(u['created_at'])}</td>"
        f"<td><form method='post' action='/users/toggle' class='inline-form'><input type='hidden' name='user_id' value='{u['id']}'><input type='hidden' name='is_active' value='{0 if int(u['is_active'] or 0)==1 else 1}'><button type='submit' class='linkbtn'>{'停用' if int(u['is_active'] or 0)==1 else '启用'}</button></form>"
        f"<form method='post' action='/users/reset' class='inline-form' onsubmit=\"return confirm('确认重置密码？')\"><input type='hidden' name='user_id' value='{u['id']}'><input name='new_password' placeholder='新密码' style='width:140px;padding:6px 8px;border:1px solid #d1d5db;border-radius:8px'><button type='submit' class='linkbtn danger'>重置密码</button></form></td></tr>"
        for u in users
    ]) or '<tr><td colspan="6">暂无用户</td></tr>'

    body = f"""
<div class='topline'><div><h1>用户管理</h1><div class='muted'>仅管理员可见。用于团队多人使用、权限与安全管理。</div></div><div><a class='btn' href='/'>返回面板</a></div></div>
<div class='nav'>{render_nav('dashboard')}</div>
{msg_html}
<div class='section card'>
  <h2>创建新用户</h2>
  <form method='post' action='/users/create'>
    <div class='formgrid3'>
      <div><label>用户名</label><input name='username' required></div>
      <div><label>密码</label><input name='password' required></div>
      <div><label>角色</label>
        <select name='role'>
          <option value='admin'>admin</option>
          <option value='editor' selected>editor</option>
          <option value='viewer'>viewer</option>
        </select>
      </div>
    </div>
    <div style='margin-top:12px'><button type='submit'>创建用户</button></div>
  </form>
</div>

<div class='section card'>
  <h2>用户列表</h2>
  <div class='tablewrap'><table>
    <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</div>
"""
    return layout_page('用户管理', body)
