"""Query filtering helpers.

Phase 2 split: move request params -> SQL WHERE clause logic here.
"""


def filter_where(params):
    wheres = []
    args = []
    keyword = (params.get('keyword', [''])[0] or '').strip()
    channel = (params.get('channel', [''])[0] or '').strip()
    tag = (params.get('tag', [''])[0] or '').strip()
    status = (params.get('status', [''])[0] or '').strip()
    date_from = (params.get('date_from', [''])[0] or '').strip()
    date_to = (params.get('date_to', [''])[0] or '').strip()
    archive = (params.get('archive', ['active'])[0] or 'active').strip()
    grade = (params.get('grade', [''])[0] or '').strip()
    deal_status = (params.get('deal_status', [''])[0] or '').strip()

    if keyword:
        wheres.append('(code LIKE ? OR name LIKE ? OR content_title LIKE ? OR content_ref LIKE ?)')
        kw = f'%{keyword}%'
        args += [kw, kw, kw, kw]
    if channel:
        wheres.append("COALESCE(NULLIF(source_channel,''),'system') = ?")
        args.append(channel)
    if tag:
        wheres.append("COALESCE(NULLIF(reason_tag,''),'未标注') = ?")
        args.append(tag)
    if status:
        wheres.append("COALESCE(NULLIF(review_status,''),'未复盘') = ?")
        args.append(status)
    if grade:
        wheres.append("COALESCE(NULLIF(result_grade,''),'待定') = ?")
        args.append(grade)
    if deal_status:
        wheres.append("COALESCE(NULLIF(deal_status,''),'未成交') = ?")
        args.append(deal_status)
    if date_from:
        wheres.append('pick_date >= ?')
        args.append(date_from)
    if date_to:
        wheres.append('pick_date <= ?')
        args.append(date_to)
    if archive == 'archived':
        wheres.append('COALESCE(archived, 0) = 1')
    elif archive != 'all':
        wheres.append('COALESCE(archived, 0) = 0')

    sql_where = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    return sql_where, args
