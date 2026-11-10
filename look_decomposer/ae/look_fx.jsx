/* look_fx.jsx — Look Decomposer AE engine.
 *
 * Builds an After Effects composition from a look-analysis JSON object.
 *
 *   LOOKFX.buildComp(analysis, sourcePath, options) -> inventory object
 *
 * options:
 *   mode       "edit" (default) — named adjustment layers + LOOK CONTROLS null
 *                               with slider controls wired by expressions
 *              "flat"          — same effect stack applied directly to the
 *                               source layer (used to render ground-truth
 *                               reference stills)
 *   prefix     comp-name prefix, default "LOOK" ("GEN" for ground truth)
 *   open       open the comp in a viewer when done (default true)
 *   export_png absolute path — also saves frame 0 as PNG after building
 *
 * Effect match names were verified against After Effects 26.5 (see
 * docs/schema.md for the JSON format this consumes).
 */

(function () {

    var ORDER = [
        ["exposure",      "Exposure"],
        ["levels",        "Levels / Contrast"],
        ["white_balance", "White Balance"],
        ["saturation",    "Saturation"],
        ["split_tone",    "Split Tone"],
        ["blur",          "Blur"],
        ["glow",          "Glow"],
        ["vignette",      "Vignette"],
        ["grain",         "Grain"]
    ];

    var CONTROLS_NAME = "LOOK CONTROLS";

    function num(v, fallback) {
        v = parseFloat(v);
        return isNaN(v) ? fallback : v;
    }

    function clamp(v, lo, hi) {
        if (v < lo) { return lo; }
        if (v > hi) { return hi; }
        return v;
    }

    function hexToRgb(hex, warnings) {
        var h = String(hex || "").replace("#", "");
        if (!/^[0-9a-fA-F]{6}$/.test(h)) {
            warnings.push("Bad hex color '" + hex + "'; using black");
            return [0, 0, 0, 1];
        }
        return [
            parseInt(h.substr(0, 2), 16) / 255,
            parseInt(h.substr(2, 2), 16) / 255,
            parseInt(h.substr(4, 2), 16) / 255,
            1
        ];
    }

    function setP(fx, matchName, value, warnings) {
        try {
            var prop = fx.property(matchName);
            if (!prop) {
                warnings.push("No property " + matchName + " on " + fx.name);
                return false;
            }
            prop.setValue(value);
            return true;
        } catch (e) {
            warnings.push(fx.name + " / " + matchName + ": " + String(e && e.message ? e.message : e));
            return false;
        }
    }

    function addFx(layer, matchName, displayName) {
        var fx = layer.property("ADBE Effect Parade").addProperty(matchName);
        fx.name = displayName;
        return fx;
    }

    /* Applies one look aspect to a layer. Returns the effects added. */
    function applyAspect(layer, key, v, warnings) {
        var fx = null;
        switch (key) {

        case "exposure":
            fx = addFx(layer, "ADBE Exposure2", "Exposure");
            setP(fx, "ADBE Exposure2-0003", num(v.stops, 0), warnings);
            if (v.gamma !== undefined && v.gamma !== null) {
                setP(fx, "ADBE Exposure2-0005", clamp(num(v.gamma, 1), 0.01, 10), warnings);
            }
            return [fx];

        case "levels":
            fx = addFx(layer, "ADBE Pro Levels2", "Levels (Individual Controls)");
            setP(fx, "ADBE Pro Levels2-0004", clamp(num(v.input_black, 0), 0, 0.98), warnings);
            setP(fx, "ADBE Pro Levels2-0005", clamp(num(v.input_white, 1), 0.02, 1), warnings);
            if (v.gamma !== undefined && v.gamma !== null) {
                setP(fx, "ADBE Pro Levels2-0006", clamp(num(v.gamma, 1), 0.01, 10), warnings);
            }
            setP(fx, "ADBE Pro Levels2-0007", clamp(num(v.output_black, 0), 0, 0.98), warnings);
            setP(fx, "ADBE Pro Levels2-0008", clamp(num(v.output_white, 1), 0.02, 1), warnings);
            return [fx];

        case "white_balance":
            fx = addFx(layer, "ADBE Lumetri", "White Balance (Lumetri)");
            setP(fx, "ADBE Lumetri-0007", clamp(num(v.temperature, 0), -100, 100), warnings);
            setP(fx, "ADBE Lumetri-0008", clamp(num(v.tint, 0), -100, 100), warnings);
            return [fx];

        case "saturation":
            // Color Balance (HLS) instead of Hue/Saturation: its Saturation
            // parameter behaves identically but accepts expressions, which
            // Hue/Saturation's legacy parameters do not (verified AE 26.5).
            fx = addFx(layer, "ADBE Color Balance (HLS)", "Saturation (Color Balance)");
            setP(fx, "ADBE Color Balance (HLS)-0003", clamp(num(v.amount, 0), -100, 100), warnings);
            return [fx];

        case "split_tone":
            fx = addFx(layer, "ADBE Tint", "Split Tone (Tint)");
            setP(fx, "ADBE Tint-0001", hexToRgb(v.shadows_hex, warnings), warnings);
            setP(fx, "ADBE Tint-0002", hexToRgb(v.highlights_hex, warnings), warnings);
            setP(fx, "ADBE Tint-0003", clamp(num(v.strength, 0), 0, 100), warnings);
            return [fx];

        case "blur":
            fx = addFx(layer, "ADBE Gaussian Blur 2", "Gaussian Blur");
            setP(fx, "ADBE Gaussian Blur 2-0001", clamp(num(v.radius_px, 0), 0, 500), warnings);
            return [fx];

        case "glow":
            fx = addFx(layer, "ADBE Glo2", "Glow");
            setP(fx, "ADBE Glo2-0002", clamp(num(v.threshold, 153), 0, 255), warnings);
            setP(fx, "ADBE Glo2-0003", clamp(num(v.radius_px, 10), 0, 500), warnings);
            setP(fx, "ADBE Glo2-0004", clamp(num(v.intensity, 1), 0, 100), warnings);
            return [fx];

        case "vignette":
            fx = addFx(layer, "ADBE Lumetri", "Vignette (Lumetri)");
            setP(fx, "ADBE Lumetri-0051", clamp(num(v.amount, 0), -5, 5), warnings);
            if (v.midpoint !== undefined && v.midpoint !== null) {
                setP(fx, "ADBE Lumetri-0052", clamp(num(v.midpoint, 50), 0, 100), warnings);
            }
            if (v.roundness !== undefined && v.roundness !== null) {
                setP(fx, "ADBE Lumetri-0053", clamp(num(v.roundness, 0), -100, 100), warnings);
            }
            if (v.feather !== undefined && v.feather !== null) {
                setP(fx, "ADBE Lumetri-0054", clamp(num(v.feather, 50), 0, 100), warnings);
            }
            return [fx];

        case "grain":
            fx = addFx(layer, "ADBE Noise2", "Grain (Noise)");
            setP(fx, "ADBE Noise2-0001", clamp(num(v.amount, 0), 0, 100), warnings);
            if (v.monochrome !== undefined && v.monochrome !== null) {
                // Noise Type: 0 = monochrome, 1 = color noise (AE 26.5 default is color)
                setP(fx, "ADBE Noise2-0002", v.monochrome ? 0 : 1, warnings);
            }
            return [fx];
        }
        return [];
    }

    function findOrImportFootage(project, path, warnings) {
        var file = new File(path);
        if (!file.exists) {
            throw new Error("Source media not found: " + path);
        }
        for (var i = 1; i <= project.numItems; i++) {
            var item = project.item(i);
            if (item instanceof FootageItem && item.file &&
                item.file.fsName.toLowerCase() === file.fsName.toLowerCase()) {
                return item;
            }
        }
        return project.importFile(new ImportOptions(file));
    }

    function sliderExpr(sliderName) {
        return 'thisComp.layer("' + CONTROLS_NAME + '").effect("' + sliderName + '")("Slider")';
    }

    function addSliderControl(comp, name, value) {
        var fx = comp.layer(CONTROLS_NAME).property("ADBE Effect Parade")
            .addProperty("ADBE Slider Control");
        fx.name = name;
        fx.property("ADBE Slider Control-0001").setValue(value);
        return fx;
    }

    function wireExpression(fx, matchName, expr, warnings) {
        try {
            fx.property(matchName).expression = expr;
            return true;
        } catch (e) {
            var reason = (e && e.message) ? e.message : String(e);
            warnings.push("Expression failed on " + fx.name + "/" + matchName + ": " + reason);
            return false;
        }
    }

    /* Creates the LOOK CONTROLS null and wires sliders to effect parameters. */
    function buildControls(comp, look, fxByAspect, warnings) {
        var n = comp.layers.addNull(comp.duration);
        n.name = CONTROLS_NAME;
        n.label = 2; // red label so it stands out
        n.comment = "Master sliders for the Look Decomposer stack. " +
                    "Rename/move with care — layer effect expressions reference this layer.";

        var wired = [];

        if (fxByAspect.exposure) {
            addSliderControl(comp, "Exposure", num(look.exposure.stops, 0));
            wired.push(wireExpression(
                fxByAspect.exposure, "ADBE Exposure2-0003", sliderExpr("Exposure"), warnings));
        }

        if (fxByAspect.levels) {
            var lv = look.levels;
            var inBlack = num(lv.input_black, 0);
            var inWhite = num(lv.input_white, 1);
            var contrast = Math.max(inBlack, 1 - inWhite);
            if (Math.abs(inBlack - contrast) > 0.001 || Math.abs((1 - inWhite) - contrast) > 0.001) {
                warnings.push("Levels contrast is asymmetric (in_black=" + inBlack +
                              ", in_white=" + inWhite +
                              "); Contrast slider uses the stronger side, check the " +
                              "Levels effect for the remainder");
            }
            addSliderControl(comp, "Contrast", contrast);
            wired.push(wireExpression(
                fxByAspect.levels, "ADBE Pro Levels2-0004", sliderExpr("Contrast"), warnings));
            wired.push(wireExpression(
                fxByAspect.levels, "ADBE Pro Levels2-0005",
                "1 - " + sliderExpr("Contrast"), warnings));

            var fade = num(lv.output_black, 0);
            if (fade > 0 || num(lv.output_white, 1) < 1) {
                if (Math.abs((1 - num(lv.output_white, 1)) - fade) > 0.001) {
                    warnings.push("Levels fade is asymmetric; Fade Lift slider uses output_black");
                }
                addSliderControl(comp, "Fade Lift", fade);
                wired.push(wireExpression(
                    fxByAspect.levels, "ADBE Pro Levels2-0007", sliderExpr("Fade Lift"), warnings));
                wired.push(wireExpression(
                    fxByAspect.levels, "ADBE Pro Levels2-0008",
                    "1 - " + sliderExpr("Fade Lift"), warnings));
            }
        }

        if (fxByAspect.white_balance) {
            addSliderControl(comp, "Temperature", num(look.white_balance.temperature, 0));
            wired.push(wireExpression(
                fxByAspect.white_balance, "ADBE Lumetri-0007",
                sliderExpr("Temperature"), warnings));
            addSliderControl(comp, "Tint", num(look.white_balance.tint, 0));
            wired.push(wireExpression(
                fxByAspect.white_balance, "ADBE Lumetri-0008", sliderExpr("Tint"), warnings));
        }

        if (fxByAspect.saturation) {
            addSliderControl(comp, "Saturation", num(look.saturation.amount, 0));
            wired.push(wireExpression(
                fxByAspect.saturation, "ADBE Color Balance (HLS)-0003",
                sliderExpr("Saturation"), warnings));
        }

        if (fxByAspect.split_tone) {
            addSliderControl(comp, "Split Tone Strength", num(look.split_tone.strength, 0));
            wired.push(wireExpression(
                fxByAspect.split_tone, "ADBE Tint-0003",
                sliderExpr("Split Tone Strength"), warnings));
        }

        if (fxByAspect.blur) {
            addSliderControl(comp, "Blur", num(look.blur.radius_px, 0));
            wired.push(wireExpression(
                fxByAspect.blur, "ADBE Gaussian Blur 2-0001", sliderExpr("Blur"), warnings));
        }

        if (fxByAspect.glow) {
            addSliderControl(comp, "Glow Intensity", num(look.glow.intensity, 1));
            wired.push(wireExpression(
                fxByAspect.glow, "ADBE Glo2-0004", sliderExpr("Glow Intensity"), warnings));
        }

        if (fxByAspect.vignette) {
            addSliderControl(comp, "Vignette Amount", num(look.vignette.amount, 0));
            wired.push(wireExpression(
                fxByAspect.vignette, "ADBE Lumetri-0051",
                sliderExpr("Vignette Amount"), warnings));
        }

        if (fxByAspect.grain) {
            addSliderControl(comp, "Grain", num(look.grain.amount, 0));
            wired.push(wireExpression(
                fxByAspect.grain, "ADBE Noise2-0001", sliderExpr("Grain"), warnings));
        }

        var okCount = 0;
        for (var i = 0; i < wired.length; i++) {
            if (wired[i]) { okCount++; }
        }
        return { sliders: okCount, total: wired.length };
    }

    function describeLayer(layer) {
        var effects = [];
        var group = layer.property("ADBE Effect Parade");
        if (group) {
            for (var i = 1; i <= group.numProperties; i++) {
                effects.push(group.property(i).name);
            }
        }
        return {
            index: layer.index,
            name: layer.name,
            adjustment: !!layer.adjustmentLayer,
            effects: effects
        };
    }

    function buildComp(analysis, sourcePath, options) {
        options = options || {};
        var mode = options.mode === "flat" ? "flat" : "edit";
        var warnings = [];

        if (!analysis || typeof analysis !== "object") {
            throw new Error("analysis must be an object");
        }
        var look = analysis.look || {};
        var path = sourcePath || (analysis.source && analysis.source.path);
        if (!path) {
            throw new Error("No source path given (pass sourcePath or analysis.source.path)");
        }

        var project = app.project;
        if (!project) { project = app.newProject(); }

        var item = findOrImportFootage(project, path, warnings);

        var w = item.width;
        var h = item.height;
        var dur = (isFinite(item.duration) && item.duration > 0) ? item.duration : 5;
        var fps = (isFinite(item.frameRate) && item.frameRate > 0) ? item.frameRate : 30;
        if (analysis.source && analysis.source.width && analysis.source.height) {
            w = analysis.source.width;
            h = analysis.source.height;
        }

        var slug = String(analysis.name || "unnamed");
        var prefix = options.prefix || (mode === "flat" ? "GEN" : "LOOK");
        var comp = project.items.addComp(prefix + " — " + slug, w, h, 1, dur, fps);

        var srcLayer = comp.layers.add(item);
        srcLayer.name = "SOURCE — plate";
        srcLayer.comment = "Original media the look was decomposed from";

        var fxByAspect = {};
        var step = 0;
        for (var i = 0; i < ORDER.length; i++) {
            var key = ORDER[i][0];
            var v = look[key];
            var present = false;
            if (v && typeof v === "object") {
                for (var pk in v) {
                    if (pk !== "confidence") { present = true; break; }
                }
            }
            if (!present) { continue; }

            var target;
            if (mode === "flat") {
                target = srcLayer;
            } else {
                step += 1;
                var layerName = "LOOK " + (step < 10 ? "0" + step : step) +
                                " — " + ORDER[i][1];
                target = comp.layers.addSolid([1, 1, 1], layerName,
                                               comp.width, comp.height, 1, comp.duration);
                target.adjustmentLayer = true;
                target.label = 5;
            }
            var added = applyAspect(target, key, v, warnings);
            for (var a = 0; a < added.length; a++) {
                fxByAspect[key] = added[a];
            }
        }

        var controlsInfo = null;
        if (mode === "edit" && options.controls !== false) {
            controlsInfo = buildControls(comp, look, fxByAspect, warnings);
        }

        var exported = null;
        if (options.export_png) {
            var png = new File(options.export_png);
            var folder = png.parent;
            if (!folder.exists) { folder.create(); }
            var ok = comp.saveFrameToPng(0, png);
            if (ok) {
                exported = png.fsName;
            } else {
                warnings.push("saveFrameToPng failed for " + png.fsName);
            }
        }

        if (options.open !== false) {
            comp.openInViewer();
        }

        var layers = [];
        for (var li = 1; li <= comp.numLayers; li++) {
            layers.push(describeLayer(comp.layer(li)));
        }

        return {
            comp: comp.name,
            id: comp.id,
            mode: mode,
            source: path,
            width: comp.width,
            height: comp.height,
            duration: comp.duration,
            frame_rate: comp.frameRate,
            layers: layers,
            controls: controlsInfo,
            exported_png: exported,
            warnings: warnings
        };
    }

    $.global.LOOKFX = {
        buildComp: buildComp,
        applyAspect: applyAspect,
        ORDER: ORDER
    };

})();
