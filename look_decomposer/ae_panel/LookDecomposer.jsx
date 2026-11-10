/*  Look Decomposer - After Effects panel.

    Four tabs:
      1. Upload   - A: a reference look (a still or video) is analyzed.
                    B: footage (pictures or videos) is added to the composition and
                       the reference look is applied to it at once.
      2. Adjust   - the look on the working footage: strength and one slider per part.
      3. Grade    - Lumetri color controls on the working footage.
      4. Regions  - auto masks (subject, tones, colors) and hue/value/blend regions.

    The analysis runs in Python (look_decomposer/analyzer.py). Effects come from
    ae/look_fx.jsx. Each footage layer keeps its own look and grade in its layer
    comment, so the settings stay with the layer.

    Loaded by the loader written by look_decomposer/install_panel.py, which calls
    this function with (thisObj, LD_ROOT, LD_PYTHON).
    ExtendScript (ES3) and ASCII only.
*/
(function (thisObj, LD_ROOT, LD_PYTHON) {

    var PANEL_TITLE = "Look Decomposer";
    var PANEL_VERSION = 16;   // bump when the panel changes; older windows are not reused
    var ENGINE_FILE = new File(LD_ROOT + "/ae/look_fx.jsx");
    var REPO_ROOT = new Folder(LD_ROOT).parent.fsName;
    var TEMP_DIR = new Folder(Folder.temp.fsName + "/LookDecomposer");
    var IMAGE_EXTS = ["png", "jpg", "jpeg", "tif", "tiff", "bmp"];
    var VIDEO_EXTS = ["mov", "mp4", "m4v", "avi", "mxf", "mpg", "mpeg", "webm"];
    var LOOK_MARKER = "LOOK_DECOMPOSER_V2";
    var LOOK_MARKER_V1 = "LOOK_DECOMPOSER_V1";
    var REGION_MARKER = "LOOK_REGION_V1";
    var EFFECT_PREFIX = "Look: ";
    var REGION_PREFIX = "Region: ";
    var REGION_FX = "Region: hue and value";
    var HUE_SAT = "ADBE HUE SATURATION";
    var HS_CHANNEL = "ADBE HUE SATURATION-0002";
    var HS_HUE = "ADBE HUE SATURATION-0004";
    var HS_SAT = "ADBE HUE SATURATION-0005";
    var HS_VALUE = "ADBE HUE SATURATION-0006";
    var PERMISSION_HELP = "Turn on Preferences > Scripting & Expressions > " +
                          "'Allow Scripts to Write Files and Access Network'. Then press Check setup.";
    var NO_TARGET = "Upload footage in tab 1 (step B), or select a footage layer in the timeline.";
    var FONT_TITLE = ScriptUI.newFont("Arial", "BOLD", 15);
    var FONT_SECTION = ScriptUI.newFont("Arial", "BOLD", 12);
    var FONT_SUB = ScriptUI.newFont("Arial", "BOLD", 11);

    /* Hue/Saturation channel numbers, verified against After Effects 26.5. */
    var CHANNELS = [
        ["All colors", 1], ["Reds", 2], ["Yellows", 3], ["Greens", 4],
        ["Cyans", 5], ["Blues", 6], ["Magentas", 7]
    ];

    var ASPECT_ORDER = ["exposure", "levels", "white_balance", "saturation", "split_tone", "blur", "glow", "vignette", "grain"];
    var ASPECT_NAMES = {
        exposure: "Brightness",
        levels: "Contrast and fade",
        white_balance: "Warm or cool colors",
        saturation: "Color strength",
        split_tone: "Tinted shadows and highlights",
        blur: "Softness",
        glow: "Glow",
        vignette: "Dark corners",
        grain: "Film grain"
    };

    /* One slider per part of the look. key = "aspect.field" is also the override name. */
    var PARTS = [
        {key: "exposure.stops", aspect: "exposure", field: "stops", label: "Brightness", min: -3, max: 3, neutral: 0, unit: " stops"},
        {key: "levels.input_black", aspect: "levels", field: "input_black", label: "Black point", min: 0, max: 0.5, neutral: 0, unit: ""},
        {key: "levels.input_white", aspect: "levels", field: "input_white", label: "White point", min: 0.5, max: 1, neutral: 1, unit: ""},
        {key: "levels.output_black", aspect: "levels", field: "output_black", label: "Faded blacks", min: 0, max: 0.3, neutral: 0, unit: ""},
        {key: "white_balance.temperature", aspect: "white_balance", field: "temperature", label: "Warm / cool", min: -100, max: 100, neutral: 0, unit: ""},
        {key: "white_balance.tint", aspect: "white_balance", field: "tint", label: "Tint", min: -100, max: 100, neutral: 0, unit: ""},
        {key: "saturation.amount", aspect: "saturation", field: "amount", label: "Color strength", min: -100, max: 100, neutral: 0, unit: ""},
        {key: "split_tone.strength", aspect: "split_tone", field: "strength", label: "Split tone", min: 0, max: 100, neutral: 0, unit: ""},
        {key: "blur.radius_px", aspect: "blur", field: "radius_px", label: "Softness", min: 0, max: 50, neutral: 0, unit: " px"},
        {key: "glow.intensity", aspect: "glow", field: "intensity", label: "Glow", min: 0, max: 3, neutral: 0, unit: ""},
        {key: "vignette.amount", aspect: "vignette", field: "amount", label: "Dark corners", min: -5, max: 5, neutral: 0, unit: ""},
        {key: "grain.amount", aspect: "grain", field: "amount", label: "Film grain", min: 0, max: 100, neutral: 0, unit: ""}
    ];

    /* Icons next to each slider, keyed by the slider's label. The PNGs are drawn by
       look_decomposer/tools/make_icons.py. The tip is shown when the cursor rests on
       the icon or the label. */
    var ICON_DIR = LD_ROOT + "/ae_panel/icons";
    var ICON_INFO = {
        "Brightness": {icon: "sun", tip: "Brightness: makes the whole picture lighter or darker."},
        "Black point": {icon: "black_point", tip: "Black point: the level that counts as black. Raise it to darken the shadows."},
        "White point": {icon: "white_point", tip: "White point: the level that counts as white. Lower it to brighten the highlights."},
        "Faded blacks": {icon: "faded_blacks", tip: "Faded blacks: lifts the blacks to grey, for a faded film look."},
        "Warm / cool": {icon: "thermometer", tip: "Warm / cool: shifts the picture toward orange (warm) or blue (cool)."},
        "Tint": {icon: "tint", tip: "Tint: shifts the picture toward green or magenta."},
        "Color strength": {icon: "drop", tip: "Color strength: makes the colors more or less vivid."},
        "Split tone": {icon: "split_tone", tip: "Split tone: gives the shadows and highlights their own colors."},
        "Softness": {icon: "blur", tip: "Softness: blurs the picture slightly."},
        "Glow": {icon: "glow", tip: "Glow: makes bright areas bleed light into their surroundings."},
        "Dark corners": {icon: "vignette", tip: "Dark corners: darkens (or brightens) the edges of the frame."},
        "Film grain": {icon: "grain", tip: "Film grain: adds fine noise, like old film."},
        "Exposure": {icon: "sun", tip: "Exposure: brightens or darkens the footage."},
        "Contrast": {icon: "contrast", tip: "Contrast: pushes the darks darker and the lights lighter."},
        "Highlights": {icon: "highlights", tip: "Highlights: adjusts only the bright areas."},
        "Shadows": {icon: "shadows", tip: "Shadows: adjusts only the dark areas."},
        "Whites": {icon: "whites", tip: "Whites: adjusts the very brightest level."},
        "Blacks": {icon: "blacks", tip: "Blacks: adjusts the very darkest level."},
        "Saturation": {icon: "drop", tip: "Saturation: color strength for the whole picture (100% = unchanged)."},
        "Vibrance": {icon: "vibrance", tip: "Vibrance: boosts the muted colors more than the vivid ones."},
        "Sharpen": {icon: "sharpen", tip: "Sharpen: makes edges crisper."},
        "Mix": {icon: "mix", tip: "Mix: blends the grade with the original (100% = full grade)."},
        "Strength": {icon: "gauge", tip: "Strength: how strongly the whole look is applied."},
        "Area size": {icon: "area", tip: "Area size: how big the selected area is."},
        "Edge softness": {icon: "edge_soft", tip: "Edge softness: how gradually the edge of the area fades out."},
        "Move left/right": {icon: "move_h", tip: "Move left/right: slides the area sideways."},
        "Move up/down": {icon: "move_v", tip: "Move up/down: slides the area up or down."},
        "Hue shift": {icon: "hue_shift", tip: "Hue shift: turns the colors of the region around the color wheel."},
        "Value": {icon: "value_half", tip: "Value: brightens or darkens the colors in the region."},
        "Opacity": {icon: "opacity", tip: "Opacity: how strongly the region is applied (0% = invisible)."},
        "Grow / shrink": {icon: "grow", tip: "Grow / shrink: expands or shrinks the selected area."}
    };

    /* Colors used for a split tone when the look has none yet. */
    var SPLIT_DEFAULTS = {shadows_hex: "#1b2c4a", highlights_hex: "#ffd9a8"};

    /* Lumetri Color parameters (Basic Correction and Creative), verified in AE 26.5.
       Mix is the effect's opacity. */
    var GRADE_CONTROLS = [
        {key: "exposure", label: "Exposure", min: -5, max: 5, neutral: 0, prop: "ADBE Lumetri-0011", unit: " stops"},
        {key: "contrast", label: "Contrast", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0012", unit: ""},
        {key: "highlights", label: "Highlights", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0013", unit: ""},
        {key: "shadows", label: "Shadows", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0014", unit: ""},
        {key: "whites", label: "Whites", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0015", unit: ""},
        {key: "blacks", label: "Blacks", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0016", unit: ""},
        {key: "saturation", label: "Saturation", min: 0, max: 200, neutral: 100, prop: "ADBE Lumetri-0020", unit: "%"},
        {key: "vibrance", label: "Vibrance", min: -100, max: 100, neutral: 0, prop: "ADBE Lumetri-0030", unit: ""},
        {key: "sharpen", label: "Sharpen", min: 0, max: 100, neutral: 0, prop: "ADBE Lumetri-0029", unit: ""},
        {key: "mix", label: "Mix", min: 0, max: 100, neutral: 100, prop: null, unit: "%"}
    ];

    /* Blend modes for regions: [label, BlendingMode name]. */
    var BLEND_MODES = [
        ["Normal", "NORMAL"], ["Multiply", "MULTIPLY"], ["Screen", "SCREEN"], ["Overlay", "OVERLAY"],
        ["Soft light", "SOFT_LIGHT"], ["Hard light", "HARD_LIGHT"], ["Color dodge", "COLOR_DODGE"],
        ["Color burn", "COLOR_BURN"], ["Lighten", "LIGHTEN"], ["Darken", "DARKEN"],
        ["Difference", "DIFFERENCE"], ["Hue", "HUE"], ["Saturation", "SATURATION"],
        ["Color", "COLOR"], ["Luminosity", "LUMINOSITY"], ["Add", "ADD"]
    ];

    /* Auto mask modes: [label, automask.py mode]. */
    var AUTO_MODES = [
        ["Subject (objects and people)", "subject"],
        ["People (photos only)", "people"],
        ["Highlights (bright areas)", "highlights"],
        ["Midtones", "midtones"],
        ["Shadows (dark areas)", "shadows"],
        ["Color range (uses Colors)", "color"]
    ];
    /* Hue (degrees) for each Colors choice, used by the color range mask. */
    var HUE_FOR_CHANNEL = {2: 0, 3: 60, 4: 120, 5: 180, 6: 240, 7: 300};
    var MATTE_DIR = new Folder(Folder.userData.fsName + "/LookDecomposer/Mattes");

    /* Session state. Layers are never held as objects here: After Effects throws an
       error that try/catch cannot catch when a removed layer is touched. Instead the
       panel keeps string IDs, stored in each layer's comment, and looks layers up.
       reference  : {name, look, confidence, text, summary} from the last reference upload
       workToken  : ID of the footage the sliders act on (last used or uploaded)
       regionTokens: IDs of the regions listed in tab 4, in list order */
    var S = {
        reference: null,
        workToken: null,
        regionTokens: [],
        loadingRegion: false
    };
    var ui = {};

    /* ------------------------------------------------------------ helpers */

    function safe(fn) {
        return function () {
            try {
                fn();
            } catch (e) {
                setStatus(e && e.message ? e.message : String(e));
            }
        };
    }

    function setStatus(text) {
        if (ui.status) { ui.status.text = text; }
        try { if (ui.win) { ui.win.update(); } } catch (e) { }
    }

    function trim(s) {
        return String(s).replace(/^\s+|\s+$/g, "");
    }

    function shq(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function stem(path) {
        return String(path).split("/").pop().replace(/\.[^.]*$/, "");
    }

    function extOf(path) {
        return String(path).split(".").pop().toLowerCase();
    }

    function inList(list, value) {
        for (var i = 0; i < list.length; i++) {
            if (list[i] === value) { return true; }
        }
        return false;
    }

    function tempPath(label, ext) {
        if (!TEMP_DIR.exists) { TEMP_DIR.create(); }
        return TEMP_DIR.fsName + "/" + label + "_" + new Date().getTime() + ext;
    }

    function readText(path) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (!f.open("r")) { throw new Error("Could not open " + path); }
        var text = f.read();
        f.close();
        return text;
    }

    /* This After Effects build does not provide JSON. Our data is plain
       numbers, strings, arrays and objects, so evaluating it is safe. */
    function parseJSON(text) {
        return eval("(" + text + ")");
    }

    /* Writes a value as JSON text (used for layer comments). */
    function jsonText(v) {
        if (v === null || v === undefined) { return "null"; }
        var t = typeof v;
        if (t === "number") { return isFinite(v) ? String(v) : "0"; }
        if (t === "boolean") { return v ? "true" : "false"; }
        if (t === "string") {
            return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r?\n/g, "\\n") + '"';
        }
        if (v instanceof Array) {
            var items = [];
            for (var i = 0; i < v.length; i++) { items.push(jsonText(v[i])); }
            return "[" + items.join(",") + "]";
        }
        var parts = [];
        for (var k in v) {
            if (v.hasOwnProperty(k)) { parts.push(jsonText(k) + ":" + jsonText(v[k])); }
        }
        return "{" + parts.join(",") + "}";
    }

    function fmt(v) {
        var n = Number(v);
        if (isNaN(n)) { return ""; }
        var a = Math.abs(n);
        if (a >= 100) { return n.toFixed(0); }
        if (a >= 10) { return n.toFixed(1); }
        return n.toFixed(2);
    }

    function signed(v) {
        var n = Math.round(Number(v));
        return (n > 0 ? "+" : "") + n;
    }

    function shell(cmd) {
        return String(system.callSystem(cmd));
    }

    function runPython(moduleName, args) {
        var errPath = tempPath("error", ".txt");
        var cmd = "cd " + shq(REPO_ROOT) + " && " + shq(LD_PYTHON) + " -m " + moduleName +
                  " " + args + " > /dev/null 2> " + shq(errPath) + "; echo $?";
        var code = parseInt(trim(shell(cmd)), 10);
        var err = new File(errPath).exists ? trim(readText(errPath)) : "";
        return {ok: code === 0, code: code, error: err};
    }

    /* Returns "" when ready, otherwise one plain-language problem. */
    function setupProblem() {
        if (!ENGINE_FILE.exists) {
            return "The Look engine file is missing: " + ENGINE_FILE.fsName;
        }
        if (!new File(LD_PYTHON).exists) {
            return "Python was not found at " + LD_PYTHON + ". Re-run install_panel.py.";
        }
        try {
            var probe = trim(shell(shq(LD_PYTHON) + " -c \"import PIL\" > /dev/null 2>&1; echo $?"));
            if (probe !== "0") {
                return "This Python is missing Pillow. In Terminal run: " +
                       shq(LD_PYTHON) + " -m pip install pillow";
            }
        } catch (e) {
            return PERMISSION_HELP;
        }
        return "";
    }

    function loadEngine() {
        eval(readText(ENGINE_FILE.fsName));
        return $.global.LOOKFX;
    }

    function hasSection(sec) {
        if (!sec || typeof sec !== "object") { return false; }
        for (var k in sec) {
            if (sec.hasOwnProperty(k) && k !== "confidence") { return true; }
        }
        return false;
    }

    function activeComp() {
        var c = app.project.activeItem;
        return (c instanceof CompItem) ? c : null;
    }

    function makeToken() {
        return "ld" + new Date().getTime() + "x" + Math.floor(Math.random() * 1000000);
    }

    /* Finds a layer whose comment carries this ID. Scans the live project each time,
       so it never returns a layer that has been removed. */
    function findLayerByToken(token) {
        if (!token) { return null; }
        var needle = '"id":"' + token + '"';
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (!(it instanceof CompItem)) { continue; }
            for (var j = 1; j <= it.numLayers; j++) {
                var c = String(it.layer(j).comment || "");
                if (c.indexOf(LOOK_MARKER) === 0 && c.indexOf(needle) >= 0) {
                    return it.layer(j);
                }
            }
        }
        return null;
    }

    /* ------------------------------------------------------ footage input */

    function isFootageLayer(layer) {
        return (layer instanceof AVLayer) && !layer.adjustmentLayer &&
               !layer.isTrackMatte && !!layer.source;
    }

    /* The footage the controls act on: the selected footage layer if there is one,
       otherwise the last footage used or uploaded. */
    function targetLayer() {
        var comp = activeComp();
        if (comp) {
            var sel = comp.selectedLayers;
            for (var i = 0; i < sel.length; i++) {
                if (isFootageLayer(sel[i])) {
                    var tok = tokenIfAny(sel[i]);
                    if (tok) { S.workToken = tok; }
                    return sel[i];
                }
            }
        }
        var found = findLayerByToken(S.workToken);
        if (found && isFootageLayer(found)) { return found; }
        S.workToken = null;
        return null;
    }

    /* The footage ID if the layer already has a look state, else null. */
    function tokenIfAny(layer) {
        var st = loadLookState(layer);
        return st && st.id ? st.id : null;
    }

    /* Gives a footage layer its ID (saving its state) and makes it the working footage. */
    function tokenOf(layer) {
        var st = ensureState(layer);
        var c = String(layer.comment || "");
        if (c.indexOf(LOOK_MARKER) !== 0 || c.indexOf('"id":"' + st.id + '"') < 0) {
            writeLook(layer, st);
        }
        S.workToken = st.id;
        return st.id;
    }

    /* Imports a file as a new footage item every time (import never reuses items). */
    function importFootage(file) {
        var item = app.project.importFile(new ImportOptions(file));
        var comp = activeComp();
        if (!comp) {
            var dur = item.duration > 0 ? item.duration : 5;
            var fps = item.frameRate > 0 ? item.frameRate : 30;
            comp = app.project.items.addComp(stem(file.fsName), item.width, item.height,
                                             item.pixelAspect, dur, fps);
        }
        var layer = comp.layers.add(item);
        for (var i = 1; i <= comp.numLayers; i++) { comp.layer(i).selected = false; }
        layer.selected = true;
        comp.openInViewer();
        return layer;
    }

    /* Saves the middle frame of a video as a PNG and returns its path. */
    function videoFrame(file) {
        var item = app.project.importFile(new ImportOptions(file));
        var comp = null;
        var out = tempPath("look_frame", ".png");
        try {
            var fps = item.frameRate > 0 ? item.frameRate : 30;
            comp = app.project.items.addComp("LD look frame", item.width, item.height,
                                             item.pixelAspect, item.duration, fps);
            comp.layers.add(item);
            var job = comp.saveFrameToPng(item.duration / 2, new File(out));
            if (job && typeof job.wait === "function") { job.wait(); }
        } finally {
            if (comp) { comp.remove(); }
            item.remove();
        }
        if (!new File(out).exists) { throw new Error("The video frame could not be saved."); }
        return out;
    }

    function isSolidItem(item) {
        try {
            return item.mainSource instanceof SolidSource;
        } catch (e) {
            return false;
        }
    }

    /* Renders the first frame of any item (precomp, or a format AE reads but the
       analyzer does not) through a temporary composition. */
    function renderItemFrame(item) {
        var fps = item.frameRate > 0 ? item.frameRate : 30;
        var dur = item.duration > 0 ? item.duration : 1;
        var tmp = app.project.items.addComp("LD mask source", item.width, item.height,
                                            item.pixelAspect, dur, fps);
        var out = tempPath("mask_source", ".png");
        try {
            tmp.layers.add(item);
            var job = tmp.saveFrameToPng(0, new File(out));
            if (job && typeof job.wait === "function") { job.wait(); }
        } finally {
            tmp.remove();
        }
        if (!new File(out).exists) { throw new Error("The picture could not be read from " + item.name + "."); }
        return out;
    }

    /* A still picture for a layer, whatever its source: picture, video, precomp.
       Throws a plain-language message when the layer has no picture to read. */
    function sourceFrameForMask(layer) {
        var src = layer.source;
        if (src instanceof CompItem) {
            return renderItemFrame(src);
        }
        if (src instanceof FootageItem) {
            if (isSolidItem(src)) {
                throw new Error("'" + layer.name + "' is a solid color, so it has no picture to mask. " +
                                "Use a picture, video or precomp layer.");
            }
            if (!src.file) {
                throw new Error("'" + layer.name + "' has no file. Re-link its footage in the Project panel.");
            }
            if (!src.file.exists) {
                throw new Error("The file for '" + layer.name + "' cannot be found. Re-link it in the Project panel.");
            }
            var ext = extOf(src.file.fsName);
            if (inList(IMAGE_EXTS, ext)) { return src.file.fsName; }
            if (inList(VIDEO_EXTS, ext)) { return videoFrame(src.file); }
            return renderItemFrame(src);
        }
        throw new Error("'" + layer.name + "' has no picture to mask. Use a picture, video or precomp layer.");
    }

    /* ----------------------------------------------- reference look (tab 1A) */

    function analyzeFile(file) {
        var ext = extOf(file.fsName);
        var name = stem(file.fsName);
        var imagePath;
        if (inList(IMAGE_EXTS, ext)) {
            imagePath = file.fsName;
        } else if (inList(VIDEO_EXTS, ext)) {
            setStatus("Reading the middle frame of " + name + "...");
            imagePath = videoFrame(file);
        } else {
            throw new Error("That file type is not supported. Use a picture (PNG, JPG, TIFF, BMP) or a video (MOV, MP4).");
        }
        var problem = setupProblem();
        if (problem) { throw new Error(problem); }

        setStatus("Analyzing " + name + "... a few seconds.");
        var out = tempPath("analysis", ".json");
        var r = runPython("look_decomposer.analyzer",
                          shq(imagePath) + " --name " + shq(name) + " -o " + shq(out));
        if (!r.ok) {
            throw new Error("The look could not be analyzed. " + (r.error || ("exit code " + r.code)));
        }
        var analysis = parseJSON(readText(out));
        return {name: name, look: analysis.look || {}, confidence: Number(analysis.overall_confidence)};
    }

    function summarize(look) {
        var parts = [];
        if (look.exposure) {
            var st = Number(look.exposure.stops);
            parts.push((st >= 0 ? "brighter" : "darker") + " " + Math.abs(st).toFixed(2) + " stops");
        }
        if (look.white_balance && Number(look.white_balance.temperature) !== 0) {
            parts.push(Number(look.white_balance.temperature) > 0 ? "warmer" : "cooler");
        }
        if (look.saturation) { parts.push(Number(look.saturation.amount) >= 0 ? "more color" : "less color"); }
        if (look.split_tone) { parts.push("tinted shadows and highlights"); }
        if (look.grain) { parts.push("film grain"); }
        if (look.vignette) { parts.push(Number(look.vignette.amount) < 0 ? "dark corners" : "bright corners"); }
        return parts.length ? parts.join(", ") : "no clear adjustments found";
    }

    function describeAspect(aspect, sec) {
        var v;
        switch (aspect) {
        case "exposure":
            v = Number(sec.stops);
            return (v >= 0 ? "brighter" : "darker") + " by " + Math.abs(v).toFixed(2) + " stops";
        case "levels":
            return "black point " + Number(sec.input_black).toFixed(2) + ", white point " +
                   Number(sec.input_white).toFixed(2) + ", faded blacks " + Number(sec.output_black).toFixed(2);
        case "white_balance":
            v = Number(sec.temperature);
            return signed(v) + " temperature (" + (v > 0 ? "warmer" : (v < 0 ? "cooler" : "neutral")) +
                   "), tint " + signed(sec.tint);
        case "saturation":
            v = Number(sec.amount);
            return signed(v) + (v >= 0 ? " (more color)" : " (less color)");
        case "split_tone":
            return "shadows " + sec.shadows_hex + ", highlights " + sec.highlights_hex +
                   ", strength " + Math.round(Number(sec.strength));
        case "blur":
            return Number(sec.radius_px).toFixed(1) + " px";
        case "glow":
            return "intensity " + Number(sec.intensity).toFixed(2);
        case "vignette":
            v = Number(sec.amount);
            return (v > 0 ? "+" : "") + v.toFixed(2) + (v < 0 ? " (darker edges)" : " (brighter edges)");
        case "grain":
            return Math.round(Number(sec.amount)) + (sec.monochrome === true ? " (black and white)" : " (color)");
        }
        return "";
    }

    function describeParts(look) {
        var lines = [];
        for (var i = 0; i < ASPECT_ORDER.length; i++) {
            var key = ASPECT_ORDER[i];
            if (hasSection(look[key])) {
                lines.push(ASPECT_NAMES[key] + ": " + describeAspect(key, look[key]));
            }
        }
        return lines.length ? lines.join("\n") : "No clear adjustments found. The picture looks close to neutral.";
    }

    function confidenceWord(c) {
        var n = Number(c);
        if (n >= 0.6) { return "High"; }
        if (n >= 0.4) { return "Medium"; }
        return "Low";
    }

    function uploadReference() {
        var f = File.openDialog("Choose a reference look: a still picture or a video");
        if (!f) { return; }
        setReference(f);
    }

    /* Analyzes a reference and applies it to the working footage, if there is any. */
    function setReference(file) {
        var a = analyzeFile(file);
        S.reference = {
            name: a.name,
            look: a.look,
            confidence: a.confidence,
            summary: summarize(a.look),
            text: describeParts(a.look)
        };
        ui.refLabel.text = "Reference: " + a.name;
        ui.refResult.text = S.reference.text +
            "\n\nConfidence: " + confidenceWord(a.confidence) +
            " (no original picture was given, so values are estimates).";
        var target = targetLayer();
        var msg = "Reference ready: " + a.name + " (" + S.reference.summary + ").";
        if (target) {
            applyReferenceTo(target);
            msg += "\nApplied to " + target.name + ". Adjust it in tab 2.";
        } else {
            msg += "\nIt will be applied to footage you upload in step B.";
        }
        refreshAll();
        setStatus(msg);
    }

    /* ------------------------------------------------- footage (tab 1B) */

    function uploadFootage() {
        var picked = File.openDialog("Choose footage to grade (one or more pictures or videos)", undefined, true);
        if (!picked) { return; }
        var list = (picked instanceof Array) ? picked : [picked];
        addFootageFiles(list);
    }

    /* Adds each file to the composition, applies the reference look, and makes the
       last one the working footage so the sliders act on it at once. */
    function addFootageFiles(list) {
        var added = [];
        var skipped = [];
        for (var i = 0; i < list.length; i++) {
            var f = list[i];
            var ext = extOf(f.fsName);
            if (!inList(IMAGE_EXTS, ext) && !inList(VIDEO_EXTS, ext)) {
                skipped.push(f.name);
                continue;
            }
            var layer = importFootage(f);
            if (S.reference) { applyReferenceTo(layer); } else { tokenOf(layer); }
            added.push(layer.name);
        }
        if (!added.length) {
            setStatus("No pictures or videos were added. Supported: PNG, JPG, TIFF, BMP, MOV, MP4.");
            return;
        }
        refreshAll();
        var msg = "Added " + added.join(", ") + ". Working on " + added[added.length - 1] + ".";
        msg += S.reference ? "\nReference look applied: " + S.reference.name + "."
                           : "\nNo reference look yet. Upload one in step A, or build a look with the sliders.";
        if (skipped.length) { msg += "\nSkipped: " + skipped.join(", "); }
        ui.tabs.selection = ui.tabAdjust;
        showCurrentTab();
        setStatus(msg);
    }

    /* Replaces the look on a layer with the current reference. Slider changes made
       on that layer are cleared; the grade and strength are kept. */
    function applyReferenceTo(layer) {
        if (!S.reference) { return false; }
        var st = ensureState(layer);
        st.analysis = {name: S.reference.name, look: S.reference.look};
        st.overrides = {};
        st.off = [];
        writeLook(layer, st);
        return true;
    }

    function applyReferenceNow() {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        if (!S.reference) { setStatus("Upload a reference look in tab 1 (step A) first."); return; }
        applyReferenceTo(layer);
        refreshAll();
        setStatus("Applied " + S.reference.name + " to " + layer.name + ". Slider changes on it were reset.");
    }

    /* --------------------------------------- look stored on each footage layer */

    /* Stored state: {analysis: {name, look} | null, strength: 0..1,
                      overrides: {key: value}, off: [aspect], grade: {key: value} | null} */
    function loadLookState(layer) {
        var c = String(layer.comment || "");
        var st = null;
        if (c.indexOf(LOOK_MARKER) === 0) {
            st = parseJSON(c.substring(LOOK_MARKER.length + 1));
        } else if (c.indexOf(LOOK_MARKER_V1) === 0) {
            var a = parseJSON(c.substring(LOOK_MARKER_V1.length + 1));
            st = {analysis: {name: a.name || "", look: a.look || {}}, strength: 1};
        }
        if (st) {
            if (!st.overrides) { st.overrides = {}; }
            if (!st.off) { st.off = []; }
            if (typeof st.strength !== "number") { st.strength = 1; }
        }
        return st;
    }

    function saveLookState(layer, st) {
        layer.comment = LOOK_MARKER + "\n" + jsonText(st);
    }

    /* The stored state, or a fresh one with no look yet. Every footage state has an ID. */
    function ensureState(layer) {
        var st = loadLookState(layer);
        if (!st) { st = {analysis: null, strength: 1, overrides: {}, off: []}; }
        if (!st.id) { st.id = makeToken(); }
        return st;
    }

    /* The look section for one aspect: the reference values with any slider changes
       applied on top. Returns null when the aspect has nothing to do. */
    function effectiveSection(st, aspect) {
        var base = (st && st.analysis && st.analysis.look) ? st.analysis.look[aspect] : null;
        var sec = {};
        var has = false;
        if (hasSection(base)) {
            for (var k in base) {
                if (base.hasOwnProperty(k)) { sec[k] = base[k]; }
            }
            has = true;
        }
        if (st && st.overrides) {
            for (var i = 0; i < PARTS.length; i++) {
                var p = PARTS[i];
                if (p.aspect === aspect && st.overrides.hasOwnProperty(p.key)) {
                    sec[p.field] = st.overrides[p.key];
                    has = true;
                }
            }
        }
        if (has && aspect === "split_tone") {
            if (!sec.shadows_hex) { sec.shadows_hex = SPLIT_DEFAULTS.shadows_hex; }
            if (!sec.highlights_hex) { sec.highlights_hex = SPLIT_DEFAULTS.highlights_hex; }
            if (sec.strength === undefined) { sec.strength = 0; }
        }
        return has ? sec : null;
    }

    function isOff(st, aspect) {
        for (var i = 0; i < st.off.length; i++) {
            if (st.off[i] === aspect) { return true; }
        }
        return false;
    }

    /* Scales one aspect toward its neutral value: strength 0 = none, 1 = full. */
    function scaleSection(key, sec, s) {
        var out = {};
        for (var k in sec) {
            if (sec.hasOwnProperty(k)) { out[k] = sec[k]; }
        }
        function scale(name, neutral) {
            if (typeof sec[name] === "number") {
                out[name] = neutral + (sec[name] - neutral) * s;
            }
        }
        switch (key) {
        case "exposure":
            scale("stops", 0);
            scale("gamma", 1);
            break;
        case "levels":
            scale("input_black", 0);
            scale("input_white", 1);
            scale("output_black", 0);
            scale("output_white", 1);
            scale("gamma", 1);
            break;
        case "white_balance":
            scale("temperature", 0);
            scale("tint", 0);
            break;
        case "saturation":
            scale("amount", 0);
            break;
        case "split_tone":
            scale("strength", 0);
            break;
        case "blur":
            scale("radius_px", 0);
            break;
        case "glow":
            scale("intensity", 0);
            break;
        case "vignette":
            scale("amount", 0);
            break;
        case "grain":
            scale("amount", 0);
            break;
        }
        return out;
    }

    function removeLookEffects(layer) {
        var group = layer.property("ADBE Effect Parade");
        for (var i = group.numProperties; i >= 1; i--) {
            var fx = group.property(i);
            if (fx.name.indexOf(EFFECT_PREFIX) === 0) { fx.remove(); }
        }
    }

    function gradeValueOf(g, c) {
        if (g && typeof g[c.key] === "number") { return g[c.key]; }
        return c.neutral;
    }

    /* Adds one Lumetri Color effect with the grade values. */
    function addGrade(layer, g) {
        var fx = layer.property("ADBE Effect Parade").addProperty("ADBE Lumetri");
        fx.name = EFFECT_PREFIX + "Grade";
        for (var i = 0; i < GRADE_CONTROLS.length; i++) {
            var c = GRADE_CONTROLS[i];
            if (c.prop) { fx.property(c.prop).setValue(gradeValueOf(g, c)); }
        }
        fx.property("ADBE Effect Built In Params").property("ADBE Effect Mask Opacity")
            .setValue(gradeValueOf(g, GRADE_CONTROLS[GRADE_CONTROLS.length - 1]));
    }

    /* Rebuilds every "Look: " effect on the layer from its stored state. */
    function renderLook(layer, st) {
        var LOOKFX = loadEngine();
        removeLookEffects(layer);
        var warnings = [];
        var order = LOOKFX.ORDER;
        for (var i = 0; i < order.length; i++) {
            var key = order[i][0];
            if (isOff(st, key)) { continue; }
            var sec = effectiveSection(st, key);
            if (!sec) { continue; }
            var added = LOOKFX.applyAspect(layer, key, scaleSection(key, sec, st.strength), warnings);
            for (var a = 0; a < added.length; a++) {
                added[a].name = EFFECT_PREFIX + added[a].name;
            }
        }
        if (st.grade) { addGrade(layer, st.grade); }
        return warnings;
    }

    function writeLook(layer, st) {
        app.beginUndoGroup("Look Decomposer: adjust look");
        try {
            saveLookState(layer, st);
            renderLook(layer, st);
        } finally {
            app.endUndoGroup();
        }
        if (st.id) { S.workToken = st.id; }
    }

    /* ----------------------------------------------- tab 2: adjust the look */

    function onStrength(v) {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = ensureState(layer);
        st.strength = v / 100;
        writeLook(layer, st);
    }

    function onPartChange(i, v) {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = ensureState(layer);
        st.overrides[PARTS[i].key] = Math.round(v * 1000) / 1000;
        writeLook(layer, st);
    }

    function onPartToggle(i, on) {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = ensureState(layer);
        var aspect = PARTS[i].aspect;
        var kept = [];
        for (var k = 0; k < st.off.length; k++) {
            if (st.off[k] !== aspect) { kept.push(st.off[k]); }
        }
        if (!on) { kept.push(aspect); }
        st.off = kept;
        writeLook(layer, st);
        refreshAll();
    }

    function removeLook() {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = loadLookState(layer);
        app.beginUndoGroup("Look Decomposer: remove look");
        try {
            if (st) {
                st.analysis = null;
                st.overrides = {};
                st.off = [];
                if (st.grade) {
                    saveLookState(layer, st);
                    renderLook(layer, st);
                } else {
                    removeLookEffects(layer);
                    layer.comment = "";
                }
            } else {
                removeLookEffects(layer);
            }
        } finally {
            app.endUndoGroup();
        }
        refreshAll();
        setStatus("Removed the look from " + layer.name + ". The grade in tab 3 is kept.");
    }

    /* ------------------------------------------------- tab 3: grade */

    function onGradeChange(i, v) {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = ensureState(layer);
        if (!st.grade) { st.grade = {}; }
        st.grade[GRADE_CONTROLS[i].key] = Math.round(v * 1000) / 1000;
        writeLook(layer, st);
    }

    function resetGrade() {
        var layer = targetLayer();
        if (!layer) { setStatus(NO_TARGET); return; }
        var st = ensureState(layer);
        st.grade = null;
        writeLook(layer, st);
        refreshAll();
        setStatus("Grade reset on " + layer.name + ".");
    }

    /* ------------------------------------------------- tab 4: regions */

    function channelName(channel) {
        for (var i = 0; i < CHANNELS.length; i++) {
            if (CHANNELS[i][1] === channel) { return CHANNELS[i][0]; }
        }
        return "All colors";
    }

    function regionSettingsOf(layer) {
        var c = String(layer.comment || "");
        if (c.indexOf(REGION_MARKER) !== 0) { return null; }
        return parseJSON(c.substring(REGION_MARKER.length + 1));
    }

    function saveRegion(layer, s) {
        layer.comment = REGION_MARKER + "\n" + jsonText(s);
    }

    function regionTitle(name, s) {
        return name + "  (" + channelName(s.channel) + (s.area ? ", area" : "") +
               (s.auto ? ", auto mask" : "") +
               ", hue " + signed(s.hue) + ", value " + signed(s.value) +
               ", sat " + signed(s.sat) + ")";
    }

    /* Ellipse or rectangle mask on the region layer, in composition pixels. */
    function addAreaMask(layer, s) {
        var comp = layer.containingComp;
        var W = comp.width;
        var H = comp.height;
        var cx = W / 2 + (s.x / 100) * W;
        var cy = H / 2 + (s.y / 100) * H;
        var rx = (s.size / 100) * W / 2;
        var ry = (s.size / 100) * H / 2;
        var mask = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        var shape = new Shape();
        if (s.shape === "rectangle") {
            shape.vertices = [[cx - rx, cy - ry], [cx + rx, cy - ry], [cx + rx, cy + ry], [cx - rx, cy + ry]];
            shape.inTangents = [[0, 0], [0, 0], [0, 0], [0, 0]];
            shape.outTangents = [[0, 0], [0, 0], [0, 0], [0, 0]];
        } else {
            var k = 0.5523;   // bezier handle length for a quarter circle
            shape.vertices = [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]];
            shape.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
            shape.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
        }
        shape.closed = true;
        mask.property("ADBE Mask Shape").setValue(shape);
        mask.property("ADBE Mask Feather").setValue([s.feather, s.feather]);
    }

    /* Rebuilds the region's effect, blend mode, opacity and mask from its settings. */
    function renderRegion(layer, s) {
        var fxs = layer.property("ADBE Effect Parade");
        for (var i = fxs.numProperties; i >= 1; i--) { fxs.property(i).remove(); }
        var masks = layer.property("ADBE Mask Parade");
        for (var m = masks.numProperties; m >= 1; m--) { masks.property(m).remove(); }

        var fx = fxs.addProperty(HUE_SAT);
        fx.name = REGION_FX;
        fx.property(HS_CHANNEL).setValue(s.channel);
        fx.property(HS_HUE).setValue(s.hue);
        fx.property(HS_SAT).setValue(s.sat);
        fx.property(HS_VALUE).setValue(s.value);
        layer.blendingMode = BlendingMode[s.blend || "NORMAL"];
        layer.opacity.setValue(s.opacity === undefined ? 100 : s.opacity);
        if (s.area) { addAreaMask(layer, s); }
    }

    function readRegionControls() {
        return {
            channel: CHANNELS[ui.regColor.selection.index][1],
            area: ui.regArea.value === true,
            shape: ui.regShape.selection.index === 1 ? "rectangle" : "ellipse",
            size: Math.round(ui.regSize.getValue()),
            feather: Math.round(ui.regFeather.getValue()),
            x: Math.round(ui.regX.getValue()),
            y: Math.round(ui.regY.getValue()),
            hue: Math.round(ui.regHue.getValue()),
            value: Math.round(ui.regValue.getValue()),
            sat: Math.round(ui.regSat.getValue()),
            opacity: Math.round(ui.regOpacity.getValue()),
            blend: BLEND_MODES[ui.regBlend.selection.index][1]
        };
    }

    function loadRegionControls(s) {
        var ci = 0;
        for (var k = 0; k < CHANNELS.length; k++) {
            if (CHANNELS[k][1] === s.channel) { ci = k; }
        }
        ui.regColor.selection = ci;
        ui.regArea.value = s.area === true;
        ui.regShape.selection = s.shape === "rectangle" ? 1 : 0;
        ui.regSize.setValue(s.size);
        ui.regFeather.setValue(s.feather);
        ui.regX.setValue(s.x);
        ui.regY.setValue(s.y);
        ui.regHue.setValue(s.hue);
        ui.regValue.setValue(s.value);
        ui.regSat.setValue(s.sat);
        var bi = 0;
        for (var b = 0; b < BLEND_MODES.length; b++) {
            if (BLEND_MODES[b][1] === (s.blend || "NORMAL")) { bi = b; }
        }
        ui.regBlend.selection = bi;
        ui.regOpacity.setValue(s.opacity === undefined ? 100 : s.opacity);
    }

    function updateAreaControls() {
        var on = ui.regArea.value === true;
        ui.regShape.enabled = on;
        ui.regSize.setEnabled(on);
        ui.regFeather.setEnabled(on);
        ui.regX.setEnabled(on);
        ui.regY.setEnabled(on);
    }

    /* Region ID: stored in the region's settings. Regions made before IDs existed
       are identified by their layer index instead. */
    function regionTokenOf(layer, s) {
        return (s && s.id) ? s.id : ("layer" + layer.index);
    }

    function refreshRegions() {
        var comp = activeComp();
        S.regionTokens = [];
        ui.regionList.removeAll();
        if (!comp) { return; }
        for (var i = 1; i <= comp.numLayers; i++) {
            var ly = comp.layer(i);
            var s = regionSettingsOf(ly);
            if (s) {
                S.regionTokens.push(regionTokenOf(ly, s));
                ui.regionList.add("item", regionTitle(ly.name, s));
            }
        }
    }

    function findRegionLayer(comp, token) {
        if (!comp || !token) { return null; }
        for (var i = 1; i <= comp.numLayers; i++) {
            var ly = comp.layer(i);
            var s = regionSettingsOf(ly);
            if (s && regionTokenOf(ly, s) === token) { return ly; }
        }
        return null;
    }

    function selectedRegionIndex() {
        return ui.regionList.selection ? ui.regionList.selection.index : -1;
    }

    /* The selected region as a live layer, or null if it no longer exists. */
    function selectedRegionLayer() {
        var idx = selectedRegionIndex();
        if (idx < 0 || !S.regionTokens[idx]) { return null; }
        return findRegionLayer(activeComp(), S.regionTokens[idx]);
    }

    function onRegionSelect() {
        var layer = selectedRegionLayer();
        if (!layer) { refreshRegions(); return; }
        var s = regionSettingsOf(layer);
        if (!s) { refreshRegions(); return; }
        S.loadingRegion = true;
        loadRegionControls(s);
        S.loadingRegion = false;
        updateAreaControls();
    }

    /* Any change to the region settings updates the selected region. */
    function onRegionChange() {
        if (S.loadingRegion) { return; }
        updateAreaControls();
        var idx = selectedRegionIndex();
        var layer = selectedRegionLayer();
        if (!layer) { return; }
        var s = readRegionControls();
        var previous = regionSettingsOf(layer);
        if (previous && previous.auto) { s.auto = previous.auto; }
        if (previous && previous.id) { s.id = previous.id; }
        app.beginUndoGroup("Look Decomposer: change region");
        try {
            saveRegion(layer, s);
            renderRegion(layer, s);
        } finally {
            app.endUndoGroup();
        }
        ui.regionList.items[idx].text = regionTitle(layer.name, s);
    }

    /* Selects the list row for a region ID, after the list has been rebuilt. */
    function selectRegionByToken(token) {
        for (var i = 0; i < S.regionTokens.length; i++) {
            if (S.regionTokens[i] === token) {
                ui.regionList.selection = i;
                onRegionSelect();
                return;
            }
        }
    }

    function addRegion() {
        var comp = activeComp();
        if (!comp) {
            setStatus("Open a composition first.");
            return;
        }
        var s = readRegionControls();
        s.id = makeToken();
        var label = channelName(s.channel) + (s.area ? " area" : "");
        app.beginUndoGroup("Look Decomposer: add region");
        try {
            var layer = comp.layers.addSolid([1, 1, 1], REGION_PREFIX + label,
                                             comp.width, comp.height, comp.pixelAspect, comp.duration);
            layer.adjustmentLayer = true;
            saveRegion(layer, s);
            renderRegion(layer, s);
        } finally {
            app.endUndoGroup();
        }
        refreshRegions();
        selectRegionByToken(s.id);
        setStatus("Added region: " + label + ". Change its settings to edit it.");
    }

    function removeRegion() {
        var layer = selectedRegionLayer();
        if (!layer) {
            setStatus("Select a region in the list first.");
            return;
        }
        var name = layer.name;
        var settings = regionSettingsOf(layer);
        var comp = layer.containingComp;
        app.beginUndoGroup("Look Decomposer: remove region");
        try {
            if (settings && settings.auto && settings.auto.matte) {
                var matte = findLayerByName(comp, settings.auto.matte);
                if (matte) { matte.remove(); }
            }
            layer.remove();
        } finally {
            app.endUndoGroup();
        }
        refreshRegions();
        setStatus("Removed " + name + ".");
    }

    function findLayerByName(comp, name) {
        for (var i = 1; i <= comp.numLayers; i++) {
            if (comp.layer(i).name === name) { return comp.layer(i); }
        }
        return null;
    }

    /* ------------------------------------------- auto mask (tab 4) */

    /* Makes a matte from the working footage and a region that uses it as a luma matte.
       The matte is read from the footage itself, so no selection is needed beyond the
       footage the sliders already act on. */
    function createAutoRegion() {
        var footage = targetLayer();
        if (!footage) { setStatus(NO_TARGET); return; }
        var comp = footage.containingComp;
        var mode = AUTO_MODES[ui.autoMode.selection.index][1];
        var channel = CHANNELS[ui.regColor.selection.index][1];
        if (mode === "color" && !HUE_FOR_CHANNEL[channel]) {
            setStatus("For the color range, pick a color in Colors (not All colors).");
            return;
        }
        var problem = setupProblem();
        if (problem) {
            setStatus(problem);
            return;
        }
        setStatus("Making the " + mode + " mask from " + footage.name + "... a few seconds.");

        var imagePath;
        try {
            imagePath = sourceFrameForMask(footage);
        } catch (e) {
            setStatus(e && e.message ? e.message : String(e));
            return;
        }
        if (!MATTE_DIR.exists) {
            new Folder(Folder.userData.fsName + "/LookDecomposer").create();
            MATTE_DIR.create();
        }
        var stamp = new Date().getTime();
        var matteFile = new File(MATTE_DIR.fsName + "/matte_" + mode + "_" + stamp + ".png");
        var grow = Math.round(ui.autoGrow.getValue());
        var feather = Math.round(ui.autoFeather.getValue());
        var invert = ui.autoInvert.value === true;
        var args = shq(imagePath) + " -o " + shq(matteFile.fsName) + " --mode " + mode +
                   " --grow=" + grow + " --feather " + feather + (invert ? " --invert" : "");
        if (mode === "color") {
            args += " --hue " + HUE_FOR_CHANNEL[channel] + " --hue-width 40 --min-sat 15";
        }
        var r = runPython("look_decomposer.automask", args);
        if (!r.ok) {
            setStatus("The mask could not be made.\n" + (r.error || ("exit code " + r.code)));
            return;
        }

        var matteName = "Matte " + stamp;
        var matteItem = app.project.importFile(new ImportOptions(matteFile));
        var s = readRegionControls();
        s.id = makeToken();
        s.auto = {mode: mode, grow: grow, feather: feather, invert: invert, matte: matteName};
        var region, matteLayer;
        app.beginUndoGroup("Look Decomposer: auto mask");
        try {
            region = comp.layers.addSolid([1, 1, 1], REGION_PREFIX + "auto " + mode,
                                          comp.width, comp.height, comp.pixelAspect, comp.duration);
            region.adjustmentLayer = true;
            matteLayer = comp.layers.add(matteItem);
            matteLayer.name = matteName;
            /* The matte sits where the footage sits, so it lines up with the picture. */
            matteLayer.position.setValue(footage.position.value);
            matteLayer.scale.setValue(footage.scale.value);
            matteLayer.anchorPoint.setValue(footage.anchorPoint.value);
            matteLayer.rotation.setValue(footage.rotation.value);
            region.setTrackMatte(matteLayer, TrackMatteType.LUMA);
            saveRegion(region, s);
            renderRegion(region, s);
        } finally {
            app.endUndoGroup();
        }
        refreshRegions();
        selectRegionByToken(s.id);
        /* Adding layers selects them; select the footage again so the sliders keep
           acting on it. */
        for (var li = 1; li <= comp.numLayers; li++) { comp.layer(li).selected = false; }
        footage.selected = true;
        tokenOf(footage);
        refreshAll();
        setStatus("Auto-masked region created from " + footage.name + " (" + mode + "). " +
                  "Its hue, value and blend settings now apply only inside the mask.");
        return region;
    }

    /* ------------------------------------------------------------ scrolling
       ScriptUI has no scrollable groups, and it does not clip child controls.
       So each tab's controls sit in a body group beside a scroll bar, and the rows
       are placed by hand: a row moves up or down with the scroll bar, and a row
       that is not entirely inside the body is moved out of the window, where it is
       not drawn. Rows are never re-laid out after placing, because a window layout
       pass puts every row back in its starting position. */

    var SCROLL_GAP = 6;        // space between rows (the body's spacing)
    var SCROLL_MARGIN = 8;     // space above the first row and below the last (body margins)
    var SCROLL_OFFSCREEN = -10000;
    var SCROLL_DEFAULT_H = 380;  // body height until the real panel height is known
    /* Height of everything above and below a tab's body (title, status, tab header),
       measured in the floating window. The docked panel's own height is read from
       ui.win.size; that reading was checked against the live docked panel (941 px). */
    var PANEL_CHROME = 172;
    var scrollViews = [];

    function scrollBodyOf(tab) {
        var outer = tab.add("group");
        outer.orientation = "row";
        outer.alignChildren = ["fill", "fill"];
        outer.alignment = ["fill", "fill"];
        outer.spacing = 4;
        outer.margins = 0;
        /* A floating window takes its size from its contents. Capping the height
           keeps it at a usable size and the scroll bar does the rest. A docked panel
           is sized by After Effects, so it is left alone. */
        if (!(thisObj instanceof Panel)) {
            outer.preferredSize = [340, 380];
            outer.maximumSize = [340, 380];
        }

        var body = outer.add("group");
        body.orientation = "column";
        body.alignChildren = ["fill", "top"];
        body.alignment = ["fill", "fill"];
        body.preferredSize = [300, 360];
        body.minimumSize = [280, 120];
        /* Without a cap the body takes the full height of its contents, and the scroll
           range collapses. The cap is the visible height in a floating window. */
        body.maximumSize = [2000, SCROLL_DEFAULT_H];

        /* The arrows are always drawn, so the scroll control is easy to find even
           when the system hides scroll bars until you scroll. */
        var side = outer.add("group");
        side.orientation = "column";
        side.alignChildren = ["fill", "fill"];
        side.alignment = ["fill", "fill"];
        side.spacing = 2;
        side.margins = 0;

        var upBtn = side.add("button", undefined, String.fromCharCode(9650));
        upBtn.preferredSize = [20, 20];
        upBtn.minimumSize = [20, 20];
        upBtn.maximumSize = [20, 20];
        upBtn.helpTip = "Scroll up";

        var bar = side.add("scrollbar", undefined, 0, 0, 1);
        bar.alignment = ["fill", "fill"];
        bar.preferredSize = [20, 300];
        bar.minimumSize = [20, 60];
        bar.stepdelta = 20;
        bar.jumpdelta = 100;
        bar.helpTip = "Drag to scroll";

        var downBtn = side.add("button", undefined, String.fromCharCode(9660));
        downBtn.preferredSize = [20, 20];
        downBtn.minimumSize = [20, 20];
        downBtn.maximumSize = [20, 20];
        downBtn.helpTip = "Scroll down";

        var view = {name: tab.text, body: body, bar: bar, up: upBtn, down: downBtn,
                    rows: [], heights: null};
        bar.onChanging = safe(function () { applyScroll(view); });
        bar.onChange = safe(function () { applyScroll(view); });
        upBtn.onClick = safe(function () {
            view.bar.value = Math.max(0, view.bar.value - view.bar.stepdelta);
            applyScroll(view);
        });
        downBtn.onClick = safe(function () {
            view.bar.value = Math.min(view.bar.maxvalue, view.bar.value + view.bar.stepdelta);
            applyScroll(view);
        });
        scrollViews.push(view);
        return body;
    }

    /* Called once the tab's controls exist: every child of the body is one row. */
    function collectRows(view) {
        var rows = [];
        for (var i = 0; i < view.body.children.length; i++) {
            rows.push(view.body.children[i]);
        }
        view.rows = rows;
        view.heights = null;
    }

    /* Reads each row's height from one layout pass, made while the tab is selected.
       This is the only layout pass the scroll makes. */
    function ensureMeasured(view) {
        if (view.heights || !view.rows.length) { return; }
        ui.win.layout.layout(true);
        view.heights = [];
        for (var j = 0; j < view.rows.length; j++) {
            var h = view.rows[j].size[1];
            view.heights.push(h > 0 ? h : 24);
        }
    }

    /* The top of each row when nothing is scrolled. */
    function rowBases(view) {
        var bases = [];
        var y = SCROLL_MARGIN;
        for (var i = 0; i < view.rows.length; i++) {
            bases.push(y);
            y += view.heights[i] + SCROLL_GAP;
        }
        return bases;
    }

    function applyScroll(view) {
        if (!view.rows.length) { return; }
        ensureMeasured(view);
        var n = view.rows.length;
        var bases = rowBases(view);
        var viewport = view.body.size[1];
        var contentBottom = bases[n - 1] + view.heights[n - 1] + SCROLL_MARGIN;
        var maxPx = Math.max(0, Math.ceil(contentBottom - viewport));

        view.bar.enabled = maxPx > 0;
        view.bar.minvalue = 0;
        view.bar.maxvalue = Math.max(1, maxPx);
        if (view.bar.value > maxPx) { view.bar.value = maxPx; }
        var offset = Math.round(view.bar.value);
        if (view.up) {
            view.up.enabled = maxPx > 0 && offset > 0;
            view.down.enabled = maxPx > 0 && offset < maxPx;
        }

        for (var i = 0; i < n; i++) {
            var y = bases[i] - offset;
            var inside = y >= 0 && y + view.heights[i] <= viewport;
            view.rows[i].location = [view.rows[i].location[0], inside ? y : SCROLL_OFFSCREEN];
        }
    }

    /* Sets the visible height of every tab's body, then places the rows again. */
    function setBodyHeight(H) {
        for (var v = 0; v < scrollViews.length; v++) {
            scrollViews[v].body.maximumSize = [2000, H];
        }
        ui.win.layout.layout(true);
        showCurrentTab();
    }

    /* A docked panel has the height After Effects gives it. Its bodies are capped to
       that height, so the scroll range matches what is visible. Floating windows keep
       their own fixed height. */
    function fitBodies() {
        if (!(thisObj instanceof Panel)) { return; }
        var panelH = ui.win.size[1];
        if (!(panelH > 200)) { panelH = SCROLL_DEFAULT_H + PANEL_CHROME; }
        setBodyHeight(Math.max(120, Math.floor(panelH - PANEL_CHROME)));
    }

    /* Applies the scroll bar of the tab that is showing. */
    function showCurrentTab() {
        var sel = ui.tabs ? ui.tabs.selection : null;
        if (!sel) { return; }
        for (var i = 0; i < scrollViews.length; i++) {
            if (scrollViews[i].name === sel.text) { applyScroll(scrollViews[i]); }
        }
    }

    /* On resize the window is laid out again, which resets row positions. Place the
       rows now, and once more shortly after the layout has settled. */
    function refreshAfterResize() {
        showCurrentTab();
        try {
            app.scheduleTask("$.global.LookDecomposer.fns.showCurrentTab();", 200, false);
        } catch (e) { }
    }

    /* --------------------------------------------------------- UI building */

    /* A slider with an optional checkbox and a readout. */
    function makeSlider(parent, label, lo, hi, value, unit, onChange, onToggle) {
        var row = parent.add("group");
        row.orientation = "row";
        row.alignChildren = ["fill", "center"];
        row.alignment = ["fill", "top"];
        var check = null;
        if (onToggle) {
            check = row.add("checkbox", undefined, "");
            check.onClick = safe(function () { onToggle(check.value); });
        }
        var info = ICON_INFO[label];
        if (info && new File(ICON_DIR + "/" + info.icon + ".png").exists) {
            var pic = row.add("image", undefined, new File(ICON_DIR + "/" + info.icon + ".png"));
            pic.preferredSize = [24, 24];
            pic.minimumSize = [24, 24];
            pic.helpTip = info.tip;
        }
        var lab = row.add("statictext", undefined, label);
        lab.preferredSize = [88, 18];
        if (info) { lab.helpTip = info.tip; }
        var bar = row.add("slider", undefined, 0, 0, 1000);
        bar.alignment = ["fill", "center"];
        var read = row.add("statictext", undefined, "");
        read.preferredSize = [50, 18];

        var range = {lo: lo, hi: hi};
        var api = {check: check, bar: bar, label: lab, readout: read, unit: unit || ""};
        api.setValue = function (v) {
            var n = Number(v);
            if (isNaN(n)) { n = 0; }
            range.lo = Math.min(lo, n);
            range.hi = Math.max(hi, n);
            if (range.hi <= range.lo) { range.hi = range.lo + 1; }
            bar.value = Math.round((n - range.lo) / (range.hi - range.lo) * 1000);
            read.text = fmt(n) + api.unit;
        };
        api.getValue = function () {
            return range.lo + (range.hi - range.lo) * bar.value / 1000;
        };
        api.setEnabled = function (on) {
            bar.enabled = on;
            lab.enabled = on;
            read.enabled = on;
            if (check) { check.enabled = on; }
        };
        var handler = safe(function () {
            var v = api.getValue();
            read.text = fmt(v) + api.unit;
            if (onChange) { onChange(v); }
        });
        bar.onChanging = handler;
        bar.onChange = handler;
        api.setValue(value);
        return api;
    }

    function helpText(parent, text, height) {
        var e = parent.add("edittext", undefined, text, {multiline: true, readonly: true, scrollable: true});
        e.alignment = ["fill", "top"];
        e.preferredSize = [260, height || 52];
        return e;
    }

    function setupTab(tab) {
        tab.orientation = "column";
        tab.alignChildren = ["fill", "top"];
        tab.margins = 6;
        tab.spacing = 6;
    }

    /* A section heading. The controls added after it, to the same column, belong to
       it. Sections are not boxed panels: a boxed panel taller than the scroll area
       cannot be scrolled through, so every control is a row of its own. */
    function sectionOf(container, title, isSub) {
        if (container.children.length > 0) {
            var line = container.add("panel");
            line.preferredSize = [260, 2];
            line.minimumSize = [260, 2];
            line.maximumSize = [2000, 2];
        }
        var h = container.add("statictext", undefined, title);
        h.graphics.font = isSub ? FONT_SUB : FONT_SECTION;
        return container;
    }

    function makePartRow(parent, i) {
        var p = PARTS[i];
        return makeSlider(parent, p.label, p.min, p.max, p.neutral, p.unit,
                          function (v) { onPartChange(i, v); },
                          function (on) { onPartToggle(i, on); });
    }

    function makeGradeRow(parent, i) {
        var c = GRADE_CONTROLS[i];
        return makeSlider(parent, c.label, c.min, c.max, c.neutral, c.unit,
                          function (v) { onGradeChange(i, v); });
    }

    /* Adds the slider rows for these parts, in order, to one section. */
    function addParts(container, indices) {
        for (var k = 0; k < indices.length; k++) {
            ui.partRows[indices[k]] = makePartRow(container, indices[k]);
        }
    }

    function addGrades(container, indices) {
        for (var k = 0; k < indices.length; k++) {
            ui.gradeRows[indices[k]] = makeGradeRow(container, indices[k]);
        }
    }

    /* Tab 1: the reference look, the footage, and the setup check. */
    function buildUploadTab(tab) {
        tab = scrollBodyOf(tab);
        setupTab(tab);

        var refSec = sectionOf(tab, "A. Reference look (the look to copy)");
        helpText(refSec, "Choose a still or a video with the look you want. It is analyzed, " +
                         "and the look is applied to your footage.", 44);
        var refBtn = refSec.add("button", undefined, "Upload reference look...");
        refBtn.onClick = safe(uploadReference);
        ui.refLabel = refSec.add("statictext", undefined, "Reference: none yet");
        ui.refResult = helpText(refSec, "", 90);

        var footSec = sectionOf(tab, "B. Footage to grade");
        helpText(footSec, "Choose one or more pictures or videos. Each is added to the " +
                          "composition with the reference look applied, and the sliders " +
                          "change it straight away.", 58);
        var footBtn = footSec.add("button", undefined, "Upload footage...");
        footBtn.onClick = safe(uploadFootage);
        ui.workLabel = footSec.add("statictext", undefined, "Working on: nothing yet");
        var next = footSec.add("button", undefined, "Go to 2 Adjust");
        next.onClick = safe(function () { ui.tabs.selection = ui.tabAdjust; showCurrentTab(); });

        var setupSec = sectionOf(tab, "Setup");
        var check = setupSec.add("button", undefined, "Check setup");
        check.onClick = safe(function () {
            var problem = setupProblem();
            setStatus(problem ? problem : "Ready. Upload a reference look, then your footage.");
        });
    }

    /* Tab 2: the look on the working footage. One section per kind of change. */
    function buildAdjustTab(tab) {
        tab = scrollBodyOf(tab);
        setupTab(tab);

        var lookSec = sectionOf(tab, "Look on the working footage");
        ui.adjustTarget = lookSec.add("statictext", undefined, "Working on: nothing yet");
        ui.strength = makeSlider(lookSec, "Strength", 0, 100, 100, "%", onStrength);
        var lookButtons = lookSec.add("group");
        lookButtons.orientation = "row";
        lookButtons.alignment = ["fill", "top"];
        var apply = lookButtons.add("button", undefined, "Apply reference");
        apply.onClick = safe(applyReferenceNow);
        var remove = lookButtons.add("button", undefined, "Remove look");
        remove.onClick = safe(removeLook);
        helpText(lookSec, "Drag a slider to change the look. Untick a box to turn that part off. " +
                          "Apply reference resets the slider changes.", 56);

        ui.partRows = [];
        addParts(sectionOf(tab, "Light"), [0, 1, 2, 3]);
        addParts(sectionOf(tab, "Color"), [4, 5, 6, 7]);
        addParts(sectionOf(tab, "Effects"), [8, 9, 10, 11]);
    }

    /* Tab 3: the color grade, after the look. */
    function buildGradeTab(tab) {
        tab = scrollBodyOf(tab);
        setupTab(tab);

        var headSec = sectionOf(tab, "Grade on the working footage");
        ui.gradeTarget = headSec.add("statictext", undefined, "Working on: nothing yet");
        helpText(headSec, "The grade is applied after the look and works with or without a look. " +
                          "Mix blends the grade with the original (100% = full grade).", 56);
        var reset = headSec.add("button", undefined, "Reset grade");
        reset.onClick = safe(resetGrade);

        ui.gradeRows = [];
        addGrades(sectionOf(tab, "Light"), [0, 1, 2, 3, 4, 5]);
        addGrades(sectionOf(tab, "Color"), [6, 7]);
        addGrades(sectionOf(tab, "Finish"), [8, 9]);
    }

    /* Tab 4: the regions list, then choose the area, then change it. */
    function buildRegionsTab(tab) {
        tab = scrollBodyOf(tab);
        setupTab(tab);

        var listSec = sectionOf(tab, "Regions in this composition");
        ui.regionList = listSec.add("listbox", undefined, []);
        ui.regionList.alignment = ["fill", "top"];
        ui.regionList.preferredSize = [260, 70];
        ui.regionList.onChange = safe(onRegionSelect);
        var buttons = listSec.add("group");
        buttons.orientation = "row";
        buttons.alignment = ["fill", "top"];
        var addB = buttons.add("button", undefined, "Add region");
        addB.onClick = safe(addRegion);
        var remB = buttons.add("button", undefined, "Remove region");
        remB.onClick = safe(removeRegion);
        var refreshB = buttons.add("button", undefined, "Refresh");
        refreshB.onClick = safe(refreshRegions);

        var areaSec = sectionOf(tab, "1. Choose the area");

        var autoPanel = sectionOf(areaSec, "Auto mask (selects by itself)", true);
        var modeRow = autoPanel.add("group");
        modeRow.orientation = "row";
        modeRow.alignment = ["fill", "top"];
        modeRow.add("statictext", undefined, "Select:");
        var modeNames = [];
        for (var am = 0; am < AUTO_MODES.length; am++) { modeNames.push(AUTO_MODES[am][0]); }
        ui.autoMode = modeRow.add("dropdownlist", undefined, modeNames);
        ui.autoMode.selection = 0;
        ui.autoGrow = makeSlider(autoPanel, "Grow / shrink", -20, 20, 0, " px");
        ui.autoFeather = makeSlider(autoPanel, "Edge softness", 0, 20, 2, " px");
        ui.autoInvert = autoPanel.add("checkbox", undefined, "Invert (select everything else)");
        var autoButton = autoPanel.add("button", undefined, "Create auto-masked region");
        autoButton.onClick = safe(createAutoRegion);
        helpText(autoPanel, "Uses the working footage. Subject and People use Apple Vision on " +
                            "this Mac. Color range uses the Colors choice in section 2. " +
                            "Section 2 applies only inside the mask.", 70);

        var manualPanel = sectionOf(areaSec, "Manual area (ellipse or rectangle)", true);
        ui.regArea = manualPanel.add("checkbox", undefined, "Limit to an area of the picture");
        ui.regArea.onClick = safe(onRegionChange);
        var shapeRow = manualPanel.add("group");
        shapeRow.orientation = "row";
        shapeRow.alignment = ["fill", "top"];
        shapeRow.add("statictext", undefined, "Shape:");
        ui.regShape = shapeRow.add("dropdownlist", undefined, ["Ellipse", "Rectangle"]);
        ui.regShape.selection = 0;
        ui.regShape.onChange = safe(onRegionChange);
        ui.regSize = makeSlider(manualPanel, "Area size", 5, 100, 50, "%", onRegionChange);
        ui.regFeather = makeSlider(manualPanel, "Edge softness", 0, 200, 20, " px", onRegionChange);
        ui.regX = makeSlider(manualPanel, "Move left/right", -50, 50, 0, "%", onRegionChange);
        ui.regY = makeSlider(manualPanel, "Move up/down", -50, 50, 0, "%", onRegionChange);

        var changeSec = sectionOf(tab, "2. Change the area");
        var colorRow = changeSec.add("group");
        colorRow.orientation = "row";
        colorRow.alignment = ["fill", "top"];
        colorRow.add("statictext", undefined, "Colors:");
        var names = [];
        for (var c = 0; c < CHANNELS.length; c++) { names.push(CHANNELS[c][0]); }
        ui.regColor = colorRow.add("dropdownlist", undefined, names);
        ui.regColor.selection = 0;
        ui.regColor.onChange = safe(onRegionChange);
        ui.regHue = makeSlider(changeSec, "Hue shift", -180, 180, 0, " deg", onRegionChange);
        ui.regValue = makeSlider(changeSec, "Value", -100, 100, 0, "", onRegionChange);
        ui.regSat = makeSlider(changeSec, "Saturation", -100, 100, 0, "", onRegionChange);
        ui.regOpacity = makeSlider(changeSec, "Opacity", 0, 100, 100, "%", onRegionChange);
        var blendRow = changeSec.add("group");
        blendRow.orientation = "row";
        blendRow.alignment = ["fill", "top"];
        blendRow.add("statictext", undefined, "Blend:");
        var blendNames = [];
        for (var bn = 0; bn < BLEND_MODES.length; bn++) { blendNames.push(BLEND_MODES[bn][0]); }
        ui.regBlend = blendRow.add("dropdownlist", undefined, blendNames);
        ui.regBlend.selection = 0;
        ui.regBlend.onChange = safe(onRegionChange);

        updateAreaControls();
    }

    function buildUI(thisObj) {
        var win;
        if (thisObj instanceof Panel) {
            win = thisObj;
        } else {
            win = new Window("palette", PANEL_TITLE, undefined, {resizeable: true});
        }
        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.margins = 8;
        win.spacing = 6;
        ui.win = win;

        var title = win.add("statictext", undefined, PANEL_TITLE);
        title.graphics.font = FONT_TITLE;
        ui.topTarget = win.add("statictext", undefined, "Working on: nothing yet");
        ui.status = win.add("edittext", undefined,
                            "Step 1: upload a reference look (A), then your footage (B).",
                            {multiline: true, readonly: true, scrollable: true});
        ui.status.alignment = ["fill", "top"];
        ui.status.preferredSize = [300, 60];

        ui.tabs = win.add("tabbedpanel");
        ui.tabs.alignment = ["fill", "fill"];
        ui.tabUpload = ui.tabs.add("tab", undefined, "1 Upload");
        ui.tabAdjust = ui.tabs.add("tab", undefined, "2 Adjust");
        ui.tabGrade = ui.tabs.add("tab", undefined, "3 Grade");
        ui.tabRegions = ui.tabs.add("tab", undefined, "4 Regions");
        /* A floating window is sized when it is built, from its contents' preferred
           widths. Capping the width here keeps the window at 340 pixels wide. */
        if (!(win instanceof Panel)) {
            ui.tabs.maximumSize = [340, 2000];
            ui.tabUpload.maximumSize = [340, 2000];
            ui.tabAdjust.maximumSize = [340, 2000];
            ui.tabGrade.maximumSize = [340, 2000];
            ui.tabRegions.maximumSize = [340, 2000];
        }
        buildUploadTab(ui.tabUpload);
        buildAdjustTab(ui.tabAdjust);
        buildGradeTab(ui.tabGrade);
        buildRegionsTab(ui.tabRegions);
        for (var v = 0; v < scrollViews.length; v++) { collectRows(scrollViews[v]); }
        ui.tabs.selection = ui.tabUpload;
        ui.tabs.onChange = safe(function () { fitBodies(); showCurrentTab(); });
        try { win.onResize = safe(function () { fitBodies(); refreshAfterResize(); }); } catch (e) { }
        return win;
    }

    /* Refreshes the labels and slider values from the working footage. */
    function refreshAll() {
        var layer = targetLayer();
        var label = "Working on: " + (layer ? layer.name : "nothing yet");
        if (ui.topTarget) { ui.topTarget.text = label; }
        if (ui.workLabel) { ui.workLabel.text = label; }
        if (ui.adjustTarget) { ui.adjustTarget.text = label; }
        if (ui.gradeTarget) { ui.gradeTarget.text = label; }
        if (ui.refLabel) { ui.refLabel.text = S.reference ? "Reference: " + S.reference.name : "Reference: none yet"; }

        var st = layer ? loadLookState(layer) : null;
        if (ui.strength) {
            ui.strength.setEnabled(!!layer);
            ui.strength.setValue(st && typeof st.strength === "number" ? st.strength * 100 : 100);
        }
        if (ui.partRows) {
            for (var i = 0; i < PARTS.length; i++) {
                var p = PARTS[i];
                var row = ui.partRows[i];
                var v = p.neutral;
                var sec = st ? effectiveSection(st, p.aspect) : null;
                if (sec && sec[p.field] !== undefined) { v = Number(sec[p.field]); }
                row.setValue(v);
                row.setEnabled(!!layer);
                if (row.check) { row.check.value = st ? !isOff(st, p.aspect) : true; }
            }
        }
        if (ui.gradeRows) {
            for (var g = 0; g < GRADE_CONTROLS.length; g++) {
                ui.gradeRows[g].setValue(gradeValueOf(st ? st.grade : null, GRADE_CONTROLS[g]));
                ui.gradeRows[g].setEnabled(!!layer);
            }
        }
    }

    /* ------------------------------------------------------------- start */

    /* Opening from File > Scripts again brings the existing window forward. */
    var existing = $.global.LookDecomposer;
    if (!(thisObj instanceof Panel) && existing && existing.version === PANEL_VERSION &&
        existing.ui && existing.ui.win) {
        try {
            existing.ui.win.show();
            return existing.ui.win;
        } catch (e) {
            /* The old window cannot be shown again; build a new one below. */
        }
    }

    var panel = buildUI(thisObj);
    refreshAll();
    refreshRegions();

    /* Handle for testing from the ExtendScript console. */
    $.global.LookDecomposer = {
        version: PANEL_VERSION,
        state: S,
        ui: ui,
        fns: {
            setReference: setReference, addFootageFiles: addFootageFiles,
            applyReferenceTo: applyReferenceTo, targetLayer: targetLayer,
            sourceFrameForMask: sourceFrameForMask, createAutoRegion: createAutoRegion,
            renderLook: renderLook, loadLookState: loadLookState, effectiveSection: effectiveSection,
            onPartChange: onPartChange, onPartToggle: onPartToggle, onStrength: onStrength,
            onGradeChange: onGradeChange, removeLook: removeLook, resetGrade: resetGrade,
            addRegion: addRegion, removeRegion: removeRegion, refreshRegions: refreshRegions,
            refreshAll: refreshAll, regionSettingsOf: regionSettingsOf, renderRegion: renderRegion,
            videoFrame: videoFrame, importFootage: importFootage, setupProblem: setupProblem,
            applyScroll: applyScroll, showCurrentTab: showCurrentTab, scrollViews: scrollViews,
            rowBases: rowBases, setBodyHeight: setBodyHeight, fitBodies: fitBodies
        }
    };

    if (panel instanceof Window) {
        try { panel.preferredSize = [340, 640]; } catch (e) { }
        panel.center();
        panel.show();
        panel.layout.layout(true);
        showCurrentTab();
    } else {
        panel.layout.layout(true);
        fitBodies();
        showCurrentTab();
    }
    return panel;

})
