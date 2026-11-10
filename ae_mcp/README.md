# After Effects MCP Bridge

Bridges a live Adobe After Effects session to an MCP client such as opencode, so
an AI can inspect the project, run ExtendScript, create comps, import footage,
and export frames.

## How it works

After Effects' scripting engine cannot open a TCP server, so the bridge uses a
local file mailbox instead of a socket:

```
opencode  ──stdio──  mcp_server.py
                          │ writes request JSON
                          ▼
        ~/Library/Application Support/AE-MCP-Bridge/inbox/
                          │ polled every 200 ms by
                          ▼
        ae_mcp_bridge.jsx  (extendscript inside After Effects)
                          │ evaluates the JSX, writes result
                          ▼
                .../AE-MCP-Bridge/outbox/<id>.json
                          │ read by mcp_server.py
                          ▼
                     tool response
```

Files are written atomically (`.tmp` then rename), so neither side ever reads a
partial message. The mailbox is local to your user account.

## Install

```sh
python3 "/Users/ikao1/Desktop/Research Project 1/ae_mcp/install.py"
```

This copies `ae_plugin/ae_mcp_bridge.jsx` into the user Startup folder for every
detected After Effects version and creates the mailbox directories.

Then:

1. Enable **Preferences > Scripting & Expressions > Allow Scripts to Write Files
   and Access Network** in After Effects.
2. Quit and reopen After Effects (or run the plugin once with
   **File > Scripts > Run Script File...**).
3. Restart opencode so it loads the MCP server.

Check the installation without launching After Effects:

```sh
python3 "/Users/ikao1/Desktop/Research Project 1/ae_mcp/install.py" --status
```

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
| `aftereffects_status` | Check the heartbeat, AE version, project, active comp |
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
var hsl = grade.Effects.addProperty("ADBE HUE SATURATION");

var grain = comp.layers.addSolid([1, 1, 1], "Grain", 1920, 1080, 1);
grain.adjustmentLayer = true;
var noise = grain.Effects.addProperty("ADBE Noise");

return {
  comp: comp.name,
  layers: [grade.name, grain.name]
};
```

## Troubleshooting

- **"bridge is NOT reachable"**: After Effects must be running, the startup
  script must be installed, and the bridge must have started. Run
  `install.py --status` to see the last heartbeat.
- **No heartbeat after installing**: quit and reopen After Effects. If it still
  fails, run the plugin manually from **File > Scripts > Run Script File...**.
- **File permission errors**: enable **Allow Scripts to Write Files and Access
  Network** in After Effects' Scripting preferences.
- **Check the AE-side log**: `~/Library/Application Support/AE-MCP-Bridge/bridge.log`.
- **Scripts take long / time out**: After Effects blocks its UI while a script
  runs; raise `timeout_seconds` (max 290).

## Notes and limits

- Polling adds up to ~200 ms of latency per call.
- ExtendScript is ES3: no native `JSON`, `Array.map`, `Object.keys`, `let`, or
  arrow functions. The bridge provides JSON serialization for return values.
- Return values are serialized up to a depth of 20 and 500 keys per object.
- `var` declarations inside `run` do not persist between calls. Use
  `$.global.name = value` for state that must survive.
- The mailbox is not encrypted. Do not expose it to other users or sync it.
- This grants an MCP client arbitrary script execution in After Effects. Only
  enable it on a machine you control and with a client you trust.
