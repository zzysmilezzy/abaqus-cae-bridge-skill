"""Send Python code to the Abaqus/CAE main-thread file bridge.

The basic mode sends arbitrary Abaqus Python. Convenience commands wrap common
inspection, job, ODB, and viewport tasks so they are available without writing a
one-off script every time.
"""

from __future__ import print_function

import argparse
import json
import os
import sys
import time
import uuid


DEFAULT_BRIDGE_DIR = r"E:\Abaqus-Codex job\.abaqus_cae_bridge"


def atomic_write(path, text):
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp_path, path)


def send_code(code, bridge_dir, timeout):
    inbox = os.path.join(bridge_dir, "inbox.json")
    outbox = os.path.join(bridge_dir, "outbox.json")
    request_id = str(uuid.uuid4())

    if not os.path.isdir(bridge_dir):
        os.makedirs(bridge_dir)
    if os.path.exists(outbox):
        os.remove(outbox)

    atomic_write(inbox, json.dumps({"id": request_id, "code": code}))

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(outbox):
            with open(outbox, "rb") as handle:
                result = json.loads(handle.read().decode("utf-8"))
            if result.get("id") == request_id:
                return result
        time.sleep(0.1)

    raise RuntimeError("Timed out waiting for Abaqus bridge in %s" % bridge_dir)


def _json(value):
    return json.dumps(value)


def _get_model_info_code():
    return r'''
from __future__ import print_function
import json
from abaqus import mdb, session

def _keys(obj):
    try:
        return [str(item) for item in list(obj.keys())]
    except Exception:
        return []

def _count(obj, attr):
    try:
        return len(getattr(obj, attr))
    except Exception:
        return None

models = {}
for model_name in mdb.models.keys():
    model = mdb.models[model_name]
    model_info = {
        "parts": _keys(model.parts),
        "materials": _keys(model.materials),
        "sections": _keys(model.sections),
        "steps": _keys(model.steps),
        "loads": _keys(model.loads),
        "boundary_conditions": _keys(model.boundaryConditions),
        "interactions": _keys(model.interactions),
        "constraints": _keys(model.constraints),
        "amplitudes": _keys(model.amplitudes),
        "assembly_instances": _keys(model.rootAssembly.instances),
        "assembly_sets": _keys(model.rootAssembly.sets),
        "assembly_surfaces": _keys(model.rootAssembly.surfaces),
    }

    part_details = {}
    for part_name in model.parts.keys():
        part = model.parts[part_name]
        part_details[str(part_name)] = {
            "cells": _count(part, "cells"),
            "faces": _count(part, "faces"),
            "edges": _count(part, "edges"),
            "vertices": _count(part, "vertices"),
            "elements": _count(part, "elements"),
            "nodes": _count(part, "nodes"),
            "sets": _keys(part.sets),
            "surfaces": _keys(part.surfaces),
        }
    model_info["part_details"] = part_details
    models[str(model_name)] = model_info

jobs = []
for job_name in mdb.jobs.keys():
    job = mdb.jobs[job_name]
    item = {"name": str(job_name)}
    for attr in ("status", "type", "model", "description", "numCpus",
                 "numDomains", "memory", "explicitPrecision"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)

result = {
    "models": models,
    "jobs": jobs,
    "current_viewport": str(getattr(session, "currentViewportName", "")),
    "viewports": _keys(session.viewports),
}
print(json.dumps(result, indent=2, sort_keys=True))
'''


def _list_jobs_code():
    return r'''
from __future__ import print_function
import json
from abaqus import mdb

jobs = []
for job_name in mdb.jobs.keys():
    job = mdb.jobs[job_name]
    item = {"name": str(job_name)}
    for attr in ("status", "type", "model", "description", "numCpus",
                 "numDomains", "memory", "explicitPrecision"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    jobs.append(item)

print(json.dumps({"jobs": jobs}, indent=2, sort_keys=True))
'''


def _set_workdir_code(path):
    return r'''
from __future__ import print_function
import json
import os

new_path = __PATH__
old_dir = os.getcwd()
if not os.path.isdir(new_path):
    raise OSError("Directory does not exist: " + new_path)
os.chdir(new_path)
print(json.dumps({
    "success": True,
    "previous": old_dir,
    "current": os.getcwd(),
}, indent=2, sort_keys=True))
'''.replace("__PATH__", _json(path))


def _submit_job_code(job_name):
    return r'''
from __future__ import print_function
import json
from abaqus import mdb

job_name = __JOB_NAME__
if job_name not in mdb.jobs:
    raise KeyError("Job not found: " + job_name)

job = mdb.jobs[job_name]
job.submit(consistencyChecking=False)
job.waitForCompletion()
print(json.dumps({
    "success": True,
    "job": job_name,
    "status": str(getattr(job, "status", "UNKNOWN")),
}, indent=2, sort_keys=True))
'''.replace("__JOB_NAME__", _json(job_name))


def _monitor_job_status_code(job_name):
    return r'''
from __future__ import print_function
import json
import os
import re
from abaqus import mdb

job_name = __JOB_NAME__
patterns = [
    r"ERROR",
    r"WARNING",
    r"TOO MANY ATTEMPTS",
    r"TIME INCREMENT REQUIRED",
    r"NEGATIVE EIGEN",
    r"CONTACT PAIR",
    r"INTERSECT",
    r"DISTORTED",
    r"ZERO PIVOT",
    r"NUMERICAL SINGULARITY",
    r"THE ANALYSIS HAS NOT BEEN COMPLETED",
    r"THE ANALYSIS HAS BEEN COMPLETED",
]

def _tail_lines(path, count):
    try:
        with open(path, "r") as handle:
            return handle.read().splitlines()[-count:]
    except Exception:
        return []

def _grep_tail(path, regexes, limit):
    try:
        rx = re.compile("|".join(regexes), re.IGNORECASE)
        matches = []
        with open(path, "r") as handle:
            for line in handle:
                if rx.search(line):
                    matches.append(line.rstrip())
        return matches[-limit:]
    except Exception:
        return []

def _job_item(name):
    job = mdb.jobs[name]
    item = {"name": str(name)}
    for attr in ("status", "type", "model", "description", "numCpus",
                 "numDomains", "memory"):
        try:
            value = getattr(job, attr, None)
            if value is not None:
                item[attr] = str(value)
        except Exception:
            pass
    return item

workdir = os.getcwd()
if not job_name:
    result = {
        "workdir": workdir,
        "jobs": [_job_item(name) for name in mdb.jobs.keys()],
    }
else:
    job_base = os.path.join(workdir, job_name)
    files = {}
    for ext in (".lck", ".log", ".sta", ".msg", ".dat", ".inp", ".odb"):
        path = job_base + ext
        files[ext[1:]] = {
            "path": path,
            "exists": os.path.exists(path),
            "size": os.path.getsize(path) if os.path.exists(path) else 0,
        }

    result = {
        "job_name": job_name,
        "workdir": workdir,
        "job": _job_item(job_name) if job_name in mdb.jobs else None,
        "files": files,
        "lock_present": files["lck"]["exists"],
        "sta_tail": _tail_lines(job_base + ".sta", 20),
        "log_tail": _tail_lines(job_base + ".log", 20),
        "msg_diagnostics_tail": _grep_tail(job_base + ".msg", patterns, 40),
        "dat_diagnostics_tail": _grep_tail(job_base + ".dat", patterns, 40),
    }

print(json.dumps(result, indent=2, sort_keys=True))
'''.replace("__JOB_NAME__", _json(job_name or ""))


def _inspect_odb_code(odb_path):
    return r'''
from __future__ import print_function
import json
from odbAccess import openOdb

odb_path = __ODB_PATH__
odb = None
try:
    odb = openOdb(path=odb_path, readOnly=True)
    steps = []

    def _sample_frames(frames):
        count = len(frames)
        if count <= 5:
            return [(i, frames[i]) for i in range(count)]
        idxs = [0, int(round((count - 1) * 0.25)),
                int(round((count - 1) * 0.5)),
                int(round((count - 1) * 0.75)), count - 1]
        out = []
        seen = []
        for idx in idxs:
            if idx not in seen:
                seen.append(idx)
                out.append((idx, frames[idx]))
        return out

    for step_name in odb.steps.keys():
        step = odb.steps[step_name]
        frame_items = []
        for idx, frame in _sample_frames(step.frames):
            frame_items.append({
                "index": idx,
                "frameId": getattr(frame, "frameId", None),
                "frameValue": getattr(frame, "frameValue", None),
                "description": str(getattr(frame, "description", "")),
            })

        field_outputs = []
        history_regions = []
        if len(step.frames):
            try:
                for key in step.frames[-1].fieldOutputs.keys():
                    field = step.frames[-1].fieldOutputs[key]
                    field_outputs.append({
                        "name": str(key),
                        "position": str(getattr(field, "position", "")),
                        "components": [str(x) for x in (getattr(field, "componentLabels", []) or [])],
                        "validInvariants": [str(x) for x in (getattr(field, "validInvariants", []) or [])],
                    })
            except Exception:
                pass
            try:
                history_regions = [str(x) for x in step.historyRegions.keys()]
            except Exception:
                pass

        steps.append({
            "name": str(step_name),
            "procedure": str(getattr(step, "procedure", "")),
            "totalTime": getattr(step, "totalTime", None),
            "frame_count": len(step.frames),
            "sample_frames": frame_items,
            "fieldOutputs": field_outputs,
            "historyRegions": history_regions,
        })

    result = {
        "path": odb_path,
        "title": str(getattr(odb, "title", "")),
        "description": str(getattr(odb, "description", "")),
        "parts": [str(x) for x in odb.parts.keys()] if hasattr(odb, "parts") else [],
        "instances": [str(x) for x in odb.rootAssembly.instances.keys()] if hasattr(odb, "rootAssembly") else [],
        "steps": steps,
    }
finally:
    if odb is not None:
        odb.close()

print(json.dumps(result, indent=2, sort_keys=True))
'''.replace("__ODB_PATH__", _json(odb_path))


def _capture_viewport_code(output_path, viewport_name, image_format):
    return r'''
from __future__ import print_function
import json
import os
import shutil
from abaqus import session
import abaqusConstants

output_path = __OUTPUT_PATH__
viewport_name = __VIEWPORT_NAME__
fmt_name = __FORMAT__.upper()
fmt_map = {
    "PNG": abaqusConstants.PNG,
    "TIFF": abaqusConstants.TIFF,
    "SVG": abaqusConstants.SVG,
    "EPS": abaqusConstants.EPS,
    "PS": abaqusConstants.PS,
}
fmt = fmt_map.get(fmt_name, abaqusConstants.PNG)
suffix = "." + fmt_name.lower()

folder = os.path.dirname(output_path)
if folder and not os.path.isdir(folder):
    os.makedirs(folder)

if not viewport_name or viewport_name not in session.viewports.keys():
    viewport_name = session.currentViewportName
vp = session.viewports[viewport_name]

base, ext = os.path.splitext(output_path)
print_name = base if ext.lower() == suffix else output_path
session.printToFile(fileName=print_name, format=fmt, canvasObjects=(vp,))

candidates = []
for item in (output_path, print_name, print_name + suffix, output_path + suffix):
    if item not in candidates:
        candidates.append(item)

actual_path = None
for item in candidates:
    if os.path.exists(item):
        actual_path = item
        break

if actual_path is None:
    raise IOError("Viewport capture did not create an expected file near: " + output_path)

if os.path.abspath(actual_path) != os.path.abspath(output_path):
    shutil.copyfile(actual_path, output_path)
    actual_path = output_path

print(json.dumps({
    "success": True,
    "viewport": str(viewport_name),
    "format": fmt_name.lower(),
    "path": actual_path,
    "size": os.path.getsize(actual_path),
}, indent=2, sort_keys=True))
'''.replace("__OUTPUT_PATH__", _json(output_path)).replace(
        "__VIEWPORT_NAME__", _json(viewport_name or "")
    ).replace("__FORMAT__", _json(image_format or "PNG"))


def _selected_command_count(args):
    selected = [
        args.ping,
        args.stop,
        args.get_model_info,
        args.list_jobs,
        args.set_workdir is not None,
        args.submit_job is not None,
        args.monitor_job_status is not None,
        args.inspect_odb is not None,
        args.capture_viewport is not None,
        args.file is not None,
        args.code is not None,
    ]
    return sum(1 for item in selected if item)


def _default_timeout(args):
    if args.timeout is not None:
        return args.timeout
    if args.submit_job:
        return 3600.0
    if args.inspect_odb:
        return 120.0
    if args.capture_viewport:
        return 60.0
    return 30.0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("code", nargs="?", help="Python code to execute")
    parser.add_argument("--file", help="Read Python code from a file")
    parser.add_argument("--timeout", default=None, type=float)
    parser.add_argument(
        "--bridge-dir",
        default=os.environ.get("CODEX_ABAQUS_BRIDGE_DIR", DEFAULT_BRIDGE_DIR),
    )
    parser.add_argument("--ping", action="store_true", help="Probe mdb/session")
    parser.add_argument("--stop", action="store_true", help="Stop the bridge")
    parser.add_argument("--get-model-info", action="store_true",
                        help="Print models, parts, sets, surfaces, jobs, and viewports as JSON")
    parser.add_argument("--list-jobs", action="store_true",
                        help="List jobs in the current CAE session as JSON")
    parser.add_argument("--set-workdir", metavar="PATH",
                        help="Change Abaqus current working directory")
    parser.add_argument("--submit-job", metavar="JOB_NAME",
                        help="Submit an existing Abaqus job and wait for completion")
    parser.add_argument("--monitor-job-status", nargs="?", const="", metavar="JOB_NAME",
                        help="List jobs, or inspect .lck/.log/.sta/.msg/.dat files for JOB_NAME")
    parser.add_argument("--inspect-odb", metavar="ODB_PATH",
                        help="Open an ODB read-only and print metadata as JSON")
    parser.add_argument("--capture-viewport", metavar="OUTPUT_PATH",
                        help="Capture the current or named viewport to an image file")
    parser.add_argument("--viewport", default="",
                        help="Viewport name for --capture-viewport")
    parser.add_argument("--image-format", default="PNG",
                        help="Image format for --capture-viewport: PNG, TIFF, SVG, EPS, or PS")
    args = parser.parse_args(argv)

    if _selected_command_count(args) > 1:
        parser.error("choose only one command, script file, or inline code")

    if args.ping:
        code = (
            "print('ABAQUS_BRIDGE_OK')\n"
            "print('models=' + repr(mdb.models.keys()))\n"
            "print('viewports=' + repr(session.viewports.keys()))\n"
        )
    elif args.stop:
        code = "bridge_stop()\nprint('ABAQUS_BRIDGE_STOP_REQUESTED')\n"
    elif args.get_model_info:
        code = _get_model_info_code()
    elif args.list_jobs:
        code = _list_jobs_code()
    elif args.set_workdir is not None:
        code = _set_workdir_code(os.path.abspath(args.set_workdir))
    elif args.submit_job is not None:
        code = _submit_job_code(args.submit_job)
    elif args.monitor_job_status is not None:
        code = _monitor_job_status_code(args.monitor_job_status)
    elif args.inspect_odb is not None:
        code = _inspect_odb_code(os.path.abspath(args.inspect_odb))
    elif args.capture_viewport is not None:
        code = _capture_viewport_code(
            os.path.abspath(args.capture_viewport),
            args.viewport,
            args.image_format,
        )
    elif args.file:
        with open(args.file, "rb") as handle:
            code = handle.read().decode("utf-8")
    elif args.code:
        code = args.code
    else:
        code = sys.stdin.read()

    result = send_code(code, args.bridge_dir, _default_timeout(args))
    if result.get("output"):
        sys.stdout.write(result["output"])
    if not result.get("ok"):
        sys.stderr.write(result.get("error", ""))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

