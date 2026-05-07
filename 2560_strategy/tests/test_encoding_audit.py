from __future__ import annotations

import json
from pathlib import Path


def test_encoding_audit_detects_mojibake_token(tmp_path):
    from scripts.encoding_audit import audit_paths

    target = tmp_path / "bad.md"
    target.write_text("姣忔棩浜ゆ槗澶嶇洏", encoding="utf-8")

    result = audit_paths(tmp_path, extensions={".md"}, excluded_dirs=set())

    assert result["ok"] is False
    assert result["finding_count"] >= 1
    assert result["findings"][0]["kind"] == "mojibake_token"


def test_encoding_audit_key_user_visible_files_are_clean():
    from scripts.encoding_audit import scan_file

    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "backend" / "application" / "report_api_service.py",
        root / "frontend" / "e2e" / "reports.spec.js",
        root / "docs" / "quant_workflow_closure_review.md",
    ]

    findings = []
    for target in targets:
        findings.extend(scan_file(target, root=root))

    assert findings == []


def test_encoding_audit_groups_filters_and_writes_read_only_plan(tmp_path):
    from scripts.encoding_audit import audit_paths, validate_cleanup_plan, write_cleanup_plan

    docs = tmp_path / "docs"
    docs.mkdir()
    broken_text = docs / "broken.txt"
    broken_text.write_text("title: bad\ufffdtext\n", encoding="utf-8")
    broken_bytes = docs / "latin1.txt"
    broken_bytes.write_bytes(b"caf\xe9")
    skipped = docs / "skip.txt"
    skipped.write_text("skip\ufffdme\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\ufffdscope\n", encoding="utf-8")

    result = audit_paths(
        tmp_path,
        extensions={".txt"},
        excluded_dirs=set(),
        include_patterns=["docs/*"],
        exclude_patterns=["docs/skip.txt"],
        group_by="kind",
    )

    assert result["ok"] is False
    assert result["checked_files"] == 2
    assert result["finding_count"] == 2
    assert {group["key"] for group in result["groups"]} == {"replacement_character", "utf8_decode_error"}
    assert {finding["path"] for finding in result["findings"]} == {"docs/broken.txt", "docs/latin1.txt"}

    plan_path = tmp_path / "plans" / "encoding-cleanup.json"
    plan = write_cleanup_plan(plan_path, result, group_by="path")
    saved_plan = json.loads(plan_path.read_text(encoding="utf-8"))

    assert saved_plan == plan
    assert plan["mode"] == "read_only_cleanup_plan"
    assert plan["writes_project_files"] is False
    assert {group["key"] for group in plan["groups"]} == {"docs/broken.txt", "docs/latin1.txt"}
    assert all(group["items"][0]["suggested_action"] for group in plan["groups"])
    assert broken_text.read_text(encoding="utf-8") == "title: bad\ufffdtext\n"
    assert broken_bytes.read_bytes() == b"caf\xe9"

    validation = validate_cleanup_plan(plan_path)
    assert validation["ok"] is True
    assert validation["item_count"] == 2
    assert validation["stale_count"] == 0

    broken_text.write_text("title: fixed text\n", encoding="utf-8")
    validation_after_fix = validate_cleanup_plan(plan_path)
    assert validation_after_fix["ok"] is True
    assert validation_after_fix["stale_count"] == 1


def test_encoding_audit_skips_excluded_dirs_before_stat(tmp_path, monkeypatch):
    from scripts.encoding_audit import iter_candidate_files

    source = tmp_path / "frontend" / "src" / "app.js"
    source.parent.mkdir(parents=True)
    source.write_text("console.log('ok')\n", encoding="utf-8")
    blocked = tmp_path / "frontend" / "node_modules" / ".bin" / "broken.js"
    blocked.parent.mkdir(parents=True)
    blocked.write_text("console.log('skip')\n", encoding="utf-8")

    original_is_file = Path.is_file

    def guarded_is_file(path):
        if "node_modules" in path.parts:
            raise OSError("inaccessible dependency link")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", guarded_is_file)

    files = list(
        iter_candidate_files(
            tmp_path,
            extensions={".js"},
            excluded_dirs={"node_modules"},
        )
    )

    assert files == [source]


def test_encoding_audit_validate_plan_reports_missing_file(tmp_path):
    from scripts.encoding_audit import audit_paths, validate_cleanup_plan, write_cleanup_plan

    target = tmp_path / "bad.txt"
    target.write_text("bad\ufffdtext\n", encoding="utf-8")
    report = audit_paths(tmp_path, extensions={".txt"}, excluded_dirs=set())
    plan_path = tmp_path / "plan.json"
    write_cleanup_plan(plan_path, report)
    target.unlink()

    validation = validate_cleanup_plan(plan_path)

    assert validation["ok"] is False
    assert validation["missing_count"] == 1
    assert "file no longer exists" in validation["errors"][0]
