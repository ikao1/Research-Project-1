# After Effects MCP Bridge

Bridges a live Adobe After Effects session to an MCP client such as opencode, so
an AI can inspect the project, run ExtendScript, create comps, import footage,
and export frames.

## How it works

On macOS the server sends ExtendScript to the already-open After Effects instance
with AppleScript's `DoScript` command:

```
opencode  ──stdio──  mcp_server.py
                          │ builds a request + runner JSX
                          ▼
              ae_plugin/ae_mcp_runner.jsx
                          │ osascript -> DoScript
                          ▼
              running After Effects (ExtendScript)
                          │ executes the code, writes JSON
                          ▼
        ~/Library/Application Support/AE-MCP-Bridge/doscript/<id>.json
                          │ read by mcp_server.py
                          ▼
                     tool response
```

The runner executes the requested code as a function body, captures
`$.writeln()` / `aeLog()` output, serializes the result or error, and writes a
JSON response. No After Effects startup script or background polling is required.

A file-mailbox transport remains available for the fallback path
(`AE_MCP_TRANSPORT=mailbox`). It uses `ae_plugin/ae_mcp_bridge.jsx` and a Startup
folder copy; it is not used by default on macOS.

## Requirements

- macOS with After Effects installed (tested with After Effects 2026 / 26.5).
- After Effects must be running and allowed to receive AppleScript commands.
- In After Effects, enable **Preferences > Scripting & Expressions > Allow
  Scripts to Write Files and Access Network** (the runner writes its response to
  disk).

## Setup

1. Open After Effects.
2. Enable the scripting preference above.
3. Verify the bridge:

   ```sh
   python3 "/Users/ikao1/Desktop/Research Project 1/ae_mcp/install.py" --status
   ```

   A successful result looks like:

   ```
   Transport: DoScript (macOS; no startup script required)
   Live probe: OK
   {
     "alive": true,
     "ae_version": "26.5x89",
     ...
   }
   ```

4. Restart opencode so it loads the MCP server.

No AE startup script is needed. `install.py` only prepares the fallback mailbox
and can optionally install the legacy startup script with `--with-startup`.

## opencode configuration

This server is registered in `~/.config/opencode/opencode.jsonc`:

```jsonc
"aftereffects": {
  "type": "local",
  "command": [
    "python3",
    "/Users/ikao1/Desktop/Research Project 1/ae_mcp/mcp_server.py"
  ],
  "environment": {
    "AE_MCP_BRIDGE_DIR": "/Users/ikao1/Library/Application Support/AE-MCP-Bridge"
  },
  "timeout": 300000,
  "enabled": true
}
```

After editing the config, quit and restart opencode.

## Tools

| Tool | What it does |
| --- | --- |
| `aftereffects_status` | Check the live DoScript connection, AE version, project, active comp |
| `aftereffects_run` | Execute arbitrary ExtendScript/JSX and return its value |
| `aftereffects_project_info` | Project name, path, item count, comps |
| `aftereffects_list_comps` | Comps with size, duration, fps, layer count |
| `aftereffects_create_comp` | Create a comp |
| `aftereffects_save_project` | Save in place or to a new path |
| `aftereffects_import_footage` | Import media, optionally add to a comp |
| `aftereffects_export_frame` | Render one frame to PNG |

`aftereffects_run` is the workhorse. The code is executed as a function body, so
use `return` to send a value back. `$.writeln()` and the global `aeLog()` are
captured and returned under `--- logs ---`.

### Example: build an editable adjustment-layer comp

```js
var comp = app.project.items.addComp("Look", 1920, 1080, 1, 5, 30);
comp.openInViewer();

var grade = comp.layers.addSolid([1, 1, 1], "Color Grade", 1920, 1080, 1);
grade.adjustmentLayer = true;
var curves = grade.Effects.addProperty("ADBE Curves");
var hsl = grade.Effects.addProperty("ADBE Hue Saturation");

var grain = comp.layers.addSolid([1, 1, 1], "Grain", 1920, 1080, 1);
grain.adjustmentLayer = true;
var noise = grain.Effects.addProperty("ADBE Noise");

return {
  comp: comp.name,
  layers: [grade.name, grain.name]
};
```

## Troubleshooting

- **"bridge is NOT reachable"**: After Effects must be running. Check with
  `python3 ae_mcp/install.py --status`.
- **AppleScript permission error**: allow your terminal (or opencode) to control
  After Effects in **System Settings > Privacy & Security > Automation**.
- **"did not write a response"**: enable **Allow Scripts to Write Files and
  Access Network** in After Effects' Scripting preferences.
- **Modal dialog / call hangs**: After Effects blocks while a script runs. Close
  any modal dialogs in AE, then retry.
- **First call after launch is slow**: wait for AE to finish starting, then retry.
- **Scripts take long / time out**: raise `timeout_seconds` (max 290).
- **Mailbox fallback**: set `AE_MCP_TRANSPORT=mailbox`, install with
  `python3 ae_mcp/install.py --with-startup`, and restart After Effects. The
  DoScript transport is more reliable on macOS.

## Notes and limits

- DoScript calls are synchronous and serialized; After Effects' UI blocks while a
  script runs.
- ExtendScript is ES3: no native `JSON`, `Array.map`, `Object.keys`, `let`, or
  arrow functions. The runner provides JSON serialization for return values.
- Return values are serialized up to a depth of 20 and 500 keys per object.
- `var` declarations inside `run` do not persist between calls. Use
  `$.global.name = value` for state that must survive.
- This grants an MCP client arbitrary script execution in After Effects. Only
  enable it on a machine you control and with a client you trust.
