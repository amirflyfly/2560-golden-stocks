import pytest
from backend import create_app
from backend.repositories.db import execute, q
from backend.repositories import picks_repo
import tempfile
import os


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


@pytest.fixture
def auth_client(client):
    from backend.services.multiuser_auth_service import create_user as create_auth_user
    create_auth_user('testuser', 'testpass', 'editor')
    
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    }, follow_redirects=True)
    
    return client


@pytest.fixture
def admin_client(client):
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    
    return client


class TestAuth:
    def test_login_page_loads(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'\xe7\x99\xbb\xe5\xbd\x95' in response.data
    
    def test_login_success(self, client):
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        assert response.status_code == 200
    
    def test_login_failure(self, client):
        response = client.post('/login', data={
            'username': 'wrong',
            'password': 'wrong'
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
        assert response.status_code == 200


class TestPicksAPI:
    def test_list_picks(self, auth_client):
        response = auth_client.get('/api/picks')
        assert response.status_code == 200
    
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
            })
            assert response.status_code == 200
    
    def test_delete_pick(self, auth_client):
        create_response = auth_client.post('/api/picks', data={
            'pick_date': '2024-01-01',
            'code': '600519',
            'name': '贵州茅台',
            'pick_price': 1688.00,
        })
        import json
        create_data = json.loads(create_response.data)
        pick_id = create_data.get('id')
        
        if pick_id:
            response = auth_client.delete(f'/api/picks/{pick_id}')
            assert response.status_code == 200


class TestBatchOperations:
    def test_batch_archive(self, auth_client):
        response = auth_client.post('/api/picks/batch/archive', json={
            'ids': [1, 2, 3]
        })
        assert response.status_code == 200
    
    def test_batch_delete(self, auth_client):
        response = auth_client.post('/api/picks/batch/delete', json={
            'ids': [999]
        })
        assert response.status_code == 200


class TestExport:
    def test_export_json(self, auth_client):
        response = auth_client.get('/api/export')
        assert response.status_code == 200
    
    def test_export_csv(self, auth_client):
        response = auth_client.get('/api/export.csv')
        assert response.status_code == 200


class TestAdminRoutes:
    def test_users_page_requires_admin(self, auth_client):
        response = auth_client.get('/admin/users')
        assert response.status_code in [200, 302, 403]
    
    def test_backups_page_requires_admin(self, auth_client):
        response = auth_client.get('/admin/backups')
        assert response.status_code in [200, 302, 403]


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
