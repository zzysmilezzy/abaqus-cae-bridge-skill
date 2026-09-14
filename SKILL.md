---
name: abaqus-cae-bridge
description: Connect to an already-open Abaqus/CAE GUI session so Codex can run Abaqus Python commands in that visible session, update the viewport, inspect or modify models, submit jobs, and diagnose Abaqus analysis failures from .log/.msg/.dat/.sta files. Use when the user asks to connect to Abaqus, control Abaqus while they watch the screen, operate an open CAE model, copy/modify Abaqus models, submit jobs, or debug failed Abaqus runs.
metadata:
  short-description: Control visible Abaqus/CAE sessions
---

# Abaqus/CAE Bridge

Use this skill when the user wants Codex to operate a currently open Abaqus/CAE GUI session and see the viewport change.

## Core Rule

Use the main-thread file bridge in `scripts/abaqus_cae_bridge.py`. Do not use a socket server or a background thread for CAE object access; Abaqus/CAE 2021 can hang or throw connection-reset errors when `mdb` or `session` objects are touched from a background thread.

## Connection Workflow

1. Check that Abaqus is running:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'ABQ|SMA|abaqus|cae' }
```

2. Ask the user to run this script inside the already-open Abaqus/CAE GUI with `File > Run Script...`:

```text
<skill-dir>\scripts\abaqus_cae_bridge.py
```

3. Wait for the user to say it is running. The Abaqus message area should show:

```text
Codex Abaqus bridge watching: E:\Abaqus-Codex job\.abaqus_cae_bridge\inbox.json
```

4. Ping from Codex:

```powershell
python <skill-dir>\scripts\abaqus_bridge_send.py --ping
```

Expected output includes model and viewport names.

5. For real operations, write a small Abaqus Python file in the workspace, then send it:

```powershell
python <skill-dir>\scripts\abaqus_bridge_send.py --file path\to\task.py --timeout 60
```

Prefer script files over inline command strings for multi-line code to avoid PowerShell newline escaping problems.

## Built-in Helper Commands

The sender script also provides reusable wrappers for common live-session tasks. These commands still execute through the same main-thread file bridge; they do not introduce a socket server or background CAE object access.

```powershell
python <skill-dir>\scripts\abaqus_bridge_send.py --get-model-info
python <skill-dir>\scripts\abaqus_bridge_send.py --list-jobs
python <skill-dir>\scripts\abaqus_bridge_send.py --set-workdir E:\temp\AbaqusRun
python <skill-dir>\scripts\abaqus_bridge_send.py --monitor-job-status
python <skill-dir>\scripts\abaqus_bridge_send.py --monitor-job-status Job-1
python <skill-dir>\scripts\abaqus_bridge_send.py --submit-job Job-1 --timeout 3600
python <skill-dir>\scripts\abaqus_bridge_send.py --inspect-odb E:\temp\AbaqusRun\Job-1.odb
python <skill-dir>\scripts\abaqus_bridge_send.py --capture-viewport E:\temp\AbaqusRun\viewport.png
```

Use `--get-model-info` before repair scripts when object names are uncertain. Use `--monitor-job-status <job>` before opening large solver files manually; it tails `.sta`/`.log` and extracts high-value diagnostics from `.msg`/`.dat`. Use `--inspect-odb` for fast metadata checks before deeper post-processing. Use `--capture-viewport` when the user needs a local image of the current CAE viewport.

Bridge errors include a short summary, source line excerpt, and common Abaqus hints for `KeyError`, `AttributeError`, `NameError`, and `TypeError`.

## Standard Abaqus Operation Pattern

- Never modify `Model-1` directly when the user asks for a repair or experiment. Copy it first, commonly:

```python
mdb.Model(name="Model-2", objectToCopy=mdb.models["Model-1"])
```

- After modifying visible objects, refresh the viewport:

```python
vp = session.viewports[session.viewports.keys()[0]]
vp.setValues(displayedObject=mdb.models["Model-2"].rootAssembly)
vp.forceRefresh()
```

- Keep modifications inside the currently open CAE by default. Do not call `mdb.saveAs(...)` unless the user explicitly asks for a separate CAE file.
- Before substantial edits, copy the appropriate existing model to a new model name in the same CAE, such as `Model-4` or the next clear model number, and modify only that copied model. Submit test jobs from the copied model so the original remains available for comparison.

## User-Visible Stepwise Workflow

Abaqus/CAE often does not repaint the model tree or viewport while a long Python script is running on the main thread. To keep the user able to watch progress, prefer short, visible operations instead of one large script whenever the task involves modeling, importing, repairing, or inspecting a CAE model.

- Split substantial work into small Abaqus Python task files and send them one at a time through `abaqus_bridge_send.py`. Let each task finish before sending the next one so Abaqus can process GUI events and repaint.
- After each visible modeling or inspection step, update the active viewport and force a refresh:

```python
vp = session.viewports[session.viewports.keys()[0]]
vp.setValues(displayedObject=target_object)
try:
    vp.view.fitView()
except Exception:
    pass
vp.forceRefresh()
```

- For new model construction, use a visible cadence: create or modify one major part, material/section group, assembly operation, mesh operation, load/BC group, or interaction group, then refresh the viewport before continuing.
- For `.inp` import, accept that `mdb.ModelFromInputFile(...)` is effectively atomic and may only appear after completion. After import, run a stepwise visual review: show each part alone, show the full assembly, then show loads, boundary conditions, interactions, constraints, sets, and surfaces as separate short steps.
- Prefer script files over inline snippets for stepwise visualization. If a step selector is needed, avoid names that collide with Abaqus constants such as `STEP`; use a namespaced variable such as `CODEX_VIS_STEP`.
- Tell the user what each visual step is about before sending it, especially when they are watching the Abaqus window. Use concise progress messages such as "showing the bolt part", "returning to full assembly", or "turning on boundary-condition symbols".
- Do not assume the model tree will expand live. Treat the viewport as the primary observable channel, and use console summaries to confirm model-tree objects such as parts, instances, materials, sections, interactions, loads, and boundary conditions.

## Job Diagnosis Pattern

When a job aborts, inspect these files in the job directory:

- `.log`: high-level Abaqus phase and final status
- `.sta`: increment history and whether the analysis completed
- `.msg`: convergence, contact, singularity, eigenvalue, and final error details
- `.dat`: input processing warnings, contact pair warnings, tie/contact adjustment, element quality
- `.inp`: exported model details when CAE object names need to be matched

Search for:

```text
ERROR
WARNING
TOO MANY ATTEMPTS
TIME INCREMENT REQUIRED
NEGATIVE EIGEN
CONTACT PAIR
INTERSECT
DISTORTED
ZERO PIVOT
NUMERICAL SINGULARITY
THE ANALYSIS HAS NOT BEEN COMPLETED
```

When changing and testing, use new job names such as `original_model2_try1`, `original_model2_try2`, etc. Keep old failed job files for comparison.

## Stop Bridge

When finished, stop the bridge politely:

```powershell
python <skill-dir>\scripts\abaqus_bridge_send.py --stop
```

If Abaqus is busy, create this flag file manually or from PowerShell:

```text
E:\Abaqus-Codex job\.abaqus_cae_bridge\stop.flag
```




