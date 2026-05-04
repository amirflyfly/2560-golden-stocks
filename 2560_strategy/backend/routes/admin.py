from flask import Blueprint, render_template, request, session, flash, redirect, url_for, jsonify, Response
from functools import wraps

bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        token = session.get('auth_token')
        sess = get_session(token)
        if not sess or sess.get('role') != 'admin':
            flash('需要管理员权限', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    from backend.services.multiuser_auth_service import get_session
    token = session.get('auth_token')
    if token:
        sess = get_session(token)
        if sess:
            return {
                'user_id': sess.get('user_id'),
                'username': sess.get('username'),
                'role': sess.get('role'),
            }
    return None


def log_action(action, target_ids=None, detail=''):
    from backend.services.logs_service import log_action as do_log
    user = get_current_user() or {}
    do_log(action, target_ids=target_ids, detail=detail, actor=user)


@bp.route('/users')
@admin_required
def users():
    from backend.repositories.users_repo import list_users
    users_list = list_users()
    return render_template('admin/users.html', users=users_list, user=get_current_user())


@bp.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    from backend.services.users_admin_service import create_user
    
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'editor')
    
    ok, msg = create_user(username, password, role)
    log_action('create_user', [], msg)
    
    if ok:
        flash(msg, 'success')
    else:
        flash(msg, 'error')
    
    return redirect(url_for('admin.users'))


@bp.route('/users/toggle', methods=['POST'])
@admin_required
def toggle_user():
    from backend.services.users_admin_service import toggle_user_active
    
    user_id = request.form.get('user_id')
    is_active = request.form.get('is_active', '0')
    
    ok, msg = toggle_user_active(user_id, is_active)
    log_action('toggle_user', [user_id], msg)
    
    return jsonify({'success': ok, 'message': msg})


@bp.route('/users/reset-password', methods=['POST'])
@admin_required
def reset_password():
    from backend.services.users_admin_service import reset_password
    
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password', '')
    
    ok, msg = reset_password(user_id, new_password)
    log_action('reset_password', [user_id], msg)
    
    return jsonify({'success': ok, 'message': msg})


@bp.route('/backups')
@admin_required
def backups():
    from backend.services import backup_service
    backups_list = backup_service.list_backups()
    stats = backup_service.backup_stats()
    return render_template('admin/backups.html', 
        backups=backups_list, 
        stats=stats, 
        user=get_current_user()
    )


@bp.route('/backups/create', methods=['POST'])
@admin_required
def create_backup():
    from backend.services import backup_service
    
    user = get_current_user() or {}
    zip_bytes = backup_service.make_backup_zip_bytes(actor=user)
    backup_service.save_backup_zip_to_disk(zip_bytes, prefix='manual', actor_username=user.get('username', ''))
    log_action('backup_download', [], '下载备份包')
    
    return Response(
        zip_bytes,
        mimetype='application/zip',
        headers={'Content-Disposition': 'attachment; filename="backup.zip"'}
    )


@bp.route('/backups/<name>')
@admin_required
def download_backup(name):
    from backend.services import backup_service
    
    try:
        zip_bytes = backup_service.read_backup_zip_bytes(name)
        log_action('backup_download_history', [], f'下载历史备份 {name}')
        return Response(
            zip_bytes,
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{name}"'}
        )
    except Exception as e:
        flash(f'下载失败：{e}', 'error')
        return redirect(url_for('admin.backups'))


@bp.route('/backups/<name>/detail')
@admin_required
def backup_detail(name):
    from backend.services import backup_service
    
    try:
        zip_bytes = backup_service.read_backup_zip_bytes(name)
        ok, msg = backup_service.validate_backup_zip_bytes(zip_bytes)
        if not ok:
            flash(msg, 'error')
            return redirect(url_for('admin.backups'))
        meta = backup_service.read_backup_meta(zip_bytes)
        return render_template('admin/backup_detail.html', 
            name=name, 
            meta=meta, 
            user=get_current_user()
        )
    except Exception as e:
        flash(f'读取备份失败：{e}', 'error')
        return redirect(url_for('admin.backups'))


@bp.route('/restore', methods=['GET'])
@admin_required
def restore_page():
    return render_template('admin/restore.html', user=get_current_user())


@bp.route('/restore', methods=['POST'])
@admin_required
def restore_upload():
    from backend.services import backup_service
    
    if 'backup_zip' not in request.files:
        flash('未选择文件', 'error')
        return redirect(url_for('admin.restore_page'))
    
    file = request.files['backup_zip']
    if file.filename == '':
        flash('未选择文件', 'error')
        return redirect(url_for('admin.restore_page'))
    
    zip_bytes = file.read()
    ok, msg = backup_service.validate_backup_zip_bytes(zip_bytes)
    if not ok:
        flash(msg, 'error')
        return redirect(url_for('admin.restore_page'))
    
    meta = backup_service.read_backup_meta(zip_bytes)
    tmp_key = backup_service.save_restore_upload(zip_bytes)
    
    return render_template('admin/restore_preview.html', 
        meta=meta, 
        tmp_key=tmp_key, 
        user=get_current_user()
    )


@bp.route('/restore/confirm', methods=['POST'])
@admin_required
def restore_confirm():
    from backend.services import backup_service
    from backend.services.multiuser_auth_service import logout
    
    tmp_key = request.form.get('tmp_key', '').strip()
    
    try:
        zip_bytes = backup_service.load_restore_upload(tmp_key)
    except Exception as e:
        flash(f'恢复文件已过期或不存在：{e}', 'error')
        return redirect(url_for('admin.restore_page'))
    
    ok, msg = backup_service.restore_from_backup_zip_bytes(zip_bytes)
    log_action('restore', [], f"恢复备份 -> {msg}")
    backup_service.delete_restore_upload(tmp_key)
    
    token = session.get('auth_token')
    if token:
        logout(token)
    session.clear()
    
    flash('恢复成功，请重新登录', 'success')
    return redirect(url_for('main.login'))


@bp.route('/backup-key')
@admin_required
def backup_key():
    from backend.services import backup_service
    has_key = backup_service._get_hmac_key() is not None
    return render_template('admin/backup_key.html', 
        has_key=has_key, 
        user=get_current_user()
    )


@bp.route('/backup-key/rotate', methods=['POST'])
@admin_required
def rotate_key():
    from backend.services import backup_service
    backup_service.rotate_hmac_key()
    log_action('backup_key_rotate', [], '轮换备份签名密钥')
    flash('已轮换密钥（已保留旧密钥用于验证旧备份）', 'success')
    return redirect(url_for('admin.backup_key'))


@bp.route('/backup-key/download')
@admin_required
def download_key():
    from backend.services import backup_service
    from pathlib import Path
    
    key_path = backup_service.DATA_DIR / 'backup_hmac_key.txt'
    if not key_path.exists():
        flash('密钥文件不存在', 'error')
        return redirect(url_for('admin.backup_key'))
    
    log_action('backup_key_download', [], '下载备份签名密钥')
    return Response(
        key_path.read_bytes(),
        mimetype='text/plain',
        headers={'Content-Disposition': 'attachment; filename="backup_hmac_key.txt"'}
    )


@bp.route('/backup-key/import', methods=['GET'])
@admin_required
def import_key_page():
    return render_template('admin/backup_key_import.html', user=get_current_user())


@bp.route('/backup-key/import/current', methods=['POST'])
@admin_required
def import_current_key():
    from backend.services import backup_service
    
    if 'key_file' not in request.files:
        flash('未选择文件', 'error')
        return redirect(url_for('admin.import_key_page'))
    
    file = request.files['key_file']
    key_bytes = file.read().strip() + b'\n'
    
    path = backup_service.DATA_DIR / 'backup_hmac_key.txt'
    path.write_bytes(key_bytes)
    log_action('backup_key_import_current', [], '导入当前备份签名密钥')
    
    flash('已导入当前密钥', 'success')
    return redirect(url_for('admin.backup_key'))


@bp.route('/migration-check')
@admin_required
def migration_check():
    from backend.repositories.db import q
    picks_cols = q("PRAGMA table_info(picks)")
    return render_template('admin/migration_check.html', 
        picks_cols=picks_cols, 
        user=get_current_user()
    )
