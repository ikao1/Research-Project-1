/* ae_mcp_bridge.jsx
 *
 * After Effects side of the opencode MCP bridge.
 *
 * Install this file in:
 *   ~/Library/Application Support/Adobe/After Effects/<version>/Scripts/Startup/
 * or run it once with File > Scripts > Run Script File...
 *
 * It polls a file mailbox, evaluates the ExtendScript it receives, and writes a
 * JSON response. The mailbox lives at:
 *   ~/Library/Application Support/AE-MCP-Bridge/
 * and can be overridden with the AE_MCP_BRIDGE_DIR environment variable.
 */

(function () {
    if ($.global.__AE_MCP_STARTED) {
        return;
    }
    $.global.__AE_MCP_STARTED = true;

    var VERSION = "0.1.0";

    var override = null;
    try {
        override = $.getenv("AE_MCP_BRIDGE_DIR");
    } catch (eOverride) {
        override = null;
    }

    var BRIDGE = override ? String(override) : (Folder.userData.fsName + "/AE-MCP-Bridge");
    var INBOX = BRIDGE + "/inbox";
    var OUTBOX = BRIDGE + "/outbox";
    var STATUS_PATH = BRIDGE + "/status.json";
    var LOG_PATH = BRIDGE + "/bridge.log";

    var currentLogs = null;
    var lastHeartbeat = 0;

    function ensureFolder(path) {
        var folder = new Folder(path);
        if (!folder.exists) {
            folder.create();
        }
        return folder;
    }

    function quote(value) {
        var text = String(value);
        var out = '"';
        for (var i = 0; i < text.length; i++) {
            var ch = text.charAt(i);
            var code = text.charCodeAt(i);
            if (ch === '"') {
                out += '\\"';
            } else if (ch === "\\") {
                out += "\\\\";
            } else if (ch === "\n") {
                out += "\\n";
            } else if (ch === "\r") {
                out += "\\r";
            } else if (ch === "\t") {
                out += "\\t";
            } else if (code < 32) {
                out += "\\u" + ("0000" + code.toString(16)).slice(-4);
            } else {
                out += ch;
            }
        }
        return out + '"';
    }

    function stringify(value, depth, seen) {
        depth = depth || 0;
        if (depth > 20) {
            return '"<max depth>"';
        }
        if (value === null) {
            return "null";
        }

        var kind = typeof value;
        if (kind === "undefined") {
            return "null";
        }
        if (kind === "number") {
            return isFinite(value) ? String(value) : "null";
        }
        if (kind === "boolean") {
            return value ? "true" : "false";
        }
        if (kind === "string") {
            return quote(value);
        }
        if (kind === "function") {
            return "null";
        }

        seen = seen || [];
        for (var s = 0; s < seen.length; s++) {
            if (seen[s] === value) {
                return '"<cycle>"';
            }
        }
        seen.push(value);

        var parts = [];
        if (value instanceof Array) {
            for (var i = 0; i < value.length; i++) {
                parts.push(stringify(value[i], depth + 1, seen));
            }
            seen.pop();
            return "[" + parts.join(",") + "]";
        }

        var keys = [];
        try {
            for (var key in value) {
                var own = true;
                try {
                    own = value.hasOwnProperty ? value.hasOwnProperty(key) : true;
                } catch (eOwn) {
                    own = true;
                }
                if (own) {
                    keys.push(key);
                }
                if (keys.length > 500) {
                    break;
                }
            }
        } catch (eKeys) {
            seen.pop();
            return quote(String(value));
        }

        for (var k = 0; k < keys.length; k++) {
            var name = keys[k];
            var child;
            try {
                child = value[name];
            } catch (eChild) {
                child = "<unreadable>";
            }
            parts.push(quote(String(name)) + ":" + stringify(child, depth + 1, seen));
        }
        seen.pop();
        return "{" + parts.join(",") + "}";
    }

    function appendLog(line) {
        try {
            var file = new File(LOG_PATH);
            if (file.open("a")) {
                file.encoding = "UTF-8";
                file.writeln((new Date()).toString() + " | " + line);
                file.close();
            }
        } catch (eLog) {
        }
    }

    function aeLog(message) {
        var line = String(message);
        if (currentLogs !== null) {
            currentLogs.push(line);
        } else {
            appendLog(line);
        }
    }

    function readText(path) {
        var file = new File(path);
        if (!file.exists) {
            return null;
        }
        if (!file.open("r")) {
            return null;
        }
        file.encoding = "UTF-8";
        var text = file.read();
        file.close();
        return text;
    }

    function writeTextAtomic(path, text) {
        var tmpPath = path + ".tmp";
        var file = new File(tmpPath);
        if (!file.open("w")) {
            return false;
        }
        file.encoding = "UTF-8";
        file.write(text);
        file.close();

        var target = new File(path);
        if (target.exists) {
            try {
                target.remove();
            } catch (eRemove) {
            }
        }
        return file.rename(path);
    }

    function writeJson(path, value) {
        var text;
        try {
            text = stringify(value);
        } catch (eStringify) {
            text = '{"ok":false,"error":"result serialization failed"}';
        }
        return writeTextAtomic(path, text);
    }

    function heartbeat(force) {
        var now = (new Date()).getTime();
        if (!force && (now - lastHeartbeat) < 2000) {
            return;
        }
        lastHeartbeat = now;

        var info = {
            alive: true,
            bridge: "ae_mcp",
            bridge_version: VERSION,
            ae_version: null,
            project_name: null,
            project_path: null,
            num_items: 0,
            active_comp: null,
            ts: now
        };

        try {
            info.ae_version = String(app.version);
        } catch (eVersion) {
        }

        try {
            var project = app.project;
            if (project) {
                info.num_items = project.numItems;
                if (project.file) {
                    info.project_name = project.file.name;
                    info.project_path = project.file.fsName;
                } else {
                    info.project_name = "Untitled";
                }
                var active = project.activeItem;
                if (active && active instanceof CompItem) {
                    info.active_comp = active.name;
                }
            }
        } catch (eProject) {
        }

        writeJson(STATUS_PATH, info);
    }

    function processRequest(file) {
        var text = readText(file.fsName);
        if (!text) {
            return;
        }

        var request = null;
        try {
            request = eval("(" + text + ")");
        } catch (eParse) {
            request = null;
        }

        if (!request || !request.id) {
            try {
                file.remove();
            } catch (eRemoveBad) {
            }
            return;
        }

        try {
            file.remove();
        } catch (eRemove) {
        }

        var response = {
            id: request.id,
            ok: false,
            result: null,
            error: null,
            logs: "",
            ts: (new Date()).getTime()
        };

        if (typeof request.code !== "string") {
            response.error = "Request does not contain a string 'code' field";
            writeJson(OUTBOX + "/" + request.id + ".json", response);
            return;
        }

        currentLogs = [];
        var originalWriteln = null;
        try {
            originalWriteln = $.writeln;
            $.writeln = function (message) {
                aeLog(message);
            };
        } catch (eWriteln) {
        }

        try {
            var value = eval("(function(){\n" + request.code + "\n})()");
            response.ok = true;
            response.result = (typeof value === "undefined") ? null : value;
        } catch (err) {
            response.ok = false;
            response.error = String(err);
            try {
                if (err.line) {
                    response.error += " (line " + err.line + ")";
                }
            } catch (eLine) {
            }
        }

        try {
            if (originalWriteln) {
                $.writeln = originalWriteln;
            }
        } catch (eRestore) {
        }

        try {
            response.logs = currentLogs.join("\n");
        } catch (eLogs) {
            response.logs = "";
        }
        currentLogs = null;

        writeJson(OUTBOX + "/" + request.id + ".json", response);
    }

    function poll() {
        try {
            var inbox = new Folder(INBOX);
            if (inbox.exists) {
                var files = inbox.getFiles("*.json");
                var names = [];
                var lookup = {};
                for (var i = 0; i < files.length; i++) {
                    names.push(files[i].name);
                    lookup[files[i].name] = files[i];
                }
                names.sort();

                var count = names.length < 10 ? names.length : 10;
                for (var n = 0; n < count; n++) {
                    processRequest(lookup[names[n]]);
                }
            }
        } catch (ePoll) {
            appendLog("poll error: " + ePoll);
        }

        heartbeat(false);
    }

    ensureFolder(BRIDGE);
    ensureFolder(INBOX);
    ensureFolder(OUTBOX);

    $.global.aeLog = aeLog;
    $.global.__aeMcpPoll = poll;

    heartbeat(true);
    appendLog("bridge started (v" + VERSION + ") at " + BRIDGE);

    try {
        app.scheduleTask("__aeMcpPoll()", 200, true);
    } catch (eSchedule) {
        appendLog("scheduleTask failed: " + eSchedule);
    }
})();
