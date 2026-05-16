"""Send Python code to the Abaqus/CAE main-thread file bridge."""

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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("code", nargs="?", help="Python code to execute")
    parser.add_argument("--file", help="Read Python code from a file")
    parser.add_argument("--timeout", default=30.0, type=float)
    parser.add_argument(
        "--bridge-dir",
        default=os.environ.get("CODEX_ABAQUS_BRIDGE_DIR", DEFAULT_BRIDGE_DIR),
    )
    parser.add_argument("--ping", action="store_true", help="Probe mdb/session")
    parser.add_argument("--stop", action="store_true", help="Stop the bridge")
    args = parser.parse_args(argv)

    if args.ping:
        code = (
            "print('ABAQUS_BRIDGE_OK')\n"
            "print('models=' + repr(mdb.models.keys()))\n"
            "print('viewports=' + repr(session.viewports.keys()))\n"
        )
    elif args.stop:
        code = "bridge_stop()\nprint('ABAQUS_BRIDGE_STOP_REQUESTED')\n"
    elif args.file:
        with open(args.file, "rb") as handle:
            code = handle.read().decode("utf-8")
    elif args.code:
        code = args.code
    else:
        code = sys.stdin.read()

    result = send_code(code, args.bridge_dir, args.timeout)
    if result.get("output"):
        sys.stdout.write(result["output"])
    if not result.get("ok"):
        sys.stderr.write(result.get("error", ""))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
