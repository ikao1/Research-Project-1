/* ae_mcp_runner.jsx
 *
 * Synchronous After Effects runner used by mcp_server.py on macOS.
 *
 * mcp_server.py prepends three globals before this file:
 *   __AE_MCP_ID        request id string
 *   __AE_MCP_CODE      ExtendScript source to evaluate as a function body
 *   __AE_MCP_RESPONSE  absolute path for the JSON response
 *
 * The runner executes the code, serializes the result/error/logs, and writes a
 * JSON response that the Python process reads back.
 */

(function () {
    var requestId = __AE_MCP_ID;
    var userCode = __AE_MCP_CODE;
    var responsePath = __AE_MCP_RESPONSE;

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

    var response = {
        id: requestId,
        ok: false,
        result: null,
        error: null,
        logs: "",
        ts: (new Date()).getTime()
    };
    var logs = [];
    var oldWriteln = null;
    var oldAeLog = null;

    try {
        oldWriteln = $.writeln;
        $.writeln = function (message) {
            logs.push(String(message));
        };
    } catch (eWriteln) {
    }

    try {
        oldAeLog = $.global.aeLog;
        $.global.aeLog = function (message) {
            logs.push(String(message));
        };
    } catch (eAeLog) {
    }

    try {
        var value = eval("(function(){\n" + userCode + "\n})()");
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
        if (oldWriteln) {
            $.writeln = oldWriteln;
        }
    } catch (eRestoreWriteln) {
    }

    try {
        $.global.aeLog = oldAeLog;
    } catch (eRestoreAeLog) {
    }

    try {
        response.logs = logs.join("\n");
    } catch (eLogs) {
        response.logs = "";
    }

    var text;
    try {
        text = stringify(response);
    } catch (eStringify) {
        text = '{"id":"' + requestId + '","ok":false,"result":null,'
            + '"error":"response serialization failed","logs":"","ts":0}';
    }

    var file = new File(responsePath);
    if (file.open("w")) {
        file.encoding = "UTF-8";
        file.write(text);
        file.close();
    }
})();
