#!/usr/bin/env python3
"""Configure the After Effects MCP bridge.

On macOS the MCP server talks to After Effects through AppleScript DoScript, so
no startup script is required. This tool prepares the fallback file mailbox and
can optionally install the legacy mailbox startup script.

The live probe uses mcp_server.py, so it exercises the same transport that
opencode will use.
"""

import argparse
import json
import os
import plistlib
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "ae_plugin" / "ae_mcp_bridge.jsx"
PREFS_ROOT = Path.home() / "Library" / "Preferences" / "Adobe" / "After Effects"
SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "Adobe" / "After Effects"
SCRIPT_ROOTS = (PREFS_ROOT, SUPPORT_ROOT)
BRIDGE_DIR = Path(
    os.environ.get(
        "AE_MCP_BRIDGE_DIR",
        str(Path.home() / "Library" / "Application Support" / "AE-MCP-Bridge"),
    )
).expanduser()


def _version_from_app(app):
    info = app / "Contents" / "Info.plist"
    try:
        with info.open("rb") as handle:
            data = plistlib.load(handle)
        short = str(data.get("CFBundleShortVersionString", ""))
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    parts = short.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return short or None


def installed_versions():
    versions = set()
    for app in Path("/Applications").glob("Adobe After Effects */Adobe After Effects *.app"):
        version = _version_from_app(app)
        if version:
            versions.add(version)

    for root in SCRIPT_ROOTS:
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and child.name[:1].isdigit():
                    versions.add(child.name)

    return sorted(versions, key=lambda value: [int(p) for p in value.split(".") if p.isdigit()])


def startup_folders(versions):
    folders = []
    for version in versions:
        for root in SCRIPT_ROOTS:
            folder = root / version / "Scripts" / "Startup"
            if folder not in folders:
                folders.append(folder)
    return folders


def ensure_mailbox():
    for path in (BRIDGE_DIR, BRIDGE_DIR / "inbox", BRIDGE_DIR / "outbox", BRIDGE_DIR / "doscript"):
        path.mkdir(parents=True, exist_ok=True)


def install_startup(versions):
    if not PLUGIN.exists():
        raise SystemExit("Missing plugin file: %s" % PLUGIN)

    installed = []
    for folder in startup_folders(versions):
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / PLUGIN.name
        shutil.copy2(PLUGIN, target)
        installed.append(target)

    print("Installed the legacy mailbox startup script:")
    for target in installed:
        print("  %s" % target)
    print()
    print("This is only needed for AE_MCP_TRANSPORT=mailbox. macOS uses DoScript.")


def uninstall(versions):
    removed = []
    for folder in startup_folders(versions):
        target = folder / PLUGIN.name
        if target.exists():
            target.unlink()
            removed.append(target)

    if removed:
        print("Removed the After Effects bridge startup script:")
        for target in removed:
            print("  %s" % target)
    else:
        print("No installed startup script was found.")


def _load_server():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import mcp_server

    return mcp_server


def status():
    ensure_mailbox()
    print("Mailbox: %s" % BRIDGE_DIR)
    print("Inbox  : %s" % (BRIDGE_DIR / "inbox"))
    print("Outbox : %s" % (BRIDGE_DIR / "outbox"))

    try:
        server = _load_server()
    except Exception as exc:
        print("Transport: unknown (%s)" % exc)
        return

    if server.doscript_enabled():
        print("Transport: DoScript (macOS; no startup script required)")
        print("Runner: %s" % server.RUNNER_PATH)
        try:
            response = server.bridge_call(server.STATUS_PROBE_CODE, timeout=30)
        except Exception as exc:
            print("Live probe: FAILED")
            print(str(exc))
            return

        if not response.get("ok"):
            print("Live probe: script error")
            print(str(response.get("error") or "unknown error"))
            return

        print("Live probe: OK")
        print(json.dumps(response.get("result") or {}, indent=2))
        return

    print("Transport: mailbox")
    status_file = BRIDGE_DIR / "status.json"
    if not status_file.exists():
        print("Heartbeat: none (After Effects has not run the bridge yet)")
        return

    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("Heartbeat: unreadable (%s)" % exc)
        return

    age = time.time() - float(data.get("ts", 0)) / 1000.0
    print("Heartbeat: %.1f seconds ago" % age)
    print("After Effects: %s" % data.get("ae_version"))
    print("Project: %s" % (data.get("project_path") or data.get("project_name")))
    print("Active comp: %s" % data.get("active_comp"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        action="append",
        metavar="VERSION",
        help="Target a specific After Effects version, e.g. 26.5. Repeatable.",
    )
    parser.add_argument("--uninstall", action="store_true", help="Remove the startup script.")
    parser.add_argument("--status", action="store_true", help="Show the transport and live status.")
    parser.add_argument(
        "--with-startup",
        action="store_true",
        help="Also install the legacy mailbox startup script.",
    )
    args = parser.parse_args()

    if args.status:
        status()
        return

    versions = args.version or installed_versions()

    if args.uninstall:
        uninstall(versions)
        return

    ensure_mailbox()

    if args.with_startup:
        if not versions:
            raise SystemExit(
                "Could not detect an After Effects version. Pass --version (for example --version 26.5)."
            )
        install_startup(versions)
        return

    print("Mailbox ready: %s" % BRIDGE_DIR)
    print("macOS uses AppleScript DoScript; no startup script is required.")
    print()
    print("Next steps:")
    print("  1. Open After Effects.")
    print("  2. Enable Preferences > Scripting & Expressions >")
    print("     'Allow Scripts to Write Files and Access Network'.")
    print("  3. Restart opencode so it loads the MCP server.")
    print()
    print("Verify with:")
    print("  python3 %s --status" % Path(__file__).resolve())


if __name__ == "__main__":
    main()
