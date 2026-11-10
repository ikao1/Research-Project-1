#!/usr/bin/env python3
"""Run JSX in the live After Effects session.

Reuses the ae_mcp DoScript transport (mcp_server.py) so there is exactly one
implementation of the AppleScript bridge. Raises BridgeError if AE is not
reachable.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = Path(__file__).resolve().parent / "ae" / "look_fx.jsx"


def load_bridge():
    spec = importlib.util.spec_from_file_location(
        "ae_mcp_server_shared", REPO_ROOT / "ae_mcp" / "mcp_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_jsx(code, timeout=120):
    bridge = load_bridge()
    if not bridge.doscript_enabled():
        print("DoScript transport unavailable (need macOS + osascript + AE runner).",
              file=sys.stderr)
        raise SystemExit(2)
    return bridge.doscript_call(code, timeout)


def _json_literal(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def build_comp_code(analysis, source_path, options):
    """Assemble the ExtendScript that runs LOOKFX.buildComp in AE.

    The engine source is embedded and eval'd directly: under DoScript,
    $.fileName does not point at the repo, so the engine cannot be located
    from inside After Effects. look_fx.jsx stays the single source of truth.
    """
    engine_source = ENGINE_PATH.read_text(encoding="utf-8")
    return (
        'eval(%s);\n'
        'var LOOK_ANALYSIS = %s;\n'
        'var LOOK_SRC = %s;\n'
        'var LOOK_OPTS = %s;\n'
        'return $.global.LOOKFX.buildComp(LOOK_ANALYSIS, LOOK_SRC, LOOK_OPTS);\n'
    ) % (
        _json_literal(engine_source),
        _json_literal(analysis),
        _json_literal(source_path),
        _json_literal(options),
    )


def build_comp(analysis, source_path, options, timeout=120):
    """Build the comp in AE and return the runner response dict."""
    return run_jsx(build_comp_code(analysis, source_path, options), timeout=timeout)
