import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.maintenance.legacy_sqlite_guard import refuse_production

refuse_production("ui_demo.py")

import werkzeug_patch
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    # 提供必要的上下文数据
    context = {
        'overview': {
            'total': 100,
            'strategies': 5,
            'today_count': 15,
            'total_picks': 500
        },
        'kpi': {
            'week_new': 25,
            'month_new': 100,
            'week_return': 5.2,
            'month_return': 15.8
        },
        'bstats': {
            'total': 50,
            'successful': 45,
            'failed': 5
        },
        'strategies': [
            {'id': 1, 'name': '2560战法', 'today_count': 10, 'total_count': 200},
            {'id': 2, 'name': '首板涨停', 'today_count': 5, 'total_count': 150},
            {'id': 3, 'name': '均线突破', 'today_count': 0, 'total_count': 100},
            {'id': 4, 'name': '量价背离', 'today_count': 0, 'total_count': 50}
        ],
        'today_picks': [
            {'code': '600000', 'name': '浦发银行', 'date': '2026-04-05', 'strategy': '2560战法', 'status': '已入库'},
            {'code': '600519', 'name': '贵州茅台', 'date': '2026-04-05', 'strategy': '2560战法', 'status': '已入库'},
            {'code': '000001', 'name': '平安银行', 'date': '2026-04-05', 'strategy': '首板涨停', 'status': '已入库'}
        ],
        'recent_records': [
            {'code': '600036', 'name': '招商银行', 'date': '2026-04-04', 'strategy': '2560战法', 'status': '已入库'},
            {'code': '000858', 'name': '五粮液', 'date': '2026-04-04', 'strategy': '2560战法', 'status': '已入库'},
            {'code': '601318', 'name': '中国平安', 'date': '2026-04-03', 'strategy': '首板涨停', 'status': '已入库'}
        ]
    }
    return render_template('dashboard.html', **context)

@app.route('/strategies')
def strategies():
    # 提供必要的上下文数据
    context = {
        'strategies': [
            {'id': 1, 'name': '2560战法', 'description': '25日均线与60日均量策略', 'created_at': '2026-01-01'},
            {'id': 2, 'name': '首板涨停', 'description': '首板涨停次日上车策略', 'created_at': '2026-01-02'},
            {'id': 3, 'name': '均线突破', 'description': '多均线突破策略', 'created_at': '2026-01-03'}
        ]
    }
    return render_template('strategies/index.html', **context)

@app.route('/profile')
def profile():
    # 提供必要的上下文数据
    context = {
        'user': {
            'username': '飞哥',
            'email': 'feige@example.com',
            'last_login': '2026-04-05 09:00:00'
        },
        'checkin_stats': {
            'consecutive_days': 7,
            'total_days': 30,
            'last_checkin': '2026-04-05'
        },
        'points': 1000,
        'point_records': [
            {'date': '2026-04-05', 'type': '签到', 'points': 10},
            {'date': '2026-04-04', 'type': '签到', 'points': 10},
            {'date': '2026-04-03', 'type': '策略运行', 'points': 5}
        ]
    }
    return render_template('user_profile.html', **context)

@app.route('/strategy/pool/<int:strategy_id>')
def strategy_pool(strategy_id):
    # 提供必要的上下文数据
    context = {
        'strategy': {
            'id': strategy_id,
            'name': '2560战法' if strategy_id == 1 else '首板涨停' if strategy_id == 2 else '均线突破',
            'code': '2560' if strategy_id == 1 else 'first_limit' if strategy_id == 2 else 'ma_breakout'
        },
        'stocks': [
            {'code': '600000', 'name': '浦发银行', 'date': '2026-04-05', 'status': '已入库'},
            {'code': '600519', 'name': '贵州茅台', 'date': '2026-04-05', 'status': '已入库'},
            {'code': '000001', 'name': '平安银行', 'date': '2026-04-05', 'status': '已入库'}
        ]
    }
    return render_template('strategies/pool.html', **context)

@app.route('/strategy/run/<int:strategy_id>')
def strategy_run(strategy_id):
    # 提供必要的上下文数据
    context = {
        'strategy': {
            'id': strategy_id,
            'name': '2560战法' if strategy_id == 1 else '首板涨停' if strategy_id == 2 else '均线突破'
        }
    }
    return render_template('strategies/run.html', **context)

@app.route('/strategy/backtest/<int:strategy_id>')
def strategy_backtest(strategy_id):
    # 提供必要的上下文数据
    context = {
        'strategy': {
            'id': strategy_id,
            'name': '2560战法' if strategy_id == 1 else '首板涨停' if strategy_id == 2 else '均线突破'
        }
    }
    return render_template('strategies/backtest.html', **context)

if __name__ == '__main__':
    print('🚀 UI Demo server running on http://localhost:8765')
    app.run(host='0.0.0.0', port=8765, debug=True)
