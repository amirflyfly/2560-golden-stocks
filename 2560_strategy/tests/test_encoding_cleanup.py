from __future__ import annotations

from pathlib import Path

from scripts.encoding_audit import audit_paths, scan_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SURFACES = [
    PROJECT_ROOT / "backend" / "services" / "dashboard_service.py",
    PROJECT_ROOT / "backend" / "strategies" / "strategy_2560.py",
    PROJECT_ROOT / "backend" / "application" / "report_api_service.py",
    PROJECT_ROOT / "docs" / "quant_workflow_closure_review.md",
]

MOJIBAKE_MARKERS = [
    "\ufffd",
    "\ue189",
    "\u93c3",
    "\u93c0",
    "\u93c8",
    "\u93b4",
    "\u95b2",
    "\u68e3\u6828",
    "\u6f98\u5a11",
]


def test_user_facing_text_surfaces_do_not_contain_known_mojibake_markers():
    failures = []
    for path in TEXT_SURFACES:
        text = path.read_text(encoding="utf-8")
        found = [marker.encode("unicode_escape").decode("ascii") for marker in MOJIBAKE_MARKERS if marker in text]
        if found:
            failures.append(f"{path.relative_to(PROJECT_ROOT)}: {', '.join(found)}")

    assert failures == []


def test_encoding_audit_detects_artificial_mojibake_file(tmp_path):
    broken = tmp_path / "broken.md"
    broken.write_text("title: 姣忔棩浜ゆ槗澶嶇洏\n", encoding="utf-8")

    findings = scan_file(broken, root=tmp_path)

    assert findings
    assert all(finding.kind == "mojibake_token" for finding in findings)
    assert {"姣忔棩", "澶嶇洏"}.issubset({finding.token for finding in findings})


def test_encoding_audit_detects_utf8_decode_errors(tmp_path):
    broken = tmp_path / "latin1.txt"
    broken.write_bytes(b"caf\xe9")

    findings = scan_file(broken, root=tmp_path)

    assert len(findings) == 1
    assert findings[0].kind == "utf8_decode_error"
    assert findings[0].path == "latin1.txt"


def test_encoding_audit_excludes_generated_and_vendor_directories(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("print('ok')\n", encoding="utf-8")
    excluded = tmp_path / "node_modules" / "package" / "bad.js"
    excluded.parent.mkdir(parents=True)
    excluded.write_text("const label = '姣忔棩浜ゆ槗澶嶇洏';\n", encoding="utf-8")

    result = audit_paths(tmp_path)

    assert result["ok"] is True
    assert result["checked_files"] == 1
    assert result["findings"] == []
