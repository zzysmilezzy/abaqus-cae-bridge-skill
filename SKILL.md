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

- Save repaired CAE files with `mdb.saveAs(pathName=...)` rather than overwriting the user's original CAE unless they explicitly ask.

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
