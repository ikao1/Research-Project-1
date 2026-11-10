#!/usr/bin/env python3
"""End-to-end test for the After Effects MCP bridge.

Runs the real MCP server against a fake After Effects responder that watches the
same file mailbox. This validates the MCP handshake, tool schemas, request
routing, and heartbeat handling without needing After Effects.
"""

import json
import os
import select
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / "mcp_server.py"

EXPECTED_TOOLS = {
    "status",
    "run",
    "project_info",
    "list_comps",
    "create_comp",
    "save_project",
    "import_footage",
    "export_frame",
}


class FakeAfterEffects(threading.Thread):
    def __init__(self, bridge_dir):
        super().__init__(daemon=True)
        self.bridge = Path(bridge_dir)
        self.inbox = self.bridge / "inbox"
        self.outbox = self.bridge / "outbox"
        self.stop_event = threading.Event()

    def run(self):
        for path in (self.bridge, self.inbox, self.outbox):
            path.mkdir(parents=True, exist_ok=True)
        self.write_status()
        last_status = 0.0
        while not self.stop_event.is_set():
            for request_path in sorted(self.inbox.glob("*.json")):
                try:
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                try:
                    request_path.unlink()
                except OSError:
                    pass
                response = {
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"fake_ae": True, "code": request.get("code")},
                    "error": None,
                    "logs": "fake-ae-log",
                    "ts": int(time.time() * 1000),
                }
                tmp = self.outbox / (request_path.name + ".tmp")
                tmp.write_text(json.dumps(response), encoding="utf-8")
                os.replace(tmp, self.outbox / request_path.name)

            now = time.time()
            if now - last_status > 0.5:
                self.write_status()
                last_status = now
            time.sleep(0.02)

    def write_status(self):
        status = {
            "alive": True,
            "bridge": "ae_mcp",
            "bridge_version": "0.1.0",
            "ae_version": "26.5.0",
            "project_name": "Test Project",
            "project_path": None,
            "num_items": 3,
            "active_comp": "Comp 1",
            "ts": int(time.time() * 1000),
        }
        tmp = self.bridge / "status.json.tmp"
        tmp.write_text(json.dumps(status), encoding="utf-8")
        os.replace(tmp, self.bridge / "status.json")


def send(proc, message):
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def receive(proc, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], 0.1)
        if ready:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout")
            return json.loads(line)
    raise TimeoutError("no MCP response within %.1fs" % timeout)


def request(proc, msg_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    send(proc, message)
    return receive(proc)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        bridge_dir = Path(tmp) / "bridge"
        fake = FakeAfterEffects(bridge_dir)
        fake.start()

        env = dict(os.environ)
        env["AE_MCP_BRIDGE_DIR"] = str(bridge_dir)
        env["AE_MCP_TRANSPORT"] = "mailbox"
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        try:
            init = request(
                proc,
                1,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "bridge-test", "version": "0"},
                },
            )
            assert init["result"]["serverInfo"]["name"] == "after-effects-bridge", init

            send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            tools = request(proc, 2, "tools/list")
            names = {tool["name"] for tool in tools["result"]["tools"]}
            assert names == EXPECTED_TOOLS, names

            run = request(
                proc,
                3,
                "tools/call",
                {"name": "run", "arguments": {"code": "return 1 + 1;"}},
            )
            run_text = run["result"]["content"][0]["text"]
            assert "status: ok" in run_text, run_text
            assert "fake_ae" in run_text, run_text
            assert run["result"]["isError"] is False, run

            status = request(
                proc, 4, "tools/call", {"name": "status", "arguments": {}}
            )
            status_text = status["result"]["content"][0]["text"]
            assert "Bridge OK" in status_text, status_text
            assert "26.5.0" in status_text, status_text

            create = request(
                proc,
                5,
                "tools/call",
                {
                    "name": "create_comp",
                    "arguments": {"name": "Bridge Test", "width": 640, "height": 360},
                },
            )
            create_text = create["result"]["content"][0]["text"]
            assert "addComp" in create_text, create_text

            print("PASS: handshake, tools/list, run, status heartbeat, create_comp routing")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            fake.stop_event.set()
            fake.join(timeout=3)

            stderr = proc.stderr.read()
            if stderr.strip():
                print(stderr, file=sys.stderr)


if __name__ == "__main__":
    main()
