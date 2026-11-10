/* build_look_comp.jsx — Look Decomposer build entry point.
 *
 * Loads the engine (look_fx.jsx) from the same folder. Call from any
 * transport (MCP bridge, Run Script File, DoScript) as:
 *
 *   $.evalFile(<this file>);
 *   $.global.LOOKFX.buildComp(analysisObject, sourcePath, options);
 */

(function () {
    var dir = new File($.fileName).parent;
    $.evalFile(new File(dir.fsName + "/look_fx.jsx").fsName);
})();
