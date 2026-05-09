"""Remove generated project files from the Git index without deleting them.

Dry-run is the default. Pass --apply to run git rm --cached for the reported
paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable

try:
    from scripts.check_repo_hygiene import (
        PROJECT_ROOT,
        _normalize,
        _run_git,
        find_git_root,
        is_forbidden_path,
        project_git_pathspec,
    )
except ModuleNotFoundError:
    from check_repo_hygiene import (  # type: ignore[no-redef]
        PROJECT_ROOT,
        _normalize,
        _run_git,
        find_git_root,
        is_forbidden_path,
        project_git_pathspec,
    )


def build_cleanup_plan(project_root: Path | None = None, paths: Iterable[str] | None = None) -> dict:
    root = project_root or PROJECT_ROOT
    git_root = find_git_root(root)
    if paths is None:
        pathspec = project_git_pathspec(root, git_root)
        tracked = _run_git(["ls-files", "--", pathspec], git_root)
        staged = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", pathspec], git_root)
        paths = [*tracked, *staged]

    candidates = []
    for git_path in sorted(set(paths)):
        project_path = _normalize(git_path, root)
        if is_forbidden_path(project_path):
            candidates.append({"git_path": git_path.replace("\\", "/"), "project_path": project_path})

    return {
        "git_root": str(git_root),
        "project_root": str(root),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def apply_cleanup(plan: dict, batch_size: int = 500) -> int:
    paths = [candidate["git_path"] for candidate in plan["candidates"]]
    if not paths:
        return 0

    git_root = Path(plan["git_root"])
    removed = 0
    for start in range(0, len(paths), batch_size):
        batch = paths[start : start + batch_size]
        payload = ("\0".join(batch) + "\0").encode("utf-8")
        completed = subprocess.run(
            [
                "git",
                "rm",
                "--cached",
                "-f",
                "-r",
                "--ignore-unmatch",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
            ],
            cwd=str(git_root),
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or "git rm --cached failed")
        removed += len(batch)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Untrack generated files while keeping local files.")
    parser.add_argument("--apply", action="store_true", help="apply git rm --cached; default is dry-run")
    parser.add_argument("--json", action="store_true", help="print the full JSON plan")
    parser.add_argument("--limit", type=int, default=100, help="maximum candidates to print in text mode")
    args = parser.parse_args()

    plan = build_cleanup_plan()
    if args.json:
        print(json.dumps({**plan, "mode": "apply" if args.apply else "dry-run"}, ensure_ascii=False, indent=2))
    else:
        print(f"mode: {'apply' if args.apply else 'dry-run'}")
        print(f"git root: {plan['git_root']}")
        print(f"project root: {plan['project_root']}")
        print(f"candidates: {plan['candidate_count']}")
        for candidate in plan["candidates"][: max(0, args.limit)]:
            print(f"- {candidate['project_path']}")
        remaining = plan["candidate_count"] - min(plan["candidate_count"], max(0, args.limit))
        if remaining > 0:
            print(f"... {remaining} more candidates hidden; rerun with --json for the full report")

    if args.apply:
        removed = apply_cleanup(plan)
        print(f"removed from index: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
