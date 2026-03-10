"""Import/export helpers.

Phase 2 split: move CSV import/export routines out of web_panel.py.
"""

import csv
import io

from backend.repositories.db import execute, q1
from backend.services.format_service import num, int_num


EXPORT_COLUMNS = [
    'id', 'pick_date', 'code', 'name', 'pick_price', 'signal', 'source', 'source_channel',
    'reason_tag', 'review_status', 'result_grade', 'inquiry_count', 'deal_status',
    'secondary_spread', 'content_title', 'content_ref', 'note', 'archived', 'created_at'
]


def bulk_import_from_csv(csv_text):
    csv_text = (csv_text or '').strip()
    if not csv_text:
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    imported_ids = []
    for row in reader:
        if not any((v or '').strip() for v in row.values()):
            continue
        execute(
            '''INSERT OR REPLACE INTO picks
            (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref, archived, result_grade, inquiry_count, deal_status, secondary_spread)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)''',
            (
                (row.get('pick_date') or '').strip(), (row.get('code') or '').strip(), (row.get('name') or '').strip(), num(row.get('pick_price')),
                (row.get('signal') or '').strip(), 'csv-import', (row.get('source_channel') or 'csv').strip(), (row.get('reason_tag') or '').strip(),
                (row.get('note') or '').strip(), (row.get('review_status') or '未复盘').strip(), (row.get('review_comment') or row.get('note') or '').strip(),
                (row.get('content_title') or '').strip(), (row.get('content_ref') or '').strip(), (row.get('result_grade') or '待定').strip(),
                int_num(row.get('inquiry_count')), (row.get('deal_status') or '未成交').strip(), (row.get('secondary_spread') or '否').strip(),
            )
        )
        new_row = q1('SELECT id FROM picks ORDER BY id DESC LIMIT 1')
        if new_row:
            imported_ids.append(new_row['id'])
    return imported_ids


def rows_to_csv(rows, fieldnames=None):
    fieldnames = fieldnames or EXPORT_COLUMNS
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, '') for k in fieldnames})
    return output.getvalue()
