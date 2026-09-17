// ae-video-studio runtime: executes op lists produced by the Python compiler (engine/aestudio).
// ExtendScript is ES3: no JSON object, no Array.forEach/map, no String.trim.
var AES = (function () {
    var EASE = "function c01(x){return Math.min(Math.max(x,0),1);}" +
        "function so(x){x=c01(x);return 1-Math.pow(1-x,3);}" +
        "function si(x){x=c01(x);return x*x*x;}" +
        "function bo(x){x=c01(x);var s=1.3;return 1+(s+1)*Math.pow(x-1,3)+s*Math.pow(x-1,2);}" +
        "function eio(x){x=c01(x);return x<0.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;}";
    var TRANSFORM = {anchor: "ADBE Anchor Point", position: "ADBE Position", scale: "ADBE Scale",
        rotation: "ADBE Rotate Z", opacity: "ADBE Opacity"};
    var BASED_ON = {chars: 1, words: 3, lines: 4};
    var ctx = null;

    function toJSON(v) {
        if (v === null || v === undefined) { return "null"; }
        var t = typeof v, i, parts;
        if (t === "number") { return isFinite(v) ? String(v) : "null"; }
        if (t === "boolean") { return v ? "true" : "false"; }
        if (t === "string") {
            return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r").replace(/\t/g, "\\t") + '"';
        }
        if (v instanceof Array) {
            parts = [];
            for (i = 0; i < v.length; i++) { parts.push(toJSON(v[i])); }
            return "[" + parts.join(",") + "]";
        }
        parts = [];
        for (var k in v) { if (v.hasOwnProperty(k)) { parts.push(toJSON(k) + ":" + toJSON(v[k])); } }
        return "{" + parts.join(",") + "}";
    }

    function findFolder(name, parent) {
        var root = parent || app.project.rootFolder;
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof FolderItem && it.name === name && it.parentFolder === root) { return it; }
        }
        var f = app.project.items.addFolder(name);
        f.parentFolder = root;
        return f;
    }

    function findComp(name) {
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof CompItem && it.name === name) { return it; }
        }
        return null;
    }

    function removeSolids(folder) {
        for (var i = app.project.numItems; i >= 1; i--) {
            var it = app.project.item(i);
            if (it instanceof FootageItem && it.parentFolder === folder && it.mainSource instanceof SolidSource) { it.remove(); }
        }
    }

    function imp(path) {
        var f = new File(path);
        if (!f.exists) { throw new Error("missing file: " + path); }
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof FootageItem && it.file && it.file.fsName === f.fsName) { return it; }
        }
        var item = app.project.importFile(new ImportOptions(f));
        item.parentFolder = ctx.folder;
        return item;
    }

    function L(id) {
        if (!ctx.layers.hasOwnProperty(id)) { throw new Error("unknown layer id: " + id); }
        return ctx.layers[id];
    }

    function tprop(layer, key) {
        if (!TRANSFORM.hasOwnProperty(key)) { throw new Error("unknown transform key: " + key); }
        return layer.property("ADBE Transform Group").property(TRANSFORM[key]);
    }

    function setExprs(layer, exprs) {
        if (!exprs) { return; }
        for (var k in exprs) { if (exprs.hasOwnProperty(k)) { tprop(layer, k).expression = EASE + exprs[k]; } }
    }

    // Name, parent, static transform, expressions and in/out. Parenting first: AE compensates the child
    // transform when a parent is set, so rotation/scale/position are reset explicitly afterwards.
    function place(layer, o) {
        layer.name = o.id;
        if (o.parent) {
            layer.parent = L(o.parent);
            tprop(layer, "rotation").setValue(0);
            tprop(layer, "scale").setValue([100, 100]);
            tprop(layer, "position").setValue([0, 0]);
        }
        if (o.anchor) { tprop(layer, "anchor").setValue(o.anchor); }
        if (o.position) { tprop(layer, "position").setValue(o.position); }
        if (o.scale) { tprop(layer, "scale").setValue(o.scale); }
        if (o.rotation !== undefined) { tprop(layer, "rotation").setValue(o.rotation); }
        if (o.opacity !== undefined) { tprop(layer, "opacity").setValue(o.opacity); }
        setExprs(layer, o.expr);
        if (o["in"] !== undefined) { layer.inPoint = o["in"]; }
        if (o.out !== undefined) { layer.outPoint = o.out; }
        ctx.layers[o.id] = layer;
        return layer;
    }

    function levels(layer, o) {
        var p = layer.property("ADBE Audio Group").property("ADBE Audio Levels");
        if (o.levels) {
            for (var i = 0; i < o.levels.length; i++) { p.setValueAtTime(o.levels[i][0], [o.levels[i][1], o.levels[i][1]]); }
        } else if (o.gain_db !== undefined) {
            p.setValue([o.gain_db, o.gain_db]);
        }
    }

    function lumetri(layer, values) {
        var lu = layer.property("ADBE Effect Parade").addProperty("ADBE Lumetri");
        for (var k in values) {
            if (values.hasOwnProperty(k)) {
                try { lu.property(parseInt(k, 10)).setValue(values[k]); } catch (e) { ctx.warnings.push(layer.name + " lumetri " + k + ": " + e); }
            }
        }
    }

    function mask(layer, item, size, scalePct) {
        var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        var shp = new Shape();
        var hw = size[0] / 2 / (scalePct / 100), hh = size[1] / 2 / (scalePct / 100);
        var cx = item.width / 2, cy = item.height / 2;
        shp.vertices = [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]];
        shp.closed = true;
        m.property("ADBE Mask Shape").setValue(shp);
    }

    function media(o, audioOnly) {
        var item = imp(o.file);
        var layer = ctx.comp.layers.add(item);
        place(layer, o);
        if (o.stretch) { layer.stretch = o.stretch; }
        var st = (o.stretch || 100) / 100;
        layer.startTime = o.start - (o.src_in || 0) * st;
        layer.inPoint = o.start;
        var end = o.end;
        if (item.duration > 0) { end = Math.min(end, layer.startTime + item.duration * st); }
        layer.outPoint = end;
        if (audioOnly) {
            if (item.hasVideo) { layer.enabled = false; }
        } else if (item.hasVideo) {
            var sc = o.width ? 100 * o.width / item.width :
                Math.max(ctx.comp.width / item.width, ctx.comp.height / item.height) * 100 * (o.zoom || 1);
            tprop(layer, "scale").setValue([sc, sc]);
            if (o.mask) { mask(layer, item, o.mask, sc); }
            if (o.lumetri) { lumetri(layer, o.lumetri); }
        }
        if (item.hasAudio) {
            layer.audioEnabled = !!audioOnly;
            if (audioOnly) { levels(layer, o); }
        }
        return layer;
    }

    function rectGroup(root, index) {
        root.addProperty("ADBE Vector Group");
        root.property(index).property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
        root.property(index).property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
        // re-fetch: adding properties invalidates earlier references
        var g = root.property(index).property("ADBE Vectors Group");
        return {rect: g.property(1), fill: g.property(2)};
    }

    function reveal(layer, rv) {
        var animators = layer.property("ADBE Text Properties").property("ADBE Text Animators");
        animators.addProperty("ADBE Text Animator");
        var an = animators.property(animators.numProperties);
        var ap = an.property("ADBE Text Animator Properties");
        ap.addProperty("ADBE Text Opacity").setValue(0);
        if (rv.rise) { ap.addProperty("ADBE Text Position 3D").setValue([0, rv.rise, 0]); }
        if (rv.blur) { ap.addProperty("ADBE Text Blur").setValue([rv.blur, rv.blur]); }
        an = animators.property(animators.numProperties);
        an.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
        var sel = animators.property(animators.numProperties).property("ADBE Text Selectors").property(1);
        sel.property("ADBE Text Range Type2").setValue(BASED_ON[rv.by || "words"]);
        sel.property("ADBE Text Expressible Amount").expression = EASE + "var T=" + toJSON(rv.times) +
            ";var i=Math.min(textIndex-1,T.length-1);var k=so((time-T[i])/" + rv.dur + ");var a=100*(1-k);[a,a,a]";
    }

    var OPS = {
        comp: function (o) {
            var old = findComp(o.name);
            if (old) { old.remove(); }
            ctx.comp = app.project.items.addComp(o.name, o.width, o.height, 1, o.duration, o.fps);
            ctx.comp.parentFolder = ctx.folder;
            ctx.comp.motionBlur = true;
            ctx.comp.bgColor = o.bg || [0, 0, 0];
        },
        footage: function (o) { media(o, false); },
        audio: function (o) { media(o, true); },
        group: function (o) {
            var n = ctx.comp.layers.addNull(ctx.comp.duration);
            tprop(n, "anchor").setValue([0, 0]);
            tprop(n, "position").setValue([0, 0]);
            if (o.fade) {
                var fx = n.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
                fx.name = "FADE";
                n.property("ADBE Effect Parade").property("FADE").property(1).expression = EASE + o.fade;
            }
            place(n, o);
        },
        rect: function (o) {
            var s = ctx.comp.layers.addShape();
            var parts = rectGroup(s.property("ADBE Root Vectors Group"), 1);
            parts.fill.property("ADBE Vector Fill Color").setValue(o.color);
            if (o.size) { parts.rect.property("ADBE Vector Rect Size").setValue(o.size); }
            if (o.center) { parts.rect.property("ADBE Vector Rect Position").setValue(o.center); }
            if (o.roundness) { parts.rect.property("ADBE Vector Rect Roundness").setValue(o.roundness); }
            if (o.rect_expr && o.rect_expr.size) { parts.rect.property("ADBE Vector Rect Size").expression = EASE + o.rect_expr.size; }
            if (o.rect_expr && o.rect_expr.center) { parts.rect.property("ADBE Vector Rect Position").expression = EASE + o.rect_expr.center; }
            tprop(s, "position").setValue([0, 0]);
            place(s, o);
        },
        rules: function (o) {
            var s = ctx.comp.layers.addShape();
            var root = s.property("ADBE Root Vectors Group");
            var w = o.width || ctx.comp.width, stroke = o.stroke || 3, i, parts;
            for (i = 0; i < o.count; i++) {
                parts = rectGroup(root, i + 1);
                parts.rect.property("ADBE Vector Rect Size").setValue([w, stroke]);
                parts.rect.property("ADBE Vector Rect Position").setValue([w / 2, o.y0 + i * o.spacing]);
                parts.fill.property("ADBE Vector Fill Color").setValue(o.color);
            }
            if (o.margin_x) {
                parts = rectGroup(root, o.count + 1);
                parts.rect.property("ADBE Vector Rect Size").setValue([stroke, ctx.comp.height]);
                parts.rect.property("ADBE Vector Rect Position").setValue([o.margin_x, ctx.comp.height / 2]);
                parts.fill.property("ADBE Vector Fill Color").setValue(o.margin_color || o.color);
            }
            tprop(s, "position").setValue([0, 0]);
            place(s, o);
        },
        text: function (o) {
            var layer = ctx.comp.layers.addText(o.text);
            var st = layer.property("ADBE Text Properties").property("ADBE Text Document");
            var td = st.value;
            td.resetCharStyle();
            td.resetParagraphStyle();
            td.font = o.font;
            td.fontSize = o.size;
            td.applyFill = true;
            td.fillColor = o.color;
            td.applyStroke = false;
            td.tracking = o.tracking || 0;
            td.justification = o.justify === "center" ? ParagraphJustification.CENTER_JUSTIFY :
                (o.justify === "right" ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY);
            st.setValue(td);
            layer.motionBlur = true;
            place(layer, o);
            if (o.reveal) { reveal(layer, o.reveal); }
        },
        image: function (o) {
            var layer = ctx.comp.layers.add(imp(o.file));
            place(layer, o);
            if (o.width) {
                var sc = 100 * o.width / layer.source.width;
                tprop(layer, "scale").setValue([sc, sc]);
            }
            if (o.tint) { layer.property("ADBE Effect Parade").addProperty("ADBE Fill").property("Color").setValue(o.tint); }
        },
        solid: function (o) {
            var layer = ctx.comp.layers.addSolid(o.color, o.id, ctx.comp.width, ctx.comp.height, 1, ctx.comp.duration);
            layer.source.parentFolder = ctx.folder;
            place(layer, o);
        },
        effect: function (o) {
            var layer = L(o.layer);
            var fx = layer.property("ADBE Effect Parade").addProperty(o.match);
            if (o.name) { fx.name = o.name; }
            var props = o.props || {};
            for (var k in props) {
                if (props.hasOwnProperty(k)) {
                    var p = /^\d+$/.test(k) ? fx.property(parseInt(k, 10)) : fx.property(k);
                    var v = props[k];
                    if (v !== null && typeof v === "object" && !(v instanceof Array) && v.expr !== undefined) {
                        p.expression = EASE + v.expr;
                    } else {
                        p.setValue(v);
                    }
                }
            }
        },
        order: function (o) {
            var low = null;
            for (var i = 0; i < o.below.length; i++) {
                var c = L(o.below[i]);
                if (!low || c.index > low.index) { low = c; }
            }
            L(o.layer).moveAfter(low);
        },
        expr: function (o) { setExprs(L(o.layer), o.exprs); }
    };

    function checkExpressions(group, path, out) {
        for (var i = 1; i <= group.numProperties; i++) {
            var p;
            try { p = group.property(i); } catch (e) { continue; }
            if (!p) { continue; }
            if (p.propertyType === PropertyType.PROPERTY) {
                if (p.canSetExpression && p.expressionEnabled && p.expressionError) { out.push(path + "/" + p.name + ": " + p.expressionError); }
            } else {
                checkExpressions(p, path + "/" + p.name, out);
            }
        }
    }

    function missingFonts(ops) {
        var seen = {}, out = [];
        if (!app.fonts || !app.fonts.getFontsByPostScriptName) { return out; }
        for (var i = 0; i < ops.length; i++) {
            var f = ops[i].font;
            if (ops[i].op === "text" && !seen[f]) {
                seen[f] = true;
                try { if (app.fonts.getFontsByPostScriptName(f).length === 0) { out.push(f); } } catch (e) { /* older AE: skip */ }
            }
        }
        return out;
    }

    function build(spec, ops) {
        var t0 = new Date().getTime();
        var report = {ok: false};
        ctx = {comp: null, folder: null, layers: {}, warnings: []};
        try {
            if (spec.project && app.project.file && app.project.file.fsName !== new File(spec.project).fsName) {
                throw new Error("A different project is open (" + app.project.file.fsName + "). Open " +
                    spec.project + " or a new, unsaved project, then build again.");
            }
            report.missingFonts = missingFonts(ops);
            ctx.folder = findFolder(ops[0].name, findFolder(spec.folder, null));
            removeSolids(ctx.folder);
            for (var i = 0; i < ops.length; i++) {
                var o = ops[i];
                if (!OPS.hasOwnProperty(o.op)) { throw new Error("unknown op: " + o.op); }
                try { OPS[o.op](o); } catch (e) {
                    throw new Error("op " + i + " (" + o.op + (o.id ? " " + o.id : "") + "): " + e.toString());
                }
            }
            var errs = [];
            for (var j = 1; j <= ctx.comp.numLayers; j++) { checkExpressions(ctx.comp.layer(j), ctx.comp.layer(j).name, errs); }
            report.comp = ctx.comp.name;
            report.layers = ctx.comp.numLayers;
            report.expressionErrors = errs;
            report.warnings = ctx.warnings;
            if (spec.project) {
                app.beginSuppressDialogs();
                try {
                    if (app.project.file) { app.project.save(); } else { app.project.save(new File(spec.project)); }
                } finally { app.endSuppressDialogs(false); }
                report.saved = app.project.file.fsName;
            }
            report.ok = errs.length === 0 && report.missingFonts.length === 0;
        } catch (e) {
            report.error = e.toString();
        }
        report.seconds = (new Date().getTime() - t0) / 1000;
        return toJSON(report);
    }

    return {build: build, toJSON: toJSON, EASE: EASE};
})();
