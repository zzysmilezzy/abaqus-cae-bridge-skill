"""Main-thread file bridge for an already-open Abaqus/CAE session.

Run from Abaqus/CAE with File > Run Script. The bridge watches JSON files in
E:\\Abaqus-Codex job\\.abaqus_cae_bridge and executes submitted Abaqus Python code on the
main CAE scripting thread.
"""

from __future__ import print_function

import json
import os
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
            code_obj = compile(req.get("code", ""), "<codex-abaqus-bridge>", "exec")
            exec(code_obj, _bridge_namespace, _bridge_namespace)
        except Exception:
            ok = False
            error = traceback.format_exc()
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
