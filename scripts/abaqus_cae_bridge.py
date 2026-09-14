"""Main-thread file bridge for an already-open Abaqus/CAE session.

Run from Abaqus/CAE with File > Run Script. The bridge watches JSON files in
E:\\Abaqus-Codex job\\.abaqus_cae_bridge and executes submitted Abaqus Python code on the
main CAE scripting thread.
"""

from __future__ import print_function

import json
import os
import re
import sys
import time
import traceback

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


DEFAULT_BRIDGE_DIR = r"E:\Abaqus-Codex job\.abaqus_cae_bridge"
BRIDGE_DIR = os.environ.get("CODEX_ABAQUS_BRIDGE_DIR", DEFAULT_BRIDGE_DIR)
INBOX = os.path.join(BRIDGE_DIR, "inbox.json")
OUTBOX = os.path.join(BRIDGE_DIR, "outbox.json")
STOP_FILE = os.path.join(BRIDGE_DIR, "stop.flag")
POLL_SECONDS = 0.2

_bridge_stop = False
_bridge_namespace = globals()


def bridge_stop():
    global _bridge_stop
    _bridge_stop = True


def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _atomic_write(path, text):
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp_path, path)


def _read_request():
    if not os.path.exists(INBOX):
        return None
    try:
        with open(INBOX, "rb") as handle:
            raw = handle.read()
        os.remove(INBOX)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {
            "id": "unknown",
            "code": "",
            "_load_error": traceback.format_exc(),
        }


def _extract_error_line(source, exc, tb_text):
    lineno = getattr(exc, "lineno", None)
    if lineno is not None:
        return lineno
    matches = re.findall(r'File "<codex-abaqus-bridge>", line (\d+)', tb_text)
    if matches:
        try:
            return int(matches[-1])
        except Exception:
            return None
    return None


def _extract_excerpt(source, lineno, radius=2):
    if lineno is None:
        return None
    lines = source.splitlines()
    index = lineno - 1
    if index < 0 or index >= len(lines):
        return None
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    out = []
    for pos in range(start, end):
        marker = ">>" if pos == index else "  "
        out.append("%s %4d | %s" % (marker, pos + 1, lines[pos]))
    return "\n".join(out)


def _core_error_line(tb_text, exc):
    lines = [line for line in tb_text.splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return str(exc)


def _format_error(source, exc, tb_text):
    error_type = type(exc).__name__
    lineno = _extract_error_line(source, exc, tb_text)
    location = " at line %s" % lineno if lineno else ""
    parts = [tb_text.rstrip(), "", "Codex Abaqus bridge summary:"]
    parts.append("  %s%s: %s" % (error_type, location, _core_error_line(tb_text, exc)))

    excerpt = _extract_excerpt(source, lineno)
    if excerpt:
        parts.append("  Code excerpt:")
        parts.extend("    " + line for line in excerpt.splitlines())

    text = str(exc)
    if error_type == "KeyError":
        parts.append(
            "  Hint: a model, part, set, surface, or job name may differ from the script. "
            "Run abaqus_bridge_send.py --get-model-info or --list-jobs to inspect names."
        )
    elif error_type == "AttributeError":
        parts.append(
            "  Hint: inspect the live object with dir(...), or run --get-model-info for common CAE containers."
        )
    elif error_type == "NameError":
        match = re.search(r"name '([^']+)' is not defined", text)
        missing = match.group(1) if match else ""
        if missing and missing.isupper():
            parts.append(
                "  Hint: uppercase Abaqus constants usually require: from abaqusConstants import *"
            )
        else:
            parts.append("  Hint: check variable scope or run a smaller probe before continuing.")
    elif error_type == "TypeError":
        parts.append("  Hint: check the Abaqus API call signature and keyword names for this version.")

    return "\n".join(parts) + "\n"


def _execute(req):
    output = StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    error = req.get("_load_error", "")
    ok = not bool(error)

    if ok:
        try:
            sys.stdout = output
            sys.stderr = output
            source = req.get("code", "")
            code_obj = compile(source, "<codex-abaqus-bridge>", "exec")
            exec(code_obj, _bridge_namespace, _bridge_namespace)
        except Exception as exc:
            ok = False
            error = _format_error(req.get("code", ""), exc, traceback.format_exc())
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    _atomic_write(
        OUTBOX,
        json.dumps(
            {
                "id": req.get("id", "unknown"),
                "ok": ok,
                "output": output.getvalue(),
                "error": error,
            }
        ),
    )


def _refresh_viewports():
    try:
        for viewport_name in session.viewports.keys():
            session.viewports[viewport_name].forceRefresh()
    except Exception:
        pass


def run_bridge():
    _ensure_dir(BRIDGE_DIR)
    for path in (INBOX, OUTBOX, STOP_FILE):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    print("Codex Abaqus bridge watching: %s" % INBOX)
    print("Send commands with abaqus_bridge_send.py. Use --stop to stop.")

    while not _bridge_stop and not os.path.exists(STOP_FILE):
        req = _read_request()
        if req is not None:
            _execute(req)
            _refresh_viewports()
        time.sleep(POLL_SECONDS)

    print("Codex Abaqus bridge stopped")


run_bridge()

