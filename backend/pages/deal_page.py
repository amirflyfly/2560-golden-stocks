"""Page: deal review."""

from backend.repositories import picks_repo
from backend.ui.html_helpers import esc, layout_page, render_nav


_NOT_DEAL_STATUSES = {"", "not_dealt", "not_done", "pending", "未成交", "鏈垚浜?"}
_NO_SPREAD_STATUSES = {"", "no", "false", "0", "否", "鍚?"}


def _is_deal_row(row):
    return (row.get("deal_status") or "").strip() not in _NOT_DEAL_STATUSES


def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def render_deal_review_page():
    deals = [row for row in picks_repo.list_picks(limit=10000) if _is_deal_row(row)]
    rows = "".join(
        [
            f"<tr><td>{esc(r.get('pick_date'))}</td><td>{esc(r.get('name'))}</td><td>{esc(r.get('code'))}</td>"
            f"<td>{esc(r.get('source_channel'))}</td><td>{esc(r.get('reason_tag'))}</td>"
            f"<td>{esc(r.get('review_status'))}</td><td>{esc(r.get('result_grade'))}</td>"
            f"<td>{esc(r.get('inquiry_count'))}</td><td>{esc(r.get('secondary_spread'))}</td>"
            f"<td>{esc(r.get('content_title'))}</td></tr>"
            for r in deals
        ]
    ) or '<tr><td colspan="10">No deal records</td></tr>'

    total = len(deals)
    avg_inquiry = round(sum(_safe_float(row.get("inquiry_count")) for row in deals) / total, 1) if total else 0
    spread_total = sum(1 for row in deals if (row.get("secondary_spread") or "").strip().lower() not in _NO_SPREAD_STATUSES)

    body = f"""
<div class="topline"><div><h1>Deal Review</h1><div class="muted">Review completed deals and compare channel, tag and content signals.</div></div><div><a class="btn" href="/">Back</a></div></div>
<div class='nav'>{render_nav('deal')}</div>
<div class="grid section">
  <div class="card"><div class="muted">Deals</div><div class="num">{total}</div></div>
  <div class="card"><div class="muted">Avg inquiries</div><div class="num">{avg_inquiry}</div></div>
  <div class="card"><div class="muted">Secondary spread</div><div class="num">{spread_total}</div></div>
</div>
<div class="section card"><div class="tablewrap"><table>
  <thead><tr><th>Date</th><th>Stock</th><th>Code</th><th>Channel</th><th>Tag</th><th>Review</th><th>Grade</th><th>Inquiries</th><th>Spread</th><th>Title</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div></div>
"""

    return layout_page("Deal Review", body)
