from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess
import datetime
import os
import urllib.request
from pathlib import Path

BASE_DIR = os.path.dirname(__file__)
VENV_PY = os.path.join(BASE_DIR, '.venv', 'bin', 'python')
PY = VENV_PY if os.path.exists(VENV_PY) else 'python'


def run_step(args, env=None):
    subprocess.run([PY] + args, check=True, env=env, cwd=BASE_DIR)


def ping_render_dashboard():
    url = 'https://dashboard.render.com'
    log_path = Path(BASE_DIR) / 'data' / 'render_dashboard_ping.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            line = f'[{ts}] status={r.status} url={url}'
    except Exception as e:
        line = f'[{ts}] error={e} url={url}'
    with log_path.open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(f'🌐 Render dashboard ping: {line}')


def morning_digest():
    print(f"🌅 触发早盘重点汇报... 时间：{datetime.datetime.now()}")
    run_step(['strategy_digest.py', 'am'])


def afternoon_digest():
    print(f"🌇 触发尾盘汇总汇报... 时间：{datetime.datetime.now()}")
    run_step(['strategy_digest.py', 'pm'])


def job():
    print(f"⏰ 触发定时任务：2560 战法选股... 时间：{datetime.datetime.now()}")
    env = os.environ.copy()
    env.setdefault('SCAN_LIMIT', '500')
    run_step(['strategy_2560.py'], env=env)
    run_step(['report_2560.py'])
    run_step(['init_tracker_db.py'])
    run_step(['ingest_daily_picks.py'])
    run_step(['first_limit_replay.py'])
    run_step(['first_limit_validate.py'])
    run_step(['review_metrics.py'])
    run_step(['leaderboards.py'])
    run_step(['master_ledger.py'])
    run_step(['daily_review_brief.py'])


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(ping_render_dashboard, CronTrigger(minute='*/10'), id='render_dashboard_ping')
    scheduler.add_job(morning_digest, CronTrigger(hour=9, minute=0), id='morning_digest')
    scheduler.add_job(job, CronTrigger(hour=10, minute=30), id='morning_scan')
    scheduler.add_job(job, CronTrigger(hour=14, minute=30), id='afternoon_scan')
    scheduler.add_job(afternoon_digest, CronTrigger(hour=15, minute=30), id='afternoon_digest')

    print("📅 定时任务已启动:")
    print("   - 每 10 分钟访问一次 https://dashboard.render.com 并写入日志")
    print("   - 每个交易日 09:00 推送昨日/今日重点关注策略汇报")
    print("   - 每个交易日 10:30 执行早盘扫描+入库+复盘+榜单+台账+日报")
    print("   - 每个交易日 14:30 执行尾盘扫描+入库+复盘+榜单+台账+日报")
    print("   - 每个交易日 15:30 推送今日策略运行汇总汇报")
    print("等待触发中... (按 Ctrl+C 停止)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("定时任务已停止")
