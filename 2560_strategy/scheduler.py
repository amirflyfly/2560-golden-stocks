from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess
import datetime
import os

BASE_DIR = os.path.dirname(__file__)
VENV_PY = os.path.join(BASE_DIR, '.venv', 'bin', 'python')
PY = VENV_PY if os.path.exists(VENV_PY) else 'python'


def run_step(args, env=None):
    subprocess.run([PY] + args, check=True, env=env, cwd=BASE_DIR)


def job():
    print(f"⏰ 触发定时任务：2560 战法选股... 时间：{datetime.datetime.now()}")
    env = os.environ.copy()
    env.setdefault('SCAN_LIMIT', '500')
    run_step(['strategy_2560.py'], env=env)
    run_step(['report_2560.py'])
    run_step(['init_tracker_db.py'])
    run_step(['ingest_daily_picks.py'])
    run_step(['review_metrics.py'])
    run_step(['leaderboards.py'])
    run_step(['master_ledger.py'])
    run_step(['daily_review_brief.py'])


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(job, CronTrigger(hour=10, minute=30), id='morning_scan')
    scheduler.add_job(job, CronTrigger(hour=14, minute=30), id='afternoon_scan')

    print("📅 定时任务已启动:")
    print("   - 每个交易日 10:30 执行早盘扫描+入库+复盘+榜单+台账+日报")
    print("   - 每个交易日 14:30 执行尾盘扫描+入库+复盘+榜单+台账+日报")
    print("等待触发中... (按 Ctrl+C 停止)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("定时任务已停止")
