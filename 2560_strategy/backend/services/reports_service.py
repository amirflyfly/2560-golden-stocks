"""Reports logic."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from backend.repositories import picks_repo


_WORTHY_STATUSES = {"worthy", "worth_review", "鍊煎緱澶嶈", "值得复盘"}
_DEAL_STATUSES = {"done", "deal", "dealt", "completed", "宸叉垚浜?", "已成交"}


def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _is_worthy(row):
    return (row.get("review_status") or "").strip() in _WORTHY_STATUSES


def _is_deal(row):
    return (row.get("deal_status") or "").strip() in _DEAL_STATUSES


def _all_rows():
    return picks_repo.list_picks(limit=100000)


def monthly_report_rows():
    grouped = defaultdict(lambda: {"total": 0, "worthy_total": 0, "deal_total": 0, "inquiry_sum": 0.0})
    for row in _all_rows():
        pick_date = str(row.get("pick_date") or "")
        if len(pick_date) < 7:
            continue
        month = pick_date[:7]
        item = grouped[month]
        item["total"] += 1
        item["worthy_total"] += 1 if _is_worthy(row) else 0
        item["deal_total"] += 1 if _is_deal(row) else 0
        item["inquiry_sum"] += _safe_float(row.get("inquiry_count"))

    result = []
    for month, item in grouped.items():
        total = item["total"]
        result.append(
            {
                "month": month,
                "total": total,
                "worthy_total": item["worthy_total"],
                "deal_total": item["deal_total"],
                "avg_inquiry": round(item["inquiry_sum"] / total, 1) if total else 0,
            }
        )
    return sorted(result, key=lambda item: item["month"], reverse=True)


def weekly_report_rows():
    grouped = defaultdict(lambda: {"total": 0, "worthy_total": 0, "deal_total": 0})
    for row in _all_rows():
        parsed = _parse_date(row.get("pick_date"))
        if parsed is None:
            continue
        iso = parsed.isocalendar()
        period = f"{iso.year}-W{iso.week:02d}"
        item = grouped[period]
        item["total"] += 1
        item["worthy_total"] += 1 if _is_worthy(row) else 0
        item["deal_total"] += 1 if _is_deal(row) else 0

    result = [
        {
            "period": period,
            "total": item["total"],
            "worthy_total": item["worthy_total"],
            "deal_total": item["deal_total"],
        }
        for period, item in grouped.items()
    ]
    return sorted(result, key=lambda item: item["period"], reverse=True)[:12]


def report_summary_text():
    monthly = monthly_report_rows()
    weekly = weekly_report_rows()
    if not monthly:
        return {
            "weekly": "No weekly data is available yet.",
            "monthly": "No monthly data is available yet.",
            "boss": "No reportable data is available yet.",
        }

    latest = monthly[0]
    month = latest.get("month") or "-"
    total = int(latest.get("total") or 0)
    worthy = int(latest.get("worthy_total") or 0)
    deal = int(latest.get("deal_total") or 0)
    avg_inquiry = latest.get("avg_inquiry") or 0
    worthy_rate = round((worthy / total * 100), 1) if total else 0

    monthly_summary = (
        f"{month}: {total} picks, {worthy} worthy reviews ({worthy_rate}%), "
        f"{deal} deals, avg inquiries {avg_inquiry}."
    )

    if weekly:
        current_week = weekly[0]
        weekly_summary = (
            f"{current_week.get('period')}: {int(current_week.get('total') or 0)} picks, "
            f"{int(current_week.get('worthy_total') or 0)} worthy reviews, "
            f"{int(current_week.get('deal_total') or 0)} deals."
        )
    else:
        weekly_summary = "No weekly data is available yet."

    boss_summary = (
        f"This month has {total} picks, {worthy} worthy reviews, {deal} deals, "
        f"and avg inquiries {avg_inquiry}."
    )
    return {"weekly": weekly_summary, "monthly": monthly_summary, "boss": boss_summary}
