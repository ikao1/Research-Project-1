#!/usr/bin/env python3
"""opencode MCP server that drives a live Adobe After Effects session.

After Effects cannot host a TCP server from ExtendScript, so this bridge uses a
small file-based mailbox in the user's Application Support folder:

    ~/Library/Application Support/AE-MCP-Bridge/
        inbox/     <-- MCP server writes JSON requests here
        outbox/    <-- After Effects startup script writes JSON responses here
        status.json

Place ae_plugin/ae_mcp_bridge.jsx in After Effects' Scripts/Startup folder (run
install.py). On launch it polls the inbox, evaluates the ExtendScript it
receives, and writes the result to the outbox.
"""

import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path

SERVER_NAME = "after-effects-bridge"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL = "2024-11-05"

DEFAULT_BRIDGE_DIR = Path.home() / "Library" / "Application Support" / "AE-MCP-Bridge"
BRIDGE_DIR = Path(os.environ.get("AE_MCP_BRIDGE_DIR", str(DEFAULT_BRIDGE_DIR))).expanduser()
INBOX = BRIDGE_DIR / "inbox"
OUTBOX = BRIDGE_DIR / "outbox"
STATUS_FILE = BRIDGE_DIR / "status.json"

MAX_FIELD = 40000
DEFAULT_TIMEOUT = 120.0
MAX_TIMEOUT = 290.0
STALE_AFTER = 10.0
POLL_INTERVAL = 0.05

INSTALL_HINT = (
    "Install the After Effects side of the bridge, then restart After Effects:\n\n"
    '    python3 "%s/ae_mcp/install.py"\n\n'
    "If After Effects is already running, you can start the bridge manually with\n"
    "File > Scripts > Run Script File... and selecting:\n\n"
    "    ~/Library/Application Support/Adobe/After Effects/<version>/Scripts/Startup/ae_mcp_bridge.jsx\n\n"
    "Also enable Preferences > Scripting & Expressions > "
    "'Allow Scripts to Write Files and Access Network'."
) % Path(__file__).resolve().parent.parent


class BridgeError(Exception):
    pass


def ensure_dirs():
    for path in (BRIDGE_DIR, INBOX, OUTBOX):
        path.mkdir(parents=True, exist_ok=True)


def _truncate(text, limit=MAX_FIELD):
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated %d chars]" % (len(text) - limit)


def _read_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _status_age(status):
    if not isinstance(status, dict):
        return None
    try:
        return max(0.0, time.time() - float(status.get("ts", 0)) / 1000.0)
    except (TypeError, ValueError):
        return None


def bridge_call(code, timeout):
    """Send ExtendScript to After Effects and wait for the JSON response."""
    ensure_dirs()
    request_id = "%d_%s" % (time.time_ns(), uuid.uuid4().hex[:8])
    req_path = INBOX / (request_id + ".json")
    tmp_path = INBOX / ("." + request_id + ".tmp")
    resp_path = OUTBOX / (request_id + ".json")

    payload = json.dumps({"id": request_id, "code": code, "ts": time.time()})
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, req_path)

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if resp_path.exists():
                try:
                    raw = resp_path.read_text(encoding="utf-8")
                    response = json.loads(raw)
                except (OSError, ValueError):
                    time.sleep(POLL_INTERVAL)
                    continue
                try:
                    resp_path.unlink()
                except OSError:
                    pass
                if isinstance(response, dict) and response.get("id") == request_id:
                    return response
            time.sleep(POLL_INTERVAL)
        raise BridgeError(
            "Timed out after %g seconds waiting for After Effects.\n\n"
            "The script is probably still running (After Effects blocks while a script runs). "
            "Increase timeout_seconds if it is legitimately slow.\n\n"
            "Bridge mailbox: %s\n\n%s" % (timeout, BRIDGE_DIR, INSTALL_HINT)
        )
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(
            "Could not talk to the After Effects bridge (%s).\n\n"
            "Bridge mailbox: %s\n\n%s" % (exc, BRIDGE_DIR, INSTALL_HINT)
        )
    finally:
        # Do not leave a stale request behind if we gave up waiting.
        try:
            if req_path.exists():
                req_path.unlink()
        except OSError:
            pass


def _format_response(response, elapsed):
    ok = bool(response.get("ok"))
    parts = ["status: %s (%.2fs)" % ("ok" if ok else "script error", elapsed)]

    result = response.get("result")
    if result is not None:
        try:
            rendered = json.dumps(result, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            rendered = str(result)
        parts.append("--- result ---\n" + rendered)

    logs = (response.get("logs") or "").strip("\n")
    if logs:
        parts.append("--- logs ---\n" + logs)

    error = response.get("error")
    if error:
        parts.append("--- error ---\n" + str(error).rstrip("\n"))

    return _truncate("\n".join(parts), MAX_FIELD * 3), not ok


def _call_and_format(code, timeout):
    started = time.time()
    try:
        response = bridge_call(code, timeout)
    except BridgeError as exc:
        return _truncate(str(exc), MAX_FIELD * 3), True
    return _format_response(response, time.time() - started)


PROJECT_INFO_CODE = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
var comps = [];
for (var i = 1; i <= p.numItems; i++) {
    var item = p.item(i);
    if (item instanceof CompItem) {
        comps.push({ name: item.name, id: item.id });
    }
}
return {
    name: p.file ? p.file.name : "Untitled",
    path: p.file ? p.file.fsName : null,
    num_items: p.numItems,
    comps: comps
};
"""

LIST_COMPS_CODE = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
var comps = [];
for (var i = 1; i <= p.numItems; i++) {
    var item = p.item(i);
    if (item instanceof CompItem) {
        comps.push({
            name: item.name,
            id: item.id,
            width: item.width,
            height: item.height,
            duration: item.duration,
            frame_rate: item.frameRate,
            num_layers: item.numLayers
        });
    }
}
return comps;
"""

STATUS_PROBE_CODE = """\
var p = app.project;
return {
    alive: true,
    ae_version: String(app.version),
    project_name: (p && p.file) ? p.file.name : (p ? "Untitled" : null),
    project_path: (p && p.file) ? p.file.fsName : null,
    active_comp: (p && p.activeItem instanceof CompItem) ? p.activeItem.name : null
};
"""


def _int_arg(args, name, default, low, high):
    value = args.get(name, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be an integer" % name)
    if value < low or value > high:
        raise ValueError("'%s' must be between %d and %d" % (name, low, high))
    return value


def _float_arg(args, name, default, low, high):
    value = args.get(name, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be a number" % name)
    if value < low or value > high:
        raise ValueError("'%s' must be between %g and %g" % (name, low, high))
    return value


def _tool_status(args):
    status = _read_status()
    age = _status_age(status)

    if status and age is not None and age <= STALE_AFTER:
        info = dict(status)
        info["bridge_dir"] = str(BRIDGE_DIR)
        info["heartbeat_age_seconds"] = round(age, 1)
        text = "Bridge OK - heartbeat %.1fs ago\n%s" % (age, json.dumps(info, indent=2))
        return _truncate(text, MAX_FIELD * 2), False

    # Heartbeat is missing or stale; try a live probe in case the status file
    # is just not being written.
    try:
        response = bridge_call(STATUS_PROBE_CODE, timeout=5)
    except BridgeError as exc:
        text = (
            "After Effects bridge is NOT reachable.\n\n%s\n\n"
            "Last heartbeat: %s"
            % (
                exc,
                (
                    "none (status.json not found)"
                    if status is None
                    else "%.1fs ago" % age if age is not None else "unknown"
                ),
            )
        )
        return _truncate(text, MAX_FIELD * 3), True

    if not response.get("ok"):
        text = "Bridge is reachable, but the status probe failed:\n\n%s" % (
            str(response.get("error") or "unknown error").rstrip("\n")
        )
        return _truncate(text), True

    info = response.get("result") or {}
    info["bridge_dir"] = str(BRIDGE_DIR)
    text = "Bridge OK - live probe\n%s" % json.dumps(info, indent=2)
    return _truncate(text, MAX_FIELD * 2), False


def _tool_run(args):
    code = args.get("code")
    if not isinstance(code, str) or not code.strip():
        return "'code' must be a non-empty string", True
    timeout = args.get("timeout_seconds")
    try:
        timeout = float(timeout) if timeout is not None else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return "'timeout_seconds' must be a number", True
    timeout = max(1.0, min(timeout, MAX_TIMEOUT))
    return _call_and_format(code, timeout)


def _tool_project_info(args):
    return _call_and_format(PROJECT_INFO_CODE, 30)


def _tool_list_comps(args):
    return _call_and_format(LIST_COMPS_CODE, 30)


def _tool_create_comp(args):
    name = args.get("name") or "MCP Comp"
    if not isinstance(name, str) or not name.strip():
        return "'name' must be a non-empty string", True
    try:
        width = _int_arg(args, "width", 1920, 1, 16384)
        height = _int_arg(args, "height", 1080, 1, 16384)
        duration = _float_arg(args, "duration_seconds", 5.0, 0.1, 3600.0)
        fps = _float_arg(args, "frame_rate", 30.0, 1.0, 240.0)
    except ValueError as exc:
        return str(exc), True

    code = """\
if (!app.project) { app.newProject(); }
var p = app.project;
var comp = p.items.addComp(%s, %d, %d, 1, %g, %g);
comp.openInViewer();
return {
    name: comp.name,
    id: comp.id,
    width: comp.width,
    height: comp.height,
    duration: comp.duration,
    frame_rate: comp.frameRate
};
""" % (json.dumps(name), width, height, duration, fps)
    return _call_and_format(code, 60)


def _tool_save_project(args):
    path = args.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            return "'path' must be a non-empty string when provided", True
        path = os.path.abspath(os.path.expanduser(path))
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return "Cannot create output folder: %s" % exc, True
        code = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
p.save(new File(%s));
return { path: p.file.fsName };
""" % json.dumps(path)
    else:
        code = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
if (!p.file) { throw new Error("Project has never been saved; pass a path"); }
p.save();
return { path: p.file.fsName };
"""
    return _call_and_format(code, 120)


def _tool_import_footage(args):
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return "'path' must be a non-empty string", True
    path = os.path.abspath(os.path.expanduser(path))
    if not Path(path).exists():
        return "File not found: %s" % path, True

    comp_name = args.get("comp_name")
    if comp_name is not None and (not isinstance(comp_name, str) or not comp_name.strip()):
        return "'comp_name' must be a non-empty string when provided", True

    comp_expr = json.dumps(comp_name) if comp_name else "null"
    code = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
var file = new File(%s);
if (!file.exists) { throw new Error("File not found: " + file.fsName); }
var item = p.importFile(new ImportOptions(file));
var addedTo = null;
var compName = %s;
if (compName) {
    var comp = null;
    for (var i = 1; i <= p.numItems; i++) {
        var candidate = p.item(i);
        if (candidate instanceof CompItem && candidate.name === compName) {
            comp = candidate;
            break;
        }
    }
    if (!comp) { throw new Error("Composition not found: " + compName); }
    comp.layers.add(item);
    addedTo = comp.name;
}
return { name: item.name, id: item.id, type: item.typeName, added_to: addedTo };
""" % (json.dumps(path), comp_expr)
    return _call_and_format(code, 120)


def _tool_export_frame(args):
    comp_name = args.get("comp_name")
    if comp_name is not None and (not isinstance(comp_name, str) or not comp_name.strip()):
        return "'comp_name' must be a non-empty string when provided", True

    try:
        time_seconds = _float_arg(args, "time_seconds", 0.0, 0.0, 3600.0)
    except ValueError as exc:
        return str(exc), True

    output_path = args.get("output_path")
    if output_path is None or (isinstance(output_path, str) and not output_path.strip()):
        output_path = str(
            Path.home()
            / "Desktop"
            / ("AE_Frame_%s.png" % time.strftime("%Y%m%d_%H%M%S"))
        )
    elif not isinstance(output_path, str):
        return "'output_path' must be a string", True

    output_path = os.path.abspath(os.path.expanduser(output_path))
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "Cannot create output folder: %s" % exc, True

    comp_expr = json.dumps(comp_name) if comp_name else "null"
    code = """\
var p = app.project;
if (!p) { throw new Error("No project is open in After Effects"); }
var comp = null;
var compName = %s;
if (compName) {
    for (var i = 1; i <= p.numItems; i++) {
        var candidate = p.item(i);
        if (candidate instanceof CompItem && candidate.name === compName) {
            comp = candidate;
            break;
        }
    }
    if (!comp) { throw new Error("Composition not found: " + compName); }
} else {
    comp = p.activeItem;
    if (!(comp instanceof CompItem)) { comp = null; }
}
if (!comp) { throw new Error("No composition selected; pass comp_name or open a comp"); }
var file = new File(%s);
var ok = comp.saveFrameToPng(%g, file);
if (!ok) { throw new Error("saveFrameToPng failed for " + file.fsName); }
return { path: file.fsName, comp: comp.name, time: %g };
""" % (comp_expr, json.dumps(output_path), time_seconds, time_seconds)
    return _call_and_format(code, 120)


TOOLS = [
    {
        "name": "status",
        "description": (
            "Check whether the live After Effects bridge is reachable. Reports the "
            "After Effects version, open project, active composition, and heartbeat. "
            "Use this before running scripts when a connection problem is suspected."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run",
        "description": (
            "Execute ExtendScript/JSX in the connected live After Effects session and "
            "return the script's value. The code runs as a function body, so use "
            "`return` to send a value back (for example `return app.project.numItems;`). "
            "Use `$.writeln()` or the global `aeLog()` for logs, which are captured. "
            "After Effects' UI blocks while the script runs. State persists in the "
            "project, and globals survive across calls through `$.global`. Requires "
            "After Effects to be running with the bridge startup script installed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "ExtendScript source to execute inside After Effects.",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": (
                        "Seconds to wait for the result, default 120, max 290. "
                        "After Effects keeps running the script after a timeout."
                    ),
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "project_info",
        "description": (
            "Return the current After Effects project's name, file path, item count, "
            "and a list of compositions. Read-only."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_comps",
        "description": (
            "List every composition in the open project with size, duration, frame "
            "rate, and layer count. Read-only."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_comp",
        "description": "Create a new composition in the open project and return its details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Composition name, default 'MCP Comp'.",
                },
                "width": {"type": "integer", "description": "Width in pixels, default 1920."},
                "height": {"type": "integer", "description": "Height in pixels, default 1080."},
                "duration_seconds": {
                    "type": "number",
                    "description": "Duration in seconds, default 5.",
                },
                "frame_rate": {
                    "type": "number",
                    "description": "Frame rate, default 30.",
                },
            },
        },
    },
    {
        "name": "save_project",
        "description": (
            "Save the open After Effects project. Pass `path` to save to a new location "
            "(folders are created as needed); omit it to save in place."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional absolute path for the .aep file.",
                }
            },
        },
    },
    {
        "name": "import_footage",
        "description": (
            "Import an image, video, or audio file into the project. Optionally add the "
            "imported item to an existing composition by name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the media file.",
                },
                "comp_name": {
                    "type": "string",
                    "description": "Optional composition to add the footage to.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "export_frame",
        "description": (
            "Render a single frame of a composition to a PNG, useful for previews and "
            "for analyzing a look. Uses the named comp, or the active comp if omitted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "comp_name": {
                    "type": "string",
                    "description": "Optional composition name; defaults to the active comp.",
                },
                "time_seconds": {
                    "type": "number",
                    "description": "Time in seconds, default 0.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional absolute PNG path; defaults to the Desktop.",
                },
            },
        },
    },
]

_HANDLERS = {
    "status": _tool_status,
    "run": _tool_run,
    "project_info": _tool_project_info,
    "list_comps": _tool_list_comps,
    "create_comp": _tool_create_comp,
    "save_project": _tool_save_project,
    "import_footage": _tool_import_footage,
    "export_frame": _tool_export_frame,
}

_INSTRUCTIONS = (
    "Tools run ExtendScript in a live Adobe After Effects session through a local "
    "file-mailbox bridge. Use aftereffects_status to confirm the bridge is reachable, "
    "then aftereffects_run to execute JSX. Scripts block the After Effects UI while "
    "running. The startup script must be installed and After Effects must be open. "
    "Use the convenience tools (create_comp, import_footage, export_frame) for common "
    "operations and aftereffects_run for everything else."
)


def _send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(msg_id, result):
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id, code, message):
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        msg_id = message.get("id")
        if msg_id is None:
            continue
        method = message.get("method")

        if method == "initialize":
            params = message.get("params") or {}
            client_version = params.get("protocolVersion")
            _result(
                msg_id,
                {
                    "protocolVersion": (
                        client_version if isinstance(client_version, str) else DEFAULT_PROTOCOL
                    ),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": _INSTRUCTIONS,
                },
            )
        elif method == "ping":
            _result(msg_id, {})
        elif method == "tools/list":
            _result(msg_id, {"tools": TOOLS})
        elif method == "resources/list":
            _result(msg_id, {"resources": []})
        elif method == "prompts/list":
            _result(msg_id, {"prompts": []})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            handler = _HANDLERS.get(name)
            if handler is None:
                _error(msg_id, -32602, "Unknown tool: %s" % name)
                continue
            try:
                text, is_error = handler(params.get("arguments") or {})
            except Exception:
                text, is_error = (
                    "after-effects-bridge server error:\n" + traceback.format_exc(),
                    True,
                )
            _result(
                msg_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_error,
                },
            )
        else:
            _error(msg_id, -32601, "Method not found: %s" % method)


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
