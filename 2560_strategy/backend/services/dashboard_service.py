"""Dashboard data aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from backend.repositories import picks_repo
from backend.services.logs_service import recent_logs


_WORTHY_STATUSES = {"worthy", "worth_review", "review", "watch", "值得复盘"}
_DEAL_STATUSES = {"done", "deal", "dealt", "completed", "filled", "已成交"}
_SPREAD_STATUSES = {"yes", "true", "1", "是"}
_FIRST_LIMIT_STRATEGIES = {"FIRST_LIMIT_UP", "first_limit_up", "首板涨停策略", "首板涨停隔日", "首板策略"}
_POSITIVE_SECOND_BOARD_EXPECTATIONS = {"强", "高", "yes", "true", "1", "strong", "high"}
_SUCCESS_VALIDATION_STATUSES = {"成功", "命中", "hit", "success", "passed", "validated"}


def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _rows():
    return [row for row in picks_repo.list_picks(limit=100000) if not _safe_int(row.get("archived"))]


def _is_worthy(row):
    return (row.get("review_status") or "").strip() in _WORTHY_STATUSES


def _is_deal(row):
    return (row.get("deal_status") or "").strip() in _DEAL_STATUSES


def _is_spread(row):
    return (row.get("secondary_spread") or "").strip() in _SPREAD_STATUSES


def _is_first_limit_row(row):
    values = {
        str(row.get("strategy_code") or "").strip(),
        str(row.get("strategy_name") or "").strip(),
        str(row.get("source") or "").strip(),
    }
    return bool(values & _FIRST_LIMIT_STRATEGIES)


def _is_positive_second_board(row):
    return str(row.get("second_board_expectation") or "").strip() in _POSITIVE_SECOND_BOARD_EXPECTATIONS


def _is_validation_success(row):
    return str(row.get("validation_result") or "").strip() in _SUCCESS_VALIDATION_STATUSES


def _count_by(rows, key, default=""):
    counter = Counter((row.get(key) or default) for row in rows)
    return [{"name": name, "cnt": cnt} for name, cnt in counter.most_common()]


def dashboard_overview():
    rows = _rows()
    return {
        "total": len(rows),
        "active_total": len(rows),
        "deal_total": sum(1 for row in rows if _is_deal(row)),
        "spread_total": sum(1 for row in rows if _is_spread(row)),
        "worthy_total": sum(1 for row in rows if _is_worthy(row)),
    }


def dashboard_kpi():
    rows = _rows()
    today = date.today()
    total = len(rows)
    worthy = sum(1 for row in rows if _is_worthy(row))
    inquiries = [_safe_float(row.get("inquiry_count")) for row in rows]
    return {
        "week_new": sum(1 for row in rows if (_parse_date(row.get("pick_date")) or date.min) >= today - timedelta(days=6)),
        "last7_new": sum(1 for row in rows if (_parse_date(row.get("pick_date")) or date.min) >= today - timedelta(days=6)),
        "last30_new": sum(1 for row in rows if (_parse_date(row.get("pick_date")) or date.min) >= today - timedelta(days=29)),
        "worthy_rate": round(100.0 * worthy / total, 1) if total else 0,
        "avg_inquiry": round(sum(inquiries) / len(inquiries), 1) if inquiries else 0,
    }


def dashboard_channels():
    return _count_by(_rows(), "source_channel", "system")


def dashboard_tags():
    return _count_by(_rows(), "reason_tag", "untagged")


def dashboard_review_status():
    return _count_by(_rows(), "review_status", "pending")


def dashboard_grades():
    return _count_by(_rows(), "result_grade", "pending")


def dashboard_deals():
    return _count_by(_rows(), "deal_status", "not_dealt")


def dashboard_trend_30d():
    cutoff = date.today() - timedelta(days=29)
    counter = Counter()
    for row in _rows():
        parsed = _parse_date(row.get("pick_date"))
        if parsed and parsed >= cutoff:
            counter[str(parsed)] += 1
    return [{"name": key, "cnt": counter[key]} for key in sorted(counter)]


def dashboard_worthy_trend_30d():
    cutoff = date.today() - timedelta(days=29)
    counter = Counter()
    for row in _rows():
        parsed = _parse_date(row.get("pick_date"))
        if parsed and parsed >= cutoff and _is_worthy(row):
            counter[str(parsed)] += 1
    return [{"name": key, "cnt": counter[key]} for key in sorted(counter)]


def dashboard_deal_trend_30d():
    cutoff = date.today() - timedelta(days=29)
    counter = Counter()
    for row in _rows():
        parsed = _parse_date(row.get("pick_date"))
        if parsed and parsed >= cutoff and _is_deal(row):
            counter[str(parsed)] += 1
    return [{"name": key, "cnt": counter[key]} for key in sorted(counter)]


def recent_operation_logs(limit=15):
    return recent_logs(limit=limit)


def dashboard_strategy_summary():
    return _count_by(_rows(), "strategy_name", "2560")


def dashboard_strategy_panels():
    grouped = defaultdict(lambda: {"total": 0, "worthy_total": 0, "deal_total": 0, "return_sum": 0.0})
    for row in _rows():
        key = row.get("strategy_name") or "2560"
        item = grouped[key]
        item["total"] += 1
        item["worthy_total"] += 1 if _is_worthy(row) else 0
        item["deal_total"] += 1 if _is_deal(row) else 0
        item["return_sum"] += _safe_float(row.get("return_pct"))
    return [
        {
            "strategy_name": key,
            "total": item["total"],
            "worthy_total": item["worthy_total"],
            "deal_total": item["deal_total"],
            "avg_return": round(item["return_sum"] / item["total"], 2) if item["total"] else 0,
        }
        for key, item in sorted(grouped.items(), key=lambda pair: pair[1]["total"], reverse=True)
    ]


def dashboard_strategy_compare():
    return [
        {"name": item["strategy_name"], "total": item["total"], "avg_return": item["avg_return"], "deal_total": item["deal_total"]}
        for item in dashboard_strategy_panels()
    ]


def dashboard_second_board_pool():
    rows = [row for row in _rows() if _is_first_limit_row(row) and _is_positive_second_board(row)]
    rows.sort(key=lambda row: (_safe_float(row.get("second_board_score")), str(row.get("pick_date") or "")), reverse=True)
    return rows[:8]


def dashboard_watch_pool():
    rows = [row for row in _rows() if _safe_int(row.get("watch_flag")) == 1]
    rows.sort(key=lambda row: (str(row.get("pick_date") or ""), _safe_float(row.get("second_board_score"))), reverse=True)
    return rows[:10]


def dashboard_validate_rows():
    rows = [row for row in _rows() if _is_first_limit_row(row) and _safe_int(row.get("watch_flag")) == 1]
    rows.sort(key=lambda row: (str(row.get("pick_date") or ""), _safe_int(row.get("id"))), reverse=True)
    return rows[:10]


def dashboard_validate_stats():
    return _count_by([row for row in _rows() if _is_first_limit_row(row)], "validation_result", "pending")


def dashboard_validate_rate():
    rows = [row for row in _rows() if _is_first_limit_row(row)]
    return {"total": len(rows), "success": sum(1 for row in rows if _is_validation_success(row))}


def dashboard_hit_compare():
    grouped = defaultdict(lambda: {"total": 0, "hit_total": 0})
    for row in _rows():
        if not _is_first_limit_row(row):
            continue
        key = row.get("second_board_expectation") or "pending"
        grouped[key]["total"] += 1
        grouped[key]["hit_total"] += 1 if _is_validation_success(row) else 0
    return [{"name": key, **value} for key, value in sorted(grouped.items(), key=lambda pair: pair[1]["total"], reverse=True)]


def dashboard_strategy_names():
    return dashboard_strategy_summary()


def dashboard_daily_strategy_matrix(target_date):
    rows = [row for row in _rows() if str(row.get("pick_date") or "")[:10] == str(target_date)]
    grouped = defaultdict(lambda: {"total": 0, "worthy_total": 0, "deal_total": 0})
    for row in rows:
        key = row.get("strategy_name") or "2560"
        grouped[key]["total"] += 1
        grouped[key]["worthy_total"] += 1 if _is_worthy(row) else 0
        grouped[key]["deal_total"] += 1 if _is_deal(row) else 0
    return [{"strategy_name": key, **value} for key, value in sorted(grouped.items(), key=lambda pair: pair[1]["total"], reverse=True)]


def dashboard_daily_strategy_picks(target_date, strategy_name=""):
    rows = [row for row in _rows() if str(row.get("pick_date") or "")[:10] == str(target_date)]
    if strategy_name:
        rows = [row for row in rows if (row.get("strategy_name") or "2560") == strategy_name]
    rows.sort(key=lambda row: ((row.get("strategy_name") or "2560"), -_safe_int(row.get("id"))))
    return rows


def dashboard_research_stats():
    rows = _rows()
    scores = [_safe_float(row.get("second_board_score")) for row in rows]
    return {
        "total": len(rows),
        "watch_total": sum(1 for row in rows if _safe_int(row.get("watch_flag")) == 1),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "strong_total": sum(1 for score in scores if score >= 75),
    }


def dashboard_research_watchlist(limit=8):
    rows = [row for row in _rows() if _safe_int(row.get("watch_flag")) == 1]
    rows.sort(key=lambda row: (_safe_float(row.get("second_board_score")), str(row.get("pick_date") or "")), reverse=True)
    return rows[: int(limit)]
