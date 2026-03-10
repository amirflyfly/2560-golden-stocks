"""Picks repository.

Phase 2: centralize picks table SQL here.
"""

from backend.repositories.db import q, q1, execute, execute_many


def get_pick_by_id(rid):
    return q1('SELECT * FROM picks WHERE id=?', (rid,))


def list_picks(where_sql='', args=None, limit=None, offset=None):
    args = args or []
    sql = f'SELECT * FROM picks {where_sql} ORDER BY pick_date DESC, id DESC'
    if limit is not None:
        sql += ' LIMIT ?'
        args = list(args) + [int(limit)]
    if offset is not None:
        sql += ' OFFSET ?'
        args = list(args) + [int(offset)]
    return q(sql, args)


def create_or_replace_pick(
    pick_date,
    code,
    name,
    pick_price,
    signal,
    source,
    source_channel,
    reason_tag,
    note,
    review_status,
    review_comment,
    content_title,
    content_ref,
    result_grade,
    inquiry_count,
    deal_status,
    secondary_spread,
):
    return execute(
        '''INSERT OR REPLACE INTO picks
        (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note,
         review_status, review_comment, content_title, content_ref, archived,
         result_grade, inquiry_count, deal_status, secondary_spread)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)''',
        (
            pick_date,
            code,
            name,
            pick_price,
            signal,
            source,
            source_channel,
            reason_tag,
            note,
            review_status,
            review_comment,
            content_title,
            content_ref,
            result_grade,
            inquiry_count,
            deal_status,
            secondary_spread,
        ),
    )


def update_pick(
    rid,
    pick_date,
    code,
    name,
    pick_price,
    signal,
    source_channel,
    reason_tag,
    note,
    review_status,
    review_comment,
    content_title,
    content_ref,
    result_grade,
    inquiry_count,
    deal_status,
    secondary_spread,
):
    return execute(
        '''UPDATE picks SET
            pick_date=?, code=?, name=?, pick_price=?, signal=?,
            source_channel=?, reason_tag=?, note=?, review_status=?, review_comment=?,
            content_title=?, content_ref=?, result_grade=?, inquiry_count=?, deal_status=?, secondary_spread=?
           WHERE id=?''',
        (
            pick_date,
            code,
            name,
            pick_price,
            signal,
            source_channel,
            reason_tag,
            note,
            review_status,
            review_comment,
            content_title,
            content_ref,
            result_grade,
            inquiry_count,
            deal_status,
            secondary_spread,
            rid,
        ),
    )


def set_archived(rid, archived: bool):
    return execute('UPDATE picks SET archived=? WHERE id=?', (1 if archived else 0, rid))


def delete_pick(rid):
    return execute('DELETE FROM picks WHERE id=?', (rid,))


def batch_set_archived(ids, archived: bool):
    return execute_many('UPDATE picks SET archived=? WHERE id=?', [(1 if archived else 0, i) for i in ids]) if ids else 0


def batch_delete(ids):
    return execute_many('DELETE FROM picks WHERE id=?', [(i,) for i in ids]) if ids else 0


def batch_set_review_status(ids, status):
    return execute_many('UPDATE picks SET review_status=? WHERE id=?', [(status, i) for i in ids]) if ids else 0


def batch_set_result_grade(ids, grade):
    return execute_many('UPDATE picks SET result_grade=? WHERE id=?', [(grade, i) for i in ids]) if ids else 0


def batch_set_deal_status(ids, deal_status):
    return execute_many('UPDATE picks SET deal_status=? WHERE id=?', [(deal_status, i) for i in ids]) if ids else 0


def batch_set_secondary_spread(ids, secondary_spread):
    return execute_many('UPDATE picks SET secondary_spread=? WHERE id=?', [(secondary_spread, i) for i in ids]) if ids else 0


def last_inserted_id():
    row = q1('SELECT id FROM picks ORDER BY id DESC LIMIT 1')
    return row['id'] if row else None



def count_picks(where_sql='', args=None):
    args = args or []
    row = q1(f'SELECT COUNT(*) AS cnt FROM picks {where_sql}', args)
    return int(row['cnt']) if row and row.get('cnt') is not None else 0
