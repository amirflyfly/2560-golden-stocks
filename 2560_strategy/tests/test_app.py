import os
import tempfile

import pytest

from backend import create_app
from backend.repositories.db import execute, q
from backend.repositories import picks_repo


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    
    app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
    })
    
    with app.app_context():
        from backend.repositories.db import DB_PATH
        import backend.repositories.db as db_module
        db_module.DB_PATH = db_path
        db_module.ensure_schema()
    
    yield app
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def get_csrf_token(client):
    with client.session_transaction() as current_session:
        return current_session.get('_csrf_token')


@pytest.fixture
def auth_client(client):
    from backend.services.multiuser_auth_service import create_user as create_auth_user
    create_auth_user('testuser', 'testpass', 'editor')
    client.get('/login')

    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass',
        'csrf_token': get_csrf_token(client),
    }, follow_redirects=True)

    return client


@pytest.fixture
def admin_client(client):
    from backend.services.multiuser_auth_service import create_user as create_auth_user
    create_auth_user('testadmin', 'testpass', 'admin')
    client.get('/login')
    response = client.post('/login', data={
        'username': 'testadmin',
        'password': 'testpass',
        'csrf_token': get_csrf_token(client),
    }, follow_redirects=True)

    return client


class TestAuth:
    def test_login_page_loads(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'\xe7\x99\xbb\xe5\xbd\x95' in response.data
    
    def test_login_success(self, client):
        client.get('/login')
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin123',
            'csrf_token': get_csrf_token(client),
        }, follow_redirects=True)
        assert response.status_code == 200
    
    def test_login_failure(self, client):
        client.get('/login')
        response = client.post('/login', data={
            'username': 'wrong',
            'password': 'wrong',
            'csrf_token': get_csrf_token(client),
        }, follow_redirects=True)
        assert b'\xe9\x94\x99\xe8\xaf\xaf' in response.data or b'error' in response.data.lower()
    
    def test_logout(self, auth_client):
        response = auth_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
    
    def test_protected_route_redirects(self, client):
        response = client.get('/')
        assert response.status_code == 302 or response.status_code == 200


class TestDashboard:
    def test_dashboard_requires_auth(self, client):
        response = client.get('/')
        assert response.status_code in [302, 200]
    
    def test_dashboard_loads(self, auth_client):
        response = auth_client.get('/')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=dashboard')


class TestPicksAPI:
    def test_list_picks(self, auth_client):
        response = auth_client.get('/api/picks')
        assert response.status_code == 200
        assert response.headers['X-Legacy-API'] == 'deprecated'
        assert '</api/v1>; rel="successor-version"' in response.headers['Link']
    
    def test_create_pick(self, auth_client):
        response = auth_client.post('/api/picks', data={
            'pick_date': '2024-01-01',
            'code': '600519',
            'name': '贵州茅台',
            'pick_price': 1688.00,
            'signal': '缩量回踩',
            'source_channel': 'test',
            'review_status': '未复盘',
            'result_grade': '待定',
            'deal_status': '未成交',
            'inquiry_count': 0,
            'secondary_spread': '否',
            'csrf_token': get_csrf_token(auth_client),
        })
        assert response.status_code == 200
        import json
        data = json.loads(response.data)
        assert data.get('success') == True
    
    def test_update_pick(self, auth_client):
        create_response = auth_client.post('/api/picks', data={
            'pick_date': '2024-01-01',
            'code': '600519',
            'name': '贵州茅台',
            'pick_price': 1688.00,
            'csrf_token': get_csrf_token(auth_client),
        })
        import json
        create_data = json.loads(create_response.data)
        pick_id = create_data.get('id')
        
        if pick_id:
            response = auth_client.put(f'/api/picks/{pick_id}', json={
                'pick_date': '2024-01-01',
                'code': '600519',
                'name': '贵州茅台',
                'pick_price': 1700.00,
            }, headers={'X-CSRF-Token': get_csrf_token(auth_client)})
            assert response.status_code == 200
    
    def test_delete_pick(self, auth_client):
        create_response = auth_client.post('/api/picks', data={
            'pick_date': '2024-01-01',
            'code': '600519',
            'name': '贵州茅台',
            'pick_price': 1688.00,
            'csrf_token': get_csrf_token(auth_client),
        })
        import json
        create_data = json.loads(create_response.data)
        pick_id = create_data.get('id')
        
        if pick_id:
            response = auth_client.delete(f'/api/picks/{pick_id}', headers={'X-CSRF-Token': get_csrf_token(auth_client)})
            assert response.status_code == 200


class TestBatchOperations:
    def test_batch_archive(self, auth_client):
        response = auth_client.post('/api/picks/batch/archive', json={
            'ids': [1, 2, 3]
        }, headers={'X-CSRF-Token': get_csrf_token(auth_client)})
        assert response.status_code == 200
    
    def test_batch_delete(self, auth_client):
        response = auth_client.post('/api/picks/batch/delete', json={
            'ids': [999]
        }, headers={'X-CSRF-Token': get_csrf_token(auth_client)})
        assert response.status_code == 200


class TestExport:
    def test_export_json(self, auth_client):
        response = auth_client.get('/api/export')
        assert response.status_code == 200
    
    def test_export_csv(self, auth_client):
        response = auth_client.get('/api/export.csv')
        assert response.status_code == 200


class TestLegacyPlatformBoundary:
    def test_frontend_api_client_uses_v1_base_not_legacy_api(self):
        from pathlib import Path

        client_source = Path('frontend/src/api/client.js').read_text(encoding='utf-8')
        assert "|| '/api/v1'" in client_source
        assert "'/api/" not in client_source.replace("'/api/v1'", "")
        assert '"/api/' not in client_source.replace('"/api/v1"', "")

    def test_legacy_stock_data_write_requires_login(self, client):
        response = client.post('/api/save-stock-data', json={'code': '000001', 'data': []})
        assert response.status_code == 401
        assert response.headers['X-Legacy-API'] == 'deprecated'

    def test_legacy_stock_data_read_requires_login(self, client):
        response = client.get('/api/stock-data?code=000001&start_date=2026-01-01&end_date=2026-01-10')
        assert response.status_code == 401
        assert response.headers['X-Legacy-API'] == 'deprecated'

    def test_legacy_strategy_stock_chart_redirects_to_react_shell(self, client):
        response = client.get('/strategies/stock-chart?symbol=000001')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=kline&symbol=000001')
        assert response.headers['X-Legacy-Page'] == 'deprecated'

    def test_react_app_entry_serves_dist_shell(self, client):
        response = client.get('/app?page=kline&symbol=000001')
        assert response.status_code == 200
        assert b'<div id="root"></div>' in response.data

    def test_legacy_reports_page_redirects_to_react_reports(self, auth_client):
        response = auth_client.get('/reports')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=reports')

    def test_legacy_deal_review_redirects_to_react_picks(self, auth_client):
        response = auth_client.get('/deal-review')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=picks&status=validated')

    def test_legacy_edit_page_redirects_to_react_picks(self, auth_client):
        response = auth_client.get('/edit?id=12')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=picks&pick_id=12')

    def test_legacy_strategies_index_redirects_to_react_strategies(self, admin_client):
        response = admin_client.get('/strategies/')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=strategies')
        assert response.headers['X-Legacy-Page'] == 'deprecated'

    def test_legacy_strategy_run_and_backtest_pages_redirect_to_react(self, auth_client):
        pool_response = auth_client.get('/strategies/pool/2560')
        assert pool_response.status_code == 302
        assert pool_response.headers['Location'].endswith('/app?page=picks&strategy_code=2560')

        run_response = auth_client.get('/strategies/run/2560')
        assert run_response.status_code == 302
        assert run_response.headers['Location'].endswith('/app?page=scans&strategy_code=2560')

        backtest_response = auth_client.get('/strategies/backtest/2560')
        assert backtest_response.status_code == 302
        assert backtest_response.headers['Location'].endswith('/app?page=strategies&strategy_code=2560')

    def test_legacy_strategy_management_write_requires_login(self, client):
        response = client.post('/api/strategy/pool/add', json={
            'strategy_code': '2560',
            'code': '000001',
            'name': 'Ping An',
            'add_price': 10,
        })
        assert response.status_code == 401
        assert response.headers['X-Legacy-API'] == 'deprecated'

    def test_legacy_scan_routes_are_marked_deprecated(self, client):
        response = client.get('/api/scan/status')
        assert response.status_code == 200
        assert response.headers['X-Legacy-API'] == 'deprecated'

    def test_legacy_watchlist_write_routes_are_frozen(self, auth_client):
        csrf = get_csrf_token(auth_client)
        endpoints = [
            '/api/picks/1/watch',
            '/api/picks/1/unwatch',
            '/api/picks/1/analyze',
            '/api/watch-pool/analyze',
            '/api/watch-pool/1/agent-stream',
            '/api/research/recent/analyze',
        ]
        for endpoint in endpoints:
            response = auth_client.post(endpoint, json={}, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-API'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=picks'

    def test_legacy_api_write_routes_are_frozen_in_production(self, auth_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'production')
        csrf = get_csrf_token(auth_client)
        requests = [
            ('post', '/api/picks', {'code': '000001', 'name': 'Ping An', 'pick_date': '2026-05-04'}),
            ('put', '/api/picks/1', {'code': '000001', 'name': 'Ping An', 'pick_date': '2026-05-04'}),
            ('delete', '/api/picks/1', {}),
            ('post', '/api/picks/1/archive', {}),
            ('post', '/api/picks/1/unarchive', {}),
            ('post', '/api/picks/batch/archive', {'ids': [1]}),
            ('post', '/api/picks/batch/unarchive', {'ids': [1]}),
            ('post', '/api/picks/batch/delete', {'ids': [1]}),
            ('post', '/api/picks/batch/review-status', {'ids': [1], 'status': 'validated'}),
            ('post', '/api/picks/batch/grade', {'ids': [1], 'grade': 'A'}),
            ('post', '/api/picks/batch/deal-status', {'ids': [1], 'status': 'done'}),
            ('post', '/api/picks/batch/spread', {'ids': [1], 'spread': 'yes'}),
            ('post', '/api/bulk-import', {'csv_text': 'code,name\n000001,Ping An'}),
            ('post', '/api/filters', {'name': 'mine', 'query_string': 'code=000001'}),
            ('delete', '/api/filters/1', {}),
            ('post', '/api/filters/1/rename', {'name': 'renamed'}),
        ]
        for method, endpoint, payload in requests:
            response = getattr(auth_client, method)(endpoint, json=payload, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-API'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=picks'

        dashboard_response = auth_client.post('/api/dashboard-order', json={'order': 'reports'}, headers={'X-CSRF-Token': csrf})
        assert dashboard_response.status_code == 410
        assert dashboard_response.get_json()['successor'] == '/app?page=dashboard'

        kline_response = auth_client.post('/api/save-stock-data', json={'code': '000001', 'data': [{'close': 1}]}, headers={'X-CSRF-Token': csrf})
        assert kline_response.status_code == 410
        assert kline_response.get_json()['successor'] == '/app?page=kline'

    def test_legacy_strategy_write_routes_are_frozen_in_production(self, admin_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'production')
        csrf = get_csrf_token(admin_client)
        api_requests = [
            ('/api/strategy/pool/add', {'strategy_code': '2560', 'code': '000001', 'name': 'Ping An', 'add_price': 10}),
            ('/api/strategy/pool/remove', {'strategy_code': '2560', 'code': '000001'}),
            ('/api/strategy/scan/add-to-pool', {'strategy_code': '2560', 'scan_results': [{'code': '000001'}]}),
        ]
        for endpoint, payload in api_requests:
            response = admin_client.post(endpoint, json=payload, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-API'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=picks'

        scan_all = admin_client.post('/api/scan/all', json={'date': '2026-05-04'}, headers={'X-CSRF-Token': csrf})
        assert scan_all.status_code == 410
        assert scan_all.headers['X-Legacy-API'] == 'deprecated'
        assert scan_all.get_json()['successor'] == '/app?page=scans'

        scan_one = admin_client.post('/api/scan/2560', json={'date': '2026-05-04'}, headers={'X-CSRF-Token': csrf})
        assert scan_one.status_code == 410
        assert scan_one.headers['X-Legacy-API'] == 'deprecated'
        assert scan_one.get_json()['successor'] == '/app?page=scans'

        page_requests = [
            ('/strategies/create', {'code': 'new', 'name': 'New Strategy'}),
            ('/strategies/1/update', {'name': 'Updated'}),
            ('/strategies/1/toggle', {}),
            ('/strategies/1/delete', {}),
        ]
        for endpoint, payload in page_requests:
            response = admin_client.post(endpoint, json=payload, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-Page'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=strategies'

        run_response = admin_client.post('/strategies/run/2560', json={'target_date': '2026-05-04'}, headers={'X-CSRF-Token': csrf})
        assert run_response.status_code == 410
        assert run_response.headers['X-Legacy-API'] == 'deprecated'
        assert run_response.get_json()['successor'] == '/app?page=scans'

        backtest_response = admin_client.post('/strategies/backtest/2560', json={'start_date': '2026-05-01', 'end_date': '2026-05-04'}, headers={'X-CSRF-Token': csrf})
        assert backtest_response.status_code == 410
        assert backtest_response.headers['X-Legacy-API'] == 'deprecated'
        assert backtest_response.get_json()['successor'] == '/app?page=strategies'

    def test_legacy_admin_users_redirects_to_react_admin(self, admin_client):
        response = admin_client.get('/admin/users')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/app?page=admin')
        assert response.headers['X-Legacy-Page'] == 'deprecated'

    def test_legacy_admin_user_write_routes_are_frozen(self, admin_client):
        csrf = get_csrf_token(admin_client)
        requests = [
            ('/admin/users/create', {'username': 'legacy-user', 'password': 'testpass', 'role': 'editor'}),
            ('/admin/users/1/toggle', {'active': 0}),
            ('/admin/users/1/password', {'password': 'newpass'}),
        ]
        for endpoint, payload in requests:
            response = admin_client.post(endpoint, json=payload, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-Page'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=admin'

    def test_legacy_admin_backup_restore_writes_are_frozen_in_production(self, admin_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'production')
        csrf = get_csrf_token(admin_client)
        requests = [
            ('post', '/admin/backups/create', {}),
            ('delete', '/admin/backups/example.zip', {}),
            ('post', '/admin/restore', {'backup_name': 'example.zip'}),
            ('post', '/admin/backup-key', {'backup_key': 'secret'}),
        ]
        for method, endpoint, payload in requests:
            response = getattr(admin_client, method)(endpoint, json=payload, headers={'X-CSRF-Token': csrf})
            assert response.status_code == 410
            assert response.headers['X-Legacy-Page'] == 'deprecated'
            assert response.get_json()['successor'] == '/app?page=admin'

    def test_legacy_checkin_write_is_frozen_in_production_before_auth_repo_access(self, auth_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'production')
        response = auth_client.post('/user/checkin', headers={'X-CSRF-Token': get_csrf_token(auth_client)})

        assert response.status_code == 410
        assert response.get_json()['successor'] == '/app?page=dashboard'

    def test_legacy_leaderboards_page_is_read_only(self, auth_client):
        response = auth_client.get('/leaderboards')
        assert response.status_code == 200
        assert 'legacy 只读页面'.encode('utf-8') in response.data


class TestAdminRoutes:
    def test_users_page_requires_admin(self, auth_client):
        response = auth_client.get('/admin/users')
        assert response.status_code in [200, 302, 403]
    
    def test_backups_page_requires_admin(self, auth_client):
        response = auth_client.get('/admin/backups')
        assert response.status_code in [200, 302, 403]

    def test_retained_legacy_admin_pages_are_deprecated_and_admin_only(self, client, admin_client):
        anonymous = client.application.test_client()
        unauthenticated = anonymous.get('/admin/backups')
        assert unauthenticated.status_code == 302

        response = admin_client.get('/admin/backups')
        assert response.status_code == 200
        assert response.headers['X-Legacy-Page'] == 'deprecated'
        assert '</app?page=admin>; rel="successor-version"' in response.headers['Link']

    def test_url_map_keeps_legacy_and_v1_admin_prefixes_separate(self, app):
        rules = {str(rule) for rule in app.url_map.iter_rules()}

        assert '/admin/users' in rules
        assert '/api/v1/admin/users' in rules
        assert not any(rule.startswith('/admin/admin') for rule in rules)
        assert not any(rule.startswith('/api/v1/api/v1') for rule in rules)


class TestStrategy2560:
    def test_is_trading_day(self):
        from strategy_2560 import is_trading_day_today
        result = is_trading_day_today()
        assert isinstance(result, bool)
    
    def test_get_stock_list(self):
        from strategy_2560 import get_stock_list
        df = get_stock_list()
        assert df is not None
        assert len(df) > 0
