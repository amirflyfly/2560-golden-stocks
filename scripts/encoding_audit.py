"""Scan text files for UTF-8 decode failures and common mojibake tokens."""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EXTENSIONS = {
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".playwright-cli",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "vendor",
    "venv",
}

MOJIBAKE_TOKENS = {
    "脙",
    "脗",
    "芒鈧",
    "盲赂",
    "氓鈥",
    "忙鈥",
    "莽拧",
    "闁插繐瀵",
    "娴溿倖妲",
    "闂傤厾骞",
    "缁涙牜鏆",
    "閿",
    "閵",
    "姣忔棩",
    "澶嶇洏",
    "璐︽埛",
}

REPLACEMENT_CHARACTER = "\ufffd"


@dataclass(frozen=True)
class EncodingFinding:
    path: str
    kind: str
    line: int | None
    column: int | None
    token: str | None
    message: str


def _normalize_extensions(extensions: Iterable[str]) -> set[str]:
    normalized = set()
    for extension in extensions:
        value = extension.strip().lower()
        if value:
            normalized.add(value if value.startswith(".") else f".{value}")
    return normalized


def _is_excluded(path: Path, root: Path, excluded_dirs: set[str]) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return any(part in excluded_dirs for part in relative.parts)


def _relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def iter_candidate_files(
    root: Path,
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
    include_patterns: Iterable[str] = (),
    exclude_patterns: Iterable[str] = (),
) -> Iterable[Path]:
    root = root.resolve()
    extension_set = _normalize_extensions(extensions)
    excluded_set = set(excluded_dirs)
    include_set = tuple(pattern for pattern in include_patterns if pattern)
    exclude_set = tuple(pattern for pattern in exclude_patterns if pattern)
    for path in root.rglob("*"):
        if _is_excluded(path, root, excluded_set):
            continue
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if not is_file:
            continue
        if path.name == ".env" or path.suffix.lower() in extension_set:
            try:
                relative = _relative_path(path, root)
            except ValueError:
                continue
            if include_set and not _matches_any(relative, include_set):
                continue
            if exclude_set and _matches_any(relative, exclude_set):
                continue
            yield path


def _line_column(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    previous_newline = text.rfind("\n", 0, index)
    column = index + 1 if previous_newline < 0 else index - previous_newline
    return line, column


def scan_file(path: Path, root: Path | None = None, tokens: Iterable[str] = MOJIBAKE_TOKENS) -> list[EncodingFinding]:
    root = (root or PROJECT_ROOT).resolve()
    relative_path = path.resolve().relative_to(root).as_posix()
    findings: list[EncodingFinding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        findings.append(
            EncodingFinding(
                path=relative_path,
                kind="utf8_decode_error",
                line=None,
                column=exc.start + 1,
                token=None,
                message=f"UTF-8 decode failed at byte {exc.start}: {exc.reason}",
            )
        )
        return findings

    if REPLACEMENT_CHARACTER in text:
        index = text.index(REPLACEMENT_CHARACTER)
        line, column = _line_column(text, index)
        findings.append(
            EncodingFinding(
                path=relative_path,
                kind="replacement_character",
                line=line,
                column=column,
                token=REPLACEMENT_CHARACTER,
                message="Suspicious Unicode replacement character found",
            )
        )

    token_candidates = [] if path.resolve() == Path(__file__).resolve() else sorted(set(tokens))
    for token in token_candidates:
        index = text.find(token)
        if index < 0:
            continue
        line, column = _line_column(text, index)
        findings.append(
            EncodingFinding(
                path=relative_path,
                kind="mojibake_token",
                line=line,
                column=column,
                token=token,
                message=f"Known mojibake token found: {token!r}",
            )
        )
    return findings


def audit_paths(
    root: Path = PROJECT_ROOT,
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
    include_patterns: Iterable[str] = (),
    exclude_patterns: Iterable[str] = (),
    group_by: str | None = None,
) -> dict:
    root = root.resolve()
    findings: list[EncodingFinding] = []
    checked = 0
    for path in iter_candidate_files(
        root,
        extensions=extensions,
        excluded_dirs=excluded_dirs,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    ):
        checked += 1
        findings.extend(scan_file(path, root=root))
    serialized_findings = [asdict(finding) for finding in findings]
    result = {
        "ok": not findings,
        "root": root.as_posix(),
        "checked_files": checked,
        "finding_count": len(findings),
        "findings": serialized_findings,
    }
    if group_by:
        result["group_by"] = group_by
        result["groups"] = group_findings(serialized_findings, group_by)
    return result


def group_findings(findings: Iterable[dict], group_by: str) -> list[dict]:
    if group_by not in {"path", "kind"}:
        raise ValueError("group_by must be 'path' or 'kind'")

    groups: dict[str, list[dict]] = {}
    for finding in findings:
        key = finding[group_by]
        groups.setdefault(key, []).append(finding)

    return [
        {
            "key": key,
            "finding_count": len(group_items),
            "findings": group_items,
        }
        for key, group_items in sorted(groups.items(), key=lambda item: item[0])
    ]


def _plan_action_for_kind(kind: str) -> str:
    if kind == "utf8_decode_error":
        return "Recover from source history or original bytes, then re-save as UTF-8."
    if kind == "replacement_character":
        return "Compare with source history and replace U+FFFD with the intended text."
    if kind == "mojibake_token":
        return "Decode the corrupted fragment from source history or rewrite the affected text."
    return "Review and repair the encoding issue manually."


def build_cleanup_plan(report: dict, group_by: str = "path") -> dict:
    findings = report["findings"]
    groups = group_findings(findings, group_by)
    return {
        "schema_version": 1,
        "mode": "read_only_cleanup_plan",
        "writes_project_files": False,
        "root": report["root"],
        "checked_files": report["checked_files"],
        "finding_count": report["finding_count"],
        "group_by": group_by,
        "groups": [
            {
                "key": group["key"],
                "finding_count": group["finding_count"],
                "items": [
                    {
                        "path": finding["path"],
                        "kind": finding["kind"],
                        "line": finding["line"],
                        "column": finding["column"],
                        "token": finding["token"],
                        "suggested_action": _plan_action_for_kind(finding["kind"]),
                    }
                    for finding in group["findings"]
                ],
            }
            for group in groups
        ],
    }


def write_cleanup_plan(path: Path, report: dict, group_by: str = "path") -> dict:
    plan = build_cleanup_plan(report, group_by=group_by)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


def validate_cleanup_plan(path: Path) -> dict:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "path": path.as_posix(), "errors": [f"invalid cleanup plan JSON: {exc}"], "items": []}
    errors: list[str] = []
    items: list[dict] = []
    if plan.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if plan.get("mode") != "read_only_cleanup_plan":
        errors.append("mode must be read_only_cleanup_plan")
    if plan.get("writes_project_files") is not False:
        errors.append("writes_project_files must be false")
    root = Path(plan.get("root") or PROJECT_ROOT).resolve()
    for group in plan.get("groups") or []:
        for item in group.get("items") or []:
            relative = str(item.get("path") or "")
            item_path = (root / relative).resolve()
            item_result = {
                "path": relative,
                "exists": item_path.exists(),
                "expected_kind": item.get("kind"),
                "still_present": False,
            }
            if not item_result["exists"]:
                item_result["error"] = "file no longer exists"
                errors.append(f"{relative}: file no longer exists")
            else:
                findings = scan_file(item_path, root=root)
                item_result["still_present"] = any(
                    finding.kind == item.get("kind")
                    and (item.get("token") in (None, finding.token) or finding.token == item.get("token"))
                    for finding in findings
                )
            items.append(item_result)
    return {
        "ok": not errors,
        "path": path.as_posix(),
        "root": root.as_posix(),
        "errors": errors,
        "item_count": len(items),
        "stale_count": sum(1 for item in items if item["exists"] and not item["still_present"]),
        "missing_count": sum(1 for item in items if not item["exists"]),
        "items": items,
    }


def _print_text_report(result: dict, limit: int) -> None:
    print(f"ok: {result['ok']}")
    print(f"checked files: {result['checked_files']}")
    print(f"findings: {result['finding_count']}")
    visible_limit = max(0, limit)

    if "groups" in result:
        printed = 0
        for group in result["groups"]:
            if printed >= visible_limit:
                break
            print(f"- {result['group_by']}={group['key']} findings={group['finding_count']}")
            for finding in group["findings"]:
                if printed >= visible_limit:
                    break
                _print_finding(finding, prefix="  - ")
                printed += 1
        remaining = result["finding_count"] - printed
    else:
        shown = result["findings"][:visible_limit]
        for finding in shown:
            _print_finding(finding)
        remaining = result["finding_count"] - len(shown)

    if remaining > 0:
        print(f"... {remaining} more findings hidden; rerun with --json for the full report")


def _print_plan_validation(result: dict, limit: int) -> None:
    print(f"ok: {result['ok']}")
    print(f"items: {result['item_count']}")
    print(f"stale: {result['stale_count']}")
    print(f"missing: {result['missing_count']}")
    for error in result["errors"][: max(0, limit)]:
        print(f"- {error}")


def _print_finding(finding: dict, prefix: str = "- ") -> None:
    location = finding["path"]
    if finding["line"] is not None:
        location = f"{location}:{finding['line']}:{finding['column']}"
    print(f"{prefix}{location} [{finding['kind']}] {finding['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit text files for UTF-8 and mojibake issues.")
    parser.add_argument("root", nargs="?", default=str(PROJECT_ROOT), help="directory to scan")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--limit", type=int, default=100, help="maximum findings to print in text mode")
    parser.add_argument("--extension", action="append", dest="extensions", help="file extension to include")
    parser.add_argument("--exclude-dir", action="append", dest="excluded_dirs", default=[], help="additional directory name to exclude")
    parser.add_argument("--group-by", choices=("path", "kind"), help="include a grouped read-only report")
    parser.add_argument("--include", action="append", dest="include_patterns", default=[], help="glob pattern for relative paths to include")
    parser.add_argument("--exclude", action="append", dest="exclude_patterns", default=[], help="glob pattern for relative paths to exclude")
    parser.add_argument("--write-plan", help="write a JSON cleanup plan without changing scanned files")
    parser.add_argument("--validate-plan", help="validate a cleanup plan without changing scanned files")
    args = parser.parse_args()

    if args.validate_plan:
        result = validate_cleanup_plan(Path(args.validate_plan))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_plan_validation(result, args.limit)
        return 0 if result["ok"] else 1

    result = audit_paths(
        Path(args.root),
        extensions=args.extensions or DEFAULT_EXTENSIONS,
        excluded_dirs={*DEFAULT_EXCLUDED_DIRS, *args.excluded_dirs},
        include_patterns=args.include_patterns,
        exclude_patterns=args.exclude_patterns,
        group_by=args.group_by,
    )
    if args.write_plan:
        plan_group_by = args.group_by or "path"
        write_cleanup_plan(Path(args.write_plan), result, group_by=plan_group_by)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text_report(result, args.limit)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
