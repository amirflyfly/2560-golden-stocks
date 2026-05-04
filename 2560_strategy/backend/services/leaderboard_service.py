"""Leaderboards logic."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from backend.repositories import picks_repo


_WORTHY_STATUSES = {"worthy", "worth_review", "鍊煎緱澶嶈", "值得复盘"}
_DEAL_STATUSES = {"done", "deal", "dealt", "completed", "宸叉垚浜?", "已成交"}
_SPREAD_STATUSES = {"yes", "true", "1", "鏄?", "是"}


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


def _filtered_rows(range_key):
    rows = picks_repo.list_picks(limit=100000)
    if range_key == "all":
        return rows
    days = {"7d": 6, "30d": 29, "90d": 89}.get(range_key, 29)
    cutoff = date.today() - timedelta(days=days)
    return [row for row in rows if (_parse_date(row.get("pick_date")) or date.min) >= cutoff]


def _top(counter):
    return [{"name": name, "cnt": cnt} for name, cnt in counter.most_common(10)]


def leaderboards(range_key="30d", metric="default"):
    rows = _filtered_rows(range_key)
    channel_counter = Counter((row.get("source_channel") or "system") for row in rows)
    worthy_counter = Counter((row.get("reason_tag") or "untagged") for row in rows if (row.get("review_status") or "").strip() in _WORTHY_STATUSES)
    deal_counter = Counter((row.get("source_channel") or "system") for row in rows if (row.get("deal_status") or "").strip() in _DEAL_STATUSES)
    spread_counter = Counter((row.get("source_channel") or "system") for row in rows if (row.get("secondary_spread") or "").strip() in _SPREAD_STATUSES)

    inquiry = defaultdict(lambda: {"sum": 0.0, "count": 0})
    for row in rows:
        key = row.get("reason_tag") or "untagged"
        inquiry[key]["sum"] += _safe_float(row.get("inquiry_count"))
        inquiry[key]["count"] += 1
    inquiry_rank = sorted(
        (
            {"name": name, "cnt": round(item["sum"] / item["count"], 1) if item["count"] else 0}
            for name, item in inquiry.items()
        ),
        key=lambda item: item["cnt"],
        reverse=True,
    )[:10]

    spread_rank = _top(spread_counter)
    right_rows = spread_rank if metric == "spread" else inquiry_rank

    return {
        "range_key": range_key,
        "metric": metric,
        "channel_rank": _top(channel_counter),
        "worthy_rank": _top(worthy_counter),
        "deal_rank": _top(deal_counter),
        "inquiry_rank": inquiry_rank,
        "spread_rank": spread_rank,
        "right_title": "Secondary Spread Channel Top10" if metric == "spread" else "Average Inquiry Tag Top10",
        "right_rows": right_rows,
        "right_color": "#7c3aed" if metric == "spread" else "#ca8a04",
    }
