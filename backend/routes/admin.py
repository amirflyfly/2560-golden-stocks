import importlib
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, current_app, send_file, flash, redirect, url_for

from backend.repositories import users_repo, settings_repo
from backend.routes.main import admin_required
from backend.services.multiuser_auth_service import create_user as create_auth_user
from backend.services.multiuser_auth_service import set_user_active as set_auth_user_active
from backend.services.multiuser_auth_service import update_user_password as update_auth_user_password

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _is_production() -> bool:
    return (os.getenv('APP_ENV') or '').strip().lower() in {'prod', 'production'}


@bp.after_request
def add_legacy_admin_headers(response):
    response.headers['X-Legacy-Page'] = 'deprecated'
    response.headers['Link'] = '</app?page=admin>; rel="successor-version"'
    return response


@bp.before_request
def freeze_production_legacy_admin_writes_before_auth():
    if _is_production() and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return _legacy_admin_frozen_response()
    return None


def _legacy_admin_frozen_response(successor='/app?page=admin'):
    response = jsonify({
        'success': False,
        'message': 'legacy admin write endpoint is frozen; use the React v1 admin workflow',
        'successor': successor,
    })
    response.status_code = 410
    return response


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendor_tradingagents_root() -> Path:
    value = (os.environ.get('TRADINGAGENTS_ASHARE_DIR') or '').strip()
    if value:
        return Path(value).expanduser().resolve()
    return _repo_root() / 'vendor' / 'TradingAgents-AShare'


def _normalize_tradingagents_test_config(payload):
    return {
        'llm_provider': (payload.get('llm_provider', '') or '').strip() or 'openai',
        'backend_url': (payload.get('backend_url', '') or '').strip(),
        'api_key': (payload.get('api_key', '') or '').strip(),
        'deep_think_llm': (payload.get('deep_think_llm', '') or '').strip() or 'gpt-4o',
        'quick_think_llm': (payload.get('quick_think_llm', '') or '').strip() or 'gpt-4o-mini',
        'max_debate_rounds': max(1, min(6, int(payload.get('max_debate_rounds', 2) or 2))),
        'max_risk_discuss_rounds': max(1, min(4, int(payload.get('max_risk_discuss_rounds', 1) or 1))),
    }


def _run_tradingagents_model_test(config):
    provider = str(config.get('llm_provider') or '').strip().lower()
    api_key = str(config.get('api_key') or '').strip()
    model = str(config.get('quick_think_llm') or config.get('deep_think_llm') or '').strip()
    base_url = str(config.get('backend_url') or '').strip() or None
    if not provider:
        raise ValueError('请先填写 LLM Provider')
    if not api_key:
        raise ValueError('请先填写 API Key')
    if not model:
        raise ValueError('请先填写至少一个模型名')

    root = _vendor_tradingagents_root()
    if not root.exists():
        raise FileNotFoundError(f'TradingAgents-AShare 目录不存在: {root}')

    path_value = str(root)
    remove_after = False
    if path_value not in sys.path:
        sys.path.insert(0, path_value)
        remove_after = True

    try:
        factory_module = importlib.import_module('tradingagents.llm_clients.factory')
        create_llm_client = getattr(factory_module, 'create_llm_client')
        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=30,
            max_retries=0,
        )
        llm = client.get_llm()
        response = llm.invoke('Reply with exactly: TEST_OK')
        content = getattr(response, 'content', response)
        text = str(content or '').strip()
        if not text:
            raise RuntimeError('模型已返回响应，但内容为空')
        return {
            'provider': provider,
            'model': model,
            'base_url': base_url or '',
            'response_preview': text[:200],
        }
    finally:
        if remove_after:
            try:
                sys.path.remove(path_value)
            except ValueError:
                pass


@bp.route('/users')
@admin_required
def users():
    return redirect('/app?page=admin')


@bp.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    return _legacy_admin_frozen_response()


@bp.route('/users/<int:uid>/toggle', methods=['POST'])
@admin_required
def toggle_user(uid):
    return _legacy_admin_frozen_response()


@bp.route('/users/<int:uid>/password', methods=['POST'])
@admin_required
def reset_user_password(uid):
    return _legacy_admin_frozen_response()


@bp.route('/backups')
@admin_required
def backups():
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    items = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isfile(path):
            st = os.stat(path)
            items.append({
                'name': name,
                'size': st.st_size,
                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'created_at': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    items.sort(key=lambda x: x['name'], reverse=True)
    stats = {'total': len(items), 'checked': 0, 'fail': 0}
    return render_template('admin/backups.html', backups=items, stats=stats)


@bp.route('/backups/create', methods=['POST'])
@admin_required
def create_backup():
    if _is_production():
        return _legacy_admin_frozen_response()
    db_path = current_app.config.get('DB_PATH')
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_name = f'backup_{ts}.zip'
    out_path = os.path.join(backup_dir, out_name)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if db_path and os.path.exists(db_path):
            zf.write(db_path, arcname=os.path.basename(db_path))
        cfg = os.path.join(current_app.root_path, '..', 'config.json')
        cfg = os.path.abspath(cfg)
        if os.path.exists(cfg):
            zf.write(cfg, arcname='config.json')
    return jsonify({'success': True, 'name': out_name})


@bp.route('/backups/<name>/download')
@admin_required
def download_backup(name):
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    path = os.path.join(backup_dir, name)
    if not os.path.isfile(path):
        return '文件不存在', 404
    return send_file(path, as_attachment=True, download_name=name)


@bp.route('/backups/<name>')
@admin_required
def backup_detail(name):
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    path = os.path.join(backup_dir, name)
    if not os.path.isfile(path):
        return '文件不存在', 404
    st = os.stat(path)
    meta = {
        'created_at': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'legacy',
        'picks_count': '-',
        'actor': {'username': 'system'},
    }
    return render_template('admin/backup_detail.html', name=name, meta=meta)


@bp.route('/backups/<name>', methods=['DELETE'])
@admin_required
def delete_backup(name):
    if _is_production():
        return _legacy_admin_frozen_response()
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    path = os.path.join(backup_dir, name)
    if not os.path.isfile(path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    os.remove(path)
    return jsonify({'success': True})


@bp.route('/tradingagents-config', methods=['GET', 'POST'])
@admin_required
def tradingagents_config():
    presets = [
        {'id': 'openai', 'label': 'OpenAI', 'provider': 'openai', 'base_url': 'https://api.openai.com/v1'},
        {'id': 'anthropic', 'label': 'Anthropic', 'provider': 'anthropic', 'base_url': ''},
        {'id': 'google', 'label': 'Google Gemini', 'provider': 'google', 'base_url': ''},
        {'id': 'dashscope', 'label': '阿里云百炼', 'provider': 'openai', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1'},
        {'id': 'siliconflow', 'label': 'SiliconFlow', 'provider': 'openai', 'base_url': 'https://api.siliconflow.cn/v1'},
        {'id': 'custom', 'label': '自定义', 'provider': 'openai', 'base_url': ''},
    ]
    existing_config = settings_repo.get_tradingagents_runtime_config()
    if request.method == 'POST':
        config = _normalize_tradingagents_test_config(request.form)
        if not config.get('api_key') and existing_config.get('api_key'):
            config['api_key'] = existing_config.get('api_key', '')
        settings_repo.save_tradingagents_runtime_config(config)
        flash('TradingAgents 模型配置已保存', 'success')
        return redirect(url_for('admin.tradingagents_config'))

    config = dict(existing_config)
    masked_api_key = ''
    if config.get('api_key'):
        api_key = str(config.get('api_key') or '')
        if len(api_key) > 8:
            masked_api_key = f"{api_key[:4]}{'*' * max(4, len(api_key) - 8)}{api_key[-4:]}"
        else:
            masked_api_key = '*' * len(api_key)
        config['api_key'] = ''
    current_preset = 'custom'
    for item in presets:
        if item['provider'] == config.get('llm_provider') and (item['base_url'] or '') == (config.get('backend_url') or ''):
            current_preset = item['id']
            break
    return render_template(
        'admin/tradingagents_config.html',
        config=config,
        presets=presets,
        current_preset=current_preset,
        masked_api_key=masked_api_key,
        has_api_key=bool(existing_config.get('api_key')),
    )


@bp.route('/tradingagents-config/test', methods=['POST'])
@admin_required
def test_tradingagents_config():
    payload = request.get_json(silent=True) or request.form or {}
    try:
        config = _normalize_tradingagents_test_config(payload)
        result = _run_tradingagents_model_test(config)
        return jsonify({
            'success': True,
            'message': '模型连接测试成功',
            'result': result,
        })
    except Exception:
        current_app.logger.exception('tradingagents model test failed')
        return jsonify({
            'success': False,
            'message': '模型连接测试失败，请检查配置后重试',
        }), 400


@bp.route('/restore', methods=['GET'])
@admin_required
def restore_page():
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    items = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isfile(path):
            st = os.stat(path)
            items.append({
                'name': name,
                'size': st.st_size,
                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    items.sort(key=lambda x: x['name'], reverse=True)
    return render_template('admin/restore.html', backups=items)


@bp.route('/restore', methods=['POST'])
@admin_required
def restore_backup():
    if _is_production():
        return _legacy_admin_frozen_response()
    backup_name = request.form.get('backup_name', '').strip()
    provided_key = request.form.get('backup_key', '').strip()
    configured_key = current_app.config.get('BACKUP_KEY', '')

    if configured_key and provided_key != configured_key:
        return render_template('admin/restore_result.html', success=False, message='恢复密钥错误')

    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    path = os.path.join(backup_dir, backup_name)
    if not os.path.isfile(path):
        return render_template('admin/restore_result.html', success=False, message='备份文件不存在')

    try:
        root_dir = os.path.abspath(os.path.join(current_app.root_path, '..'))
        db_path = current_app.config.get('DB_PATH')
        temp_dir = os.path.join(backup_dir, f'_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        os.makedirs(temp_dir, exist_ok=True)
        with zipfile.ZipFile(path, 'r') as zf:
            zf.extractall(temp_dir)

        extracted_db = None
        extracted_cfg = os.path.join(temp_dir, 'config.json')
        for root, _, files in os.walk(temp_dir):
            for fn in files:
                if db_path and fn == os.path.basename(db_path):
                    extracted_db = os.path.join(root, fn)
                    break
            if extracted_db:
                break

        if db_path and extracted_db and os.path.exists(extracted_db):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            shutil.copy2(extracted_db, db_path)

        target_cfg = os.path.join(root_dir, 'config.json')
        if os.path.exists(extracted_cfg):
            shutil.copy2(extracted_cfg, target_cfg)

        shutil.rmtree(temp_dir, ignore_errors=True)
        return render_template(
            'admin/restore_result.html',
            success=True,
            message='恢复完成，建议刷新页面并重新检查数据。',
        )
    except Exception:
        current_app.logger.exception('restore backup failed')
        return render_template('admin/restore_result.html', success=False, message='恢复失败，请检查备份文件或稍后重试')


@bp.route('/backup-key', methods=['GET'])
@admin_required
def backup_key_page():
    has_backup_key = bool(current_app.config.get('BACKUP_KEY', '').strip())
    return render_template('admin/backup_key.html', has_backup_key=has_backup_key)


@bp.route('/backup-key', methods=['POST'])
@admin_required
def save_backup_key():
    if _is_production():
        return _legacy_admin_frozen_response()
    key = request.form.get('backup_key', '').strip()
    cfg_path = os.path.abspath(os.path.join(current_app.root_path, '..', 'config.json'))
    try:
        import json
        data = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data['backup_key'] = key
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        current_app.config['BACKUP_KEY'] = key
        flash('恢复密钥已保存', 'success')
        return redirect(url_for('admin.backup_key_page'))
    except Exception:
        current_app.logger.exception('save backup key failed')
        flash('保存失败，请稍后重试', 'danger')
        return redirect(url_for('admin.backup_key_page'))
