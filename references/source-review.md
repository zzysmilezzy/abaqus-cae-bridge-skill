# Source review and compatibility

Source: https://github.com/jasonanewcoder/abaqus_skills

Pinned commit: `4737c0ab8d0548e0aa26345c5f7d5ac1a2e5dbc9`, reviewed 2026-10-20.

The 42 Markdown reference files under `upstream/` are unchanged snapshots of `abaqus_scriptcontrol_skills/*/reference/*.md` and `abaqus_subroutine_skills/reference/**/*.md`. Upstream `docs/ERRATA.md` is included. Their MIT license/copyright notice is retained in `upstream/LICENSE`. No upstream installer, AGENTS/CLAUDE policy or automatic job submission is adopted.

## Adopted ideas

Separate modeling, isolated execution, diagnosis, extraction and verification; progressively load domain references; reuse offline input checks, unit conversion and ODB extraction. Retain the local main-thread GUI bridge and Windows execution model.

## Corrected rather than directly installed

| Source | Observed issue at pinned revision | Local treatment |
|---|---|---|
| `scripts/unit_converter.py` | Four-entry tuple indexes use `q[2]` (unit string), not factor `q[3]`; SI metre-to-mm multiplier reversed; W/m3-to-mW/mm3 factor 1000 times too large | Independent converter with dimensional regression cases: 1m=1000mm; 1W/m3=1e-6mW/mm3 |
| `scripts/odb_extract.py` | History tuples accessed through `.value/.frameValue`; scalar data assumed iterable; default vector metric is maximum component; tensor invariant unspecified | Python 2.7/3 scalar/vector/tensor semantics, history pairs, explicit Mises from S |
| Same extractor | Node/element metadata assumed available; first matching instance set chosen; helper failure status ignored; initial frames not distinguished | Safe metadata, set disambiguation, nonzero errors, initial-only rejection |
| `scripts/inp_checker.py` | Legal multiple per-part Node/Element blocks flagged; case-sensitive material names; includes unresolved | Scoped labels, case-insensitive names, recursive includes and structural checks; heuristic limits retained |
| `scripts/job_monitor.sh` | Bash dependency and lock-file timing can miss a startup; one log success string | Read-only Windows-compatible Python monitor with file evidence and no liveness claim |
| Playbook / README | Fixed N-mm defaults, universal formats/thresholds and blanket release/Python assumptions | Preserve user physics/units; verify actual release; interpret energy ratios by procedure |

The local bridge submit helper now enables consistency checking and returns without waiting. Submission is explicitly distinguished from completed analysis.

Local runtime check: the Abaqus 2021 batch launcher returned exit code 0 even when the Python script called `sys.exit(1)`. The extractor therefore also emits JSON `ok: false` on failure and `ok: true` on extraction success. Callers must check this envelope; `ok` does not certify solver completion. Empty steps/initial-only frames remain rejected by default.

## Validation boundary

Reference snippets are not all ported/runtime-tested. Check f-strings, `encoding=` on Python 2, release-dependent CAE APIs and Fortran interfaces before using them. Do not copy compiler support or `official` example claims as certification. No claim is made that this update repairs a specific nonconvergent model. Offline fixture tests and read-only ODB checks validate software behavior; they are not a resumed cancelled analysis.
