"""Read-only repository hygiene checks.

The script reports generated files that should not be tracked or staged. It does
not delete, move, or unstage anything.
"""

from __future__ import annotations

import json
import argparse
import subprocess
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROJECT_PREFIXES = {"2560_strategy"}

FORBIDDEN_PARTS = {
    "__pycache__",
    "node_modules",
    "venv",
    ".pytest_cache",
    ".playwright-cli",
    "playwright-report",
    "test-results",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".temp",
    ".pid",
}

FORBIDDEN_EXACT = {
    ".env",
    "err.log",
    "out.log",
    "data/picks.db",
    "dist/index.html",
    "frontend/dist/index.html",
    "static/dist/index.html",
}

FORBIDDEN_PREFIXES = {
    "data/cache/",
    "dist/assets/",
    "frontend/dist/assets/",
    "static/dist/",
}


def _run_git(args: list[str], cwd: Path) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def find_git_root(project_root: Path | None = None) -> Path:
    root = project_root or PROJECT_ROOT
    lines = _run_git(["rev-parse", "--show-toplevel"], root)
    if not lines:
        return root.parent
    return Path(lines[0]).resolve()


def project_git_pathspec(project_root: Path | None = None, git_root: Path | None = None) -> str:
    root = (project_root or PROJECT_ROOT).resolve()
    repo_root = (git_root or find_git_root(root)).resolve()
    try:
        return root.relative_to(repo_root).as_posix()
    except ValueError:
        return root.as_posix()


def _strip_current_dir_prefix(path: str) -> str:
    value = path
    while value.startswith("./"):
        value = value[2:]
    return value


def _normalize(path: str, root: Path) -> str:
    raw = Path(path)
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(root).as_posix()
        except ValueError:
            pass

    value = path.replace("\\", "/")
    root_name = root.name.rstrip("/")
    prefixes = {root_name, *LEGACY_PROJECT_PREFIXES}
    for prefix_name in prefixes:
        prefix = f"{prefix_name}/"
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return _strip_current_dir_prefix(value)


def is_forbidden_path(path: str) -> bool:
    normalized = _strip_current_dir_prefix(path.replace("\\", "/"))
    parts = set(normalized.split("/"))
    if parts & FORBIDDEN_PARTS:
        return True
    if normalized in FORBIDDEN_EXACT:
        return True
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return True
    return any(normalized.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)


def find_hygiene_violations(project_root: Path | None = None, paths: Iterable[str] | None = None) -> dict:
    root = project_root or PROJECT_ROOT
    if paths is None:
        git_root = find_git_root(root)
        pathspec = project_git_pathspec(root, git_root)
        tracked = _run_git(["ls-files", "--", pathspec], git_root)
        staged = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", pathspec], git_root)
        paths = [*tracked, *staged]

    normalized_paths = sorted({_normalize(path, root) for path in paths})
    violations = [path for path in normalized_paths if is_forbidden_path(path)]
    return {
        "ok": not violations,
        "total_paths": len(normalized_paths),
        "violations": violations,
        "violation_count": len(violations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check tracked/staged generated files.")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--limit", type=int, default=100, help="maximum violations to print in text mode")
    args = parser.parse_args()
    result = find_hygiene_violations()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ok: {result['ok']}")
        print(f"checked paths: {result['total_paths']}")
        print(f"violations: {result['violation_count']}")
        for path in result["violations"][: max(0, args.limit)]:
            print(f"- {path}")
        remaining = result["violation_count"] - min(result["violation_count"], max(0, args.limit))
        if remaining > 0:
            print(f"... {remaining} more violations hidden; rerun with --json for the full report")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
