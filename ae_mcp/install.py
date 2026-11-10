#!/usr/bin/env python3
"""Install (or remove) the After Effects side of the AE MCP bridge.

Copies ae_plugin/ae_mcp_bridge.jsx into each After Effects version's user
Startup folder and creates the mailbox directories used by mcp_server.py.
"""

import argparse
import os
import plistlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "ae_plugin" / "ae_mcp_bridge.jsx"
SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "Adobe" / "After Effects"
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

    if SUPPORT_ROOT.exists():
        for child in SUPPORT_ROOT.iterdir():
            if child.is_dir() and child.name[:1].isdigit():
                versions.add(child.name)

    return sorted(versions, key=lambda value: [int(p) for p in value.split(".") if p.isdigit()])


def startup_folders(versions):
    return [SUPPORT_ROOT / version / "Scripts" / "Startup" for version in versions]


def ensure_mailbox():
    for path in (BRIDGE_DIR, BRIDGE_DIR / "inbox", BRIDGE_DIR / "outbox"):
        path.mkdir(parents=True, exist_ok=True)


def install(versions):
    if not PLUGIN.exists():
        raise SystemExit("Missing plugin file: %s" % PLUGIN)

    ensure_mailbox()
    installed = []
    for folder in startup_folders(versions):
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / PLUGIN.name
        shutil.copy2(PLUGIN, target)
        installed.append(target)

    print("After Effects bridge installed.")
    print()
    print("  Mailbox : %s" % BRIDGE_DIR)
    for target in installed:
        print("  Startup : %s" % target)
    print()
    print("Next steps:")
    print("  1. Quit and reopen After Effects (or run the plugin once via")
    print("     File > Scripts > Run Script File...).")
    print("  2. In After Effects, enable Preferences > Scripting & Expressions >")
    print("     'Allow Scripts to Write Files and Access Network'.")
    print("  3. Restart opencode so it loads the new MCP server.")
    print()
    print("Verify with the aftereffects_status tool, or run:")
    print("  python3 %s --status" % Path(__file__).resolve())


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


def status():
    ensure_mailbox()
    print("Mailbox: %s" % BRIDGE_DIR)
    print("Inbox  : %s" % (BRIDGE_DIR / "inbox"))
    print("Outbox : %s" % (BRIDGE_DIR / "outbox"))

    status_file = BRIDGE_DIR / "status.json"
    if not status_file.exists():
        print("Heartbeat: none (After Effects has not run the bridge yet)")
        return

    import json
    import time

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
        help="Install for a specific After Effects version, e.g. 26.5. Repeatable.",
    )
    parser.add_argument("--uninstall", action="store_true", help="Remove the startup script.")
    parser.add_argument("--status", action="store_true", help="Show the mailbox and heartbeat.")
    args = parser.parse_args()

    if args.status:
        status()
        return

    versions = args.version or installed_versions()
    if not versions:
        raise SystemExit(
            "Could not detect an After Effects version. Pass --version (for example --version 26.5)."
        )

    if args.uninstall:
        uninstall(versions)
    else:
        install(versions)


if __name__ == "__main__":
    main()
