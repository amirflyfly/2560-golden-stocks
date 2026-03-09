import argparse
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'


def main():
    parser = argparse.ArgumentParser(description='手动录入宣传好票')
    parser.add_argument('--date', required=True, help='推荐日期，如 2026-03-09')
    parser.add_argument('--code', required=True, help='股票代码')
    parser.add_argument('--name', required=True, help='股票名称')
    parser.add_argument('--price', required=True, type=float, help='推荐价')
    parser.add_argument('--signal', default='', help='信号/形态')
    parser.add_argument('--source', default='manual', help='来源系统')
    parser.add_argument('--channel', default='unknown', help='宣传渠道，如 douyin/xhs/live/community')
    parser.add_argument('--reason-tag', default='', help='推荐理由标签，如 趋势突破/缩量回踩')
    parser.add_argument('--note', default='', help='备注')
    parser.add_argument('--review-status', default='', help='人工复盘结论，如 值得复讲/逻辑一般/不建议再提')
    parser.add_argument('--review-comment', default='', help='人工复盘评论')
    parser.add_argument('--content-title', default='', help='关联内容标题')
    parser.add_argument('--content-ref', default='', help='关联内容链接/编号')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT OR REPLACE INTO picks
            (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                args.date, args.code, args.name, args.price, args.signal,
                args.source, args.channel, args.reason_tag, args.note,
                args.review_status, args.review_comment, args.content_title, args.content_ref
            )
        )
        conn.commit()
        print(f'录入成功: {args.date} {args.name}({args.code}) @ {args.price}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
