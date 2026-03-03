from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess
import datetime
import os

def job():
    print(f"⏰ 触发定时任务：2560 战法选股... 时间：{datetime.datetime.now()}")
    # 执行选股脚本
    subprocess.run(["python", "strategy_2560.py"], check=True)

if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    
    # 添加两个任务：工作日 10:30 和 14:30
    # 注意：这里简单设置为每天，实际可在脚本内判断是否为交易日
    scheduler.add_job(job, CronTrigger(hour=10, minute=30), id='morning_scan')
    scheduler.add_job(job, CronTrigger(hour=14, minute=30), id='afternoon_scan')
    
    print("📅 定时任务已启动:")
    print("   - 每个交易日 10:30 执行早盘扫描")
    print("   - 每个交易日 14:30 执行尾盘扫描")
    print("等待触发中... (按 Ctrl+C 停止)")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("定时任务已停止")
