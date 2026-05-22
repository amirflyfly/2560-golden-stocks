# AiStocks v1.1 Production Evidence Local Precheck — 2026-05-22

## Scope

This is a local, read-only/safe precheck against the current `D:/AiStocks` checkout, based on `docs/software-company/aistocks-v11-production-evidence-execution-plan-2026-05-21.md`. It does not connect to a real production or staging environment, does not trigger external push delivery, and does not create real production evidence.

- Project root: `D:/AiStocks` (`/d/AiStocks` in Git Bash)
- Local timestamp: `2026-05-22T10:37:05+08:00`
- Git short hash observed: `465525e`
- Target environment info: not provided in this task
- Final production GO/NO-GO: **NOT SET / DO NOT MARK GO**

## Script Inventory

The following scripts exist in `D:/AiStocks/scripts`:

- `scripts/production_evidence.py`
- `scripts/deploy_preflight.py`
- `scripts/check_repo_hygiene.py`

## Commands Executed

| # | Command | Exit code | stdout summary | stderr summary | Notes |
| --- | --- | ---: | --- | --- | --- |
| 1 | `find "D:/AiStocks/scripts" -maxdepth 1 -type f \( -name "production_evidence.py" -o -name "deploy_preflight.py" -o -name "check_repo_hygiene.py" \) -print` | 0 | Listed all three target scripts. | Empty. | Inventory only. |
| 2 | `find "D:/AiStocks" -maxdepth 2 -type f \( -name "package.json" -o -name "pyproject.toml" -o -name "requirements*.txt" -o -name "pytest.ini" -o -name "Makefile" \) -print` | 0 | Found `frontend/package.json`, root `package.json`, `pytest.ini`, `requirements.txt`. | Empty. | Inventory only. |
| 3 | `"D:/AiStocks/venv/Scripts/python.exe" "D:/AiStocks/scripts/production_evidence.py" --help` | 127 | Empty. | `/usr/bin/bash: D:/AiStocks/venv/Scripts/python.exe: No such file or directory` | Project venv path referenced by npm scripts is absent in this shell. |
| 4 | `"D:/AiStocks/venv/Scripts/python.exe" "D:/AiStocks/scripts/check_repo_hygiene.py" --help` | 127 | Empty. | `/usr/bin/bash: D:/AiStocks/venv/Scripts/python.exe: No such file or directory` | Same missing venv issue. |
| 5 | `"D:/AiStocks/venv/Scripts/python.exe" --version` | 127 | Empty. | `/usr/bin/bash: D:/AiStocks/venv/Scripts/python.exe: No such file or directory` | Confirms missing venv executable. |
| 6 | `python --version` | 0 | `Python 3.12.10` | Empty. | System Python available. |
| 7 | `py --version` | 0 | `Python 3.12.10` | Empty. | Windows launcher available. |
| 8 | `python "/d/AiStocks/scripts/production_evidence.py" --help` | 0 | Help output lists `--evidence`, `--min-soak-minutes`, `--write-template`, `--write-readiness-sample`, `--write-runtime-bundle`. | Empty. | Safe help command. |
| 9 | `python "/d/AiStocks/scripts/check_repo_hygiene.py" --help` | 0 | Help output lists `--json` and `--limit`. | Empty. | Safe help command. |
| 10 | `python "/d/AiStocks/scripts/deploy_preflight.py"` | 0 | JSON result: `ok: true`, `total: 61`, `failed: 0`, `summary: preflight passed`. | Empty. | Local read-only deployment baseline check passed. |
| 11 | `python "/d/AiStocks/scripts/check_repo_hygiene.py" --json` | 0 | JSON result: `ok: true`, `total_paths: 405`, `violation_count: 0`, `violations: []`. | Empty. | Local repo hygiene check passed. |
| 12 | `python "/d/AiStocks/scripts/production_evidence.py" --evidence "/d/AiStocks/docs/product/PRODUCTION_EVIDENCE.example.json"` | 1 | JSON result: `ok: false`, `core_evidence_ok: false`, `total: 36`, `failed: 23`, `summary: production evidence failed: 23 checks`. | Empty. | Expected: example/template evidence is incomplete and must not be treated as real production evidence. |
| 13 | `git -C "/d/AiStocks" rev-parse --short HEAD && git -C "/d/AiStocks" status --short` | 0 | Head `465525e`; working tree has many modified/untracked files. | Empty. | Status recorded for traceability; not a pass/fail production gate. |
| 14 | `date -Iseconds` | 0 | `2026-05-22T10:37:05+08:00` | Empty. | Timestamp only. |

## Key Results

- Local deploy preflight passed: `ok=true`, `61/61` checks passed.
- Local repo hygiene passed: `ok=true`, `405` tracked/staged paths checked, `0` hygiene violations.
- `production_evidence.py` is present and its CLI works with system Python.
- Validating `docs/product/PRODUCTION_EVIDENCE.example.json` correctly failed because it is only an example/incomplete bundle, not collected production evidence.
- The project npm scripts reference `venv\Scripts\python.exe`, but `D:/AiStocks/venv/Scripts/python.exe` was not present in this Git Bash environment. System Python 3.12.10 was used for safe local checks instead.

## Blockers / Owners

| Blocker | Owner | Detail |
| --- | --- | --- |
| Real production/staging target missing | Environment owner | No target base URL, credentials, tenant/test account, log system link, DB read-only access, or push channel test endpoint was provided. Real API/page/log/DB/push evidence remains pending. |
| Project virtualenv missing at scripted path | Engineer owner | Root `package.json` scripts use `venv\Scripts\python.exe`; that executable was absent. Recreate/restore venv or adjust execution instructions before relying on npm script wrappers. |
| Production evidence bundle incomplete | Config/Release owner | The checked example file intentionally lacks backup sha256/size, restore verification, migration validation, release/security/regression approvals, and multiple soak samples. |
| Dirty working tree | Engineer/Release owner | `git status --short` shows many modified and untracked files. This does not invalidate local precheck commands, but release evidence should be tied to a clean, reviewed release commit/artifact. |

## Production Evidence Status

**Real production evidence is still pending.** This document only records local precheck/readiness command execution. It does not prove production health, login, market sync, scan, paper trading `apply-signal`, `evaluate-exits`, daily report push, external delivery query, logs, screenshots, or database records.

Final judgment for the production evidence execution plan: **NO GO / NOT EVALUATED FOR GO** until target environment evidence is collected and validated.
