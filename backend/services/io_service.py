"""Import/export helpers."""

import csv
import io

from backend.repositories import picks_repo
from backend.services.format_service import int_num, num


EXPORT_COLUMNS = [
    "id",
    "pick_date",
    "code",
    "name",
    "pick_price",
    "signal",
    "source",
    "source_channel",
    "reason_tag",
    "review_status",
    "result_grade",
    "inquiry_count",
    "deal_status",
    "secondary_spread",
    "content_title",
    "content_ref",
    "note",
    "archived",
    "created_at",
]


def bulk_import_from_csv(csv_text):
    csv_text = (csv_text or "").strip()
    if not csv_text:
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    imported_ids = []
    for row in reader:
        if not any((value or "").strip() for value in row.values()):
            continue
        pick_date = (row.get("pick_date") or "").strip()
        code = (row.get("code") or "").strip()
        source = "csv-import"
        if not pick_date or not code:
            continue
        picks_repo.create_or_replace_pick(
            pick_date,
            code,
            (row.get("name") or "").strip(),
            num(row.get("pick_price")),
            (row.get("signal") or "").strip(),
            source,
            (row.get("source_channel") or "csv").strip(),
            (row.get("reason_tag") or "").strip(),
            (row.get("note") or "").strip(),
            (row.get("review_status") or "pending").strip(),
            (row.get("review_comment") or row.get("note") or "").strip(),
            (row.get("content_title") or "").strip(),
            (row.get("content_ref") or "").strip(),
            (row.get("result_grade") or "pending").strip(),
            int_num(row.get("inquiry_count")),
            (row.get("deal_status") or "not_dealt").strip(),
            (row.get("secondary_spread") or "no").strip(),
        )
        new_row = picks_repo.get_pick_by_unique(pick_date, code, source)
        if new_row:
            imported_ids.append(new_row["id"])
    return imported_ids


def rows_to_csv(rows, fieldnames=None):
    fieldnames = fieldnames or EXPORT_COLUMNS
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output.getvalue()
