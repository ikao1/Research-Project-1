#!/usr/bin/env python3
"""Install the Look Decomposer panel into After Effects.

Writes two small loaders into each After Effects user Scripts folder:

    ~/Library/Preferences/Adobe/After Effects/<version>/Scripts/ScriptUI Panels/Look Decomposer.jsx
        -> Window > Look Decomposer (a dockable panel, shown as a tab)
    ~/Library/Preferences/Adobe/After Effects/<version>/Scripts/Open Look Decomposer.jsx
        -> File > Scripts > Open Look Decomposer (opens the window)

The loader points at this project folder and at a Python interpreter that has
Pillow installed. The panel code itself is read from the project each time
After Effects starts, so edits to ae_panel/LookDecomposer.jsx need only a
restart of After Effects.

Open the panel from Window > Look Decomposer, or from
File > Scripts > Open Look Decomposer, in After Effects.

Usage:
    python3 -m look_decomposer.install_panel               # install
    python3 -m look_decomposer.install_panel --status      # check
    python3 -m look_decomposer.install_panel --uninstall   # remove
    python3 -m look_decomposer.install_panel --python /path/to/python3
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE
PANEL_CODE = HERE / "ae_panel" / "LookDecomposer.jsx"
ENGINE = HERE / "ae" / "look_fx.jsx"
ANALYZER = HERE / "analyzer.py"
PLATE = HERE.parent / "test_stills" / "base_plate.png"
LOADER_NAME = "Look Decomposer.jsx"
MENU_LOADER_NAME = "Open Look Decomposer.jsx"
PREFS_ROOT = Path.home() / "Library" / "Preferences" / "Adobe" / "After Effects"

LOADER_TEMPLATE = r'''/*  Look Decomposer loader. Written by look_decomposer/install_panel.py.
    Re-run that script if the project folder moves.
    The panel code is read from the project each time this loads.
*/
(function (thisObj) {
    var LD_ROOT = __LD_ROOT__;
    var LD_PYTHON = __LD_PYTHON__;
    var panelFile = new File(LD_ROOT + "/ae_panel/LookDecomposer.jsx");
    if (!panelFile.exists) {
        alert("Look Decomposer: the panel code was not found at:\n" + panelFile.fsName +
              "\n\nRe-run install_panel.py from the project.");
        return;
    }
    panelFile.encoding = "UTF-8";
    panelFile.open("r");
    var source = panelFile.read();
    panelFile.close();
    var run = eval(source);
    run(thisObj, LD_ROOT, LD_PYTHON);
})(this);
'''


def version_folders():
    """User preference folders for After Effects versions, e.g. 26.5."""
    if not PREFS_ROOT.exists():
        return []
    versions = [p for p in PREFS_ROOT.iterdir()
                if p.is_dir() and re.fullmatch(r"\d+\.\d+", p.name)]
    return sorted(versions, key=lambda p: [int(x) for x in p.name.split(".")])


def scripts_folder(version_dir):
    return version_dir / "Scripts" / "ScriptUI Panels"


def loader_path(version_dir):
    return scripts_folder(version_dir) / LOADER_NAME


def menu_loader_path(version_dir):
    """Top-level Scripts folder: these appear in File > Scripts."""
    return version_dir / "Scripts" / MENU_LOADER_NAME


def all_loader_paths(version_dir):
    return [loader_path(version_dir), menu_loader_path(version_dir)]


def has_pillow(python):
    try:
        result = subprocess.run([python, "-c", "import PIL"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return result.returncode == 0


def check_project_files():
    missing = [p for p in (PANEL_CODE, ENGINE, ANALYZER, PLATE) if not p.exists()]
    return missing


def make_loader(python):
    return (LOADER_TEMPLATE
            .replace("__LD_ROOT__", json.dumps(str(PROJECT_DIR)))
            .replace("__LD_PYTHON__", json.dumps(str(python))))


def install(python, versions):
    missing = check_project_files()
    if missing:
        print("Missing project files:")
        for path in missing:
            print("  %s" % path)
        return 1

    if not has_pillow(python):
        print("The Python at %s does not have Pillow installed." % python)
        print("Install it, then run this command again:")
        print("  %s -m pip install pillow" % python)
        print("Or choose another Python with --python.")
        return 1

    if not versions:
        print("No After Effects preference folders were found in:")
        print("  %s" % PREFS_ROOT)
        print("Open After Effects once, then run this command again.")
        return 1

    text = make_loader(python)
    for version in versions:
        for target in all_loader_paths(version):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print("Installed: %s" % target)

    print()
    print("Next steps:")
    print("  1. Restart After Effects.")
    print("  2. Turn on Preferences > Scripting & Expressions >")
    print("     'Allow Scripts to Write Files and Access Network'.")
    print("  3. Open the panel with Window > Look Decomposer (docks as a tab),")
    print("     or File > Scripts > Open Look Decomposer (opens the window).")
    return 0


def uninstall(versions):
    removed = 0
    for version in versions:
        for target in all_loader_paths(version):
            if target.exists():
                target.unlink()
                print("Removed: %s" % target)
                removed += 1
    if not removed:
        print("No installed loader was found.")
    return 0


def status(python, versions):
    print("Project folder : %s" % PROJECT_DIR)
    print("Python         : %s (%s)" % (python, "Pillow OK" if has_pillow(python) else "Pillow MISSING"))
    missing = check_project_files()
    print("Project files  : %s" % ("all present" if not missing else "missing " + ", ".join(p.name for p in missing)))
    if not versions:
        print("After Effects  : no preference folders found")
        return 0
    for version in versions:
        for label, target in (("Window menu", loader_path(version)),
                              ("File > Scripts", menu_loader_path(version))):
            state = "installed" if target.exists() else "not installed"
            print("AE %-8s %-14s: %s (%s)" % (version.name, label, state, target))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default=sys.executable,
                        help="Python interpreter the panel should use (must have Pillow)")
    parser.add_argument("--version", action="append", metavar="VERSION",
                        help="Only this After Effects version, e.g. 26.5 (repeatable)")
    parser.add_argument("--status", action="store_true", help="Show what is installed")
    parser.add_argument("--uninstall", action="store_true", help="Remove the loader")
    args = parser.parse_args(argv)

    python = str(Path(args.python).expanduser())
    versions = version_folders()
    if args.version:
        wanted = set(args.version)
        versions = [v for v in versions if v.name in wanted]

    if args.status:
        return status(python, versions)
    if args.uninstall:
        return uninstall(versions)
    return install(python, versions)


if __name__ == "__main__":
    raise SystemExit(main())
