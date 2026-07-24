/*!
 * SnapPrint · 切片就绪预设模块（纯浏览器，零后端）
 * - analyze(V, F, opt)：分析网格几何 → 推荐切片参数（层高/填充/支撑/brim/超床警告）
 * - exportINI(rec, printerId, matId, name)：导出 PrusaSlicer 兼容 .ini（OrcaSlicer 亦可导入）
 * - exportTXT(rec, printerId, matId, name)：导出中文可读参数卡
 * 暴露 global.SnapPrintPresets = { printers, materials, analyze, exportINI, exportTXT }
 */
(function (global) {
  "use strict";

  /* —— 常见打印机（热床尺寸 mm、喷嘴、速度档）—— */
  var PRINTERS = [
    { id: "bambu_a1",     name: "拓竹 Bambu Lab A1",      bed: [256, 256, 256], nozzle: 0.4, fast: true },
    { id: "bambu_a1mini", name: "拓竹 Bambu Lab A1 mini", bed: [180, 180, 180], nozzle: 0.4, fast: true },
    { id: "bambu_p1s",    name: "拓竹 P1S / X1C",         bed: [256, 256, 256], nozzle: 0.4, fast: true },
    { id: "ender3v3",     name: "创想三维 Ender-3 V3",     bed: [220, 220, 250], nozzle: 0.4, fast: true },
    { id: "k1c",          name: "创想三维 K1C",            bed: [220, 220, 250], nozzle: 0.4, fast: true },
    { id: "prusa_mk4s",   name: "Prusa MK4S",             bed: [250, 210, 220], nozzle: 0.4, fast: true },
    { id: "neptune4",     name: "Elegoo Neptune 4 Pro",   bed: [225, 225, 265], nozzle: 0.4, fast: true },
    { id: "kobra3",       name: "Anycubic Kobra 3",       bed: [250, 250, 260], nozzle: 0.4, fast: true },
    { id: "generic",      name: "通用 FDM（0.4 喷嘴）",     bed: [220, 220, 250], nozzle: 0.4, fast: false }
  ];

  /* —— 材料预设（喷嘴/热床温度 °C、风扇 %）—— */
  var MATERIALS = [
    { id: "pla",  name: "PLA",     nozzle: 215, nozzleFirst: 220, bed: 60, bedFirst: 60, fanMin: 80, fanMax: 100, density: 1.24 },
    { id: "petg", name: "PETG",    nozzle: 245, nozzleFirst: 250, bed: 75, bedFirst: 80, fanMin: 30, fanMax: 50,  density: 1.27 },
    { id: "tpu",  name: "TPU 95A", nozzle: 225, nozzleFirst: 230, bed: 45, bedFirst: 50, fanMin: 40, fanMax: 60,  density: 1.21, slow: true }
  ];

  function byId(list, id) {
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return list[list.length - 1];
  }

  /* ============================================================
   * 几何分析：V=[[x,y,z]...] (mm, Z-up)，F=[[a,b,c]...]
   * 返回推荐参数对象 rec
   * ============================================================ */
  function analyze(V, F, opt) {
    opt = opt || {};
    var mode = opt.mode || "relief"; // relief / extrude / solid3d / import
    var i, j;

    /* 包围盒 */
    var mn = [1e18, 1e18, 1e18], mx = [-1e18, -1e18, -1e18];
    for (i = 0; i < V.length; i++) {
      for (j = 0; j < 3; j++) {
        if (V[i][j] < mn[j]) mn[j] = V[i][j];
        if (V[i][j] > mx[j]) mx[j] = V[i][j];
      }
    }
    var size = [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]];
    var maxDim = Math.max(size[0], size[1], size[2]);
    var footMin = Math.min(size[0], size[1]);

    /* 逐面：法线 → 悬垂面积 / 底面接触面积 / 总面积 / 体积 */
    var areaTotal = 0, areaOverhang = 0, areaContact = 0, vol6 = 0;
    var COS45 = Math.SQRT1_2; // cos(45°)
    for (i = 0; i < F.length; i++) {
      var a = V[F[i][0]], b = V[F[i][1]], c = V[F[i][2]];
      var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
      var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
      var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      var len = Math.sqrt(nx * nx + ny * ny + nz * nz);
      if (len < 1e-12) continue;
      var area = len / 2;
      areaTotal += area;
      var cosDown = -nz / len; // 与 -Z 的夹角余弦（朝下程度）
      var minZ = Math.min(a[2], b[2], c[2]) - mn[2];
      if (cosDown > 0.999 && minZ < 0.5) {
        areaContact += area;                 // 贴床底面
      } else if (cosDown > COS45 && minZ > 1.0) {
        areaOverhang += area;                // 悬垂 >45° 且不贴床
      }
      vol6 += a[0] * (b[1] * c[2] - c[1] * b[2])
            - b[0] * (a[1] * c[2] - c[1] * a[2])
            + c[0] * (a[1] * b[2] - b[1] * a[2]);
    }
    var volumeCm3 = Math.abs(vol6 / 6) / 1000;
    var overhangRatio = areaTotal > 0 ? areaOverhang / areaTotal : 0;
    var footprint = size[0] * size[1];
    var contactRatio = footprint > 0 ? areaContact / footprint : 1;

    /* —— 推荐规则 —— */
    // 支撑：浮雕/拉伸天然自支撑；其它看悬垂面积占比
    var supports = false, supportReason = "自支撑几何，无需支撑";
    if (mode !== "relief" && mode !== "extrude") {
      if (overhangRatio > 0.03) {
        supports = true;
        supportReason = "悬垂(>45°)面积占 " + (overhangRatio * 100).toFixed(1) + "%，建议开启支撑";
      } else {
        supportReason = "悬垂面积仅 " + (overhangRatio * 100).toFixed(1) + "%，可免支撑";
      }
    }

    // 层高：小件/浮雕细节 → 0.12；常规 → 0.2
    var layer = 0.2, layerWhy = "标准精度";
    if (maxDim <= 45 || mode === "relief") { layer = 0.12; layerWhy = maxDim <= 45 ? "小尺寸模型，提升细节" : "浮雕细节优先"; }
    else if (maxDim >= 150) { layer = 0.28; layerWhy = "大件提速"; }

    // 填充：默认 15%；大件 10%；微小件 25%
    var infill = 15;
    if (volumeCm3 >= 80) infill = 10;
    else if (volumeCm3 <= 2) infill = 25;

    // brim：接触面小或细高比大 → 开
    var tallRatio = footMin > 0 ? size[2] / footMin : 0;
    var brim = 0, brimWhy = "接触面充足，无需 brim";
    if (contactRatio < 0.15 || tallRatio > 2.5) {
      brim = 5;
      brimWhy = contactRatio < 0.15 ? "贴床面积小(" + (contactRatio * 100).toFixed(0) + "%)，加 5mm brim 防翘" : "细高件(高/宽=" + tallRatio.toFixed(1) + ")，加 5mm brim 防倒";
    }

    // 料重估算（外壳+填充的粗略折算系数）
    var solidFactor = 0.30 + 0.70 * (infill / 100);

    return {
      mode: mode,
      size_mm: size,
      volume_cm3: volumeCm3,
      overhang_ratio: overhangRatio,
      contact_ratio: contactRatio,
      layer_height: layer, layer_why: layerWhy,
      first_layer_height: Math.max(layer, 0.2),
      infill: infill,
      perimeters: 2, top_layers: 4, bottom_layers: 3,
      supports: supports, support_reason: supportReason,
      brim_mm: brim, brim_why: brimWhy,
      solid_factor: solidFactor
    };
  }

  /* 料重（g）与粗略耗时估算，依赖材料密度 */
  function estimate(rec, mat) {
    var grams = rec.volume_cm3 * mat.density * rec.solid_factor;
    // 粗略时间：按 12 mm^3/s（快速机）折算实体挤出量
    var mm3 = rec.volume_cm3 * 1000 * rec.solid_factor;
    var minutes = mm3 / 12 / 60 + rec.size_mm[2] / rec.layer_height * 0.02; // 加层切换开销
    return { grams: grams, minutes: minutes };
  }

  function fit(rec, printer) {
    var s = rec.size_mm, b = printer.bed;
    // 允许水平旋转：footprint 长短边 vs 床长短边
    var f1 = Math.max(s[0], s[1]), f2 = Math.min(s[0], s[1]);
    var b1 = Math.max(b[0], b[1]), b2 = Math.min(b[0], b[1]);
    var ok = f1 <= b1 && f2 <= b2 && s[2] <= b[2];
    return { ok: ok, bed: b };
  }

  /* ============================================================
   * PrusaSlicer 兼容 .ini（文件 → 导入 → 导入配置；OrcaSlicer 同样支持）
   * ============================================================ */
  function exportINI(rec, printerId, matId, name) {
    var p = byId(PRINTERS, printerId), m = byId(MATERIALS, matId);
    var est = estimate(rec, m);
    var ft = fit(rec, p);
    var L = [];
    L.push("# SnapPrint 咔印3D · 切片就绪预设 (PrusaSlicer/OrcaSlicer 可导入)");
    L.push("# 模型: " + (name || "model") + "  模式: " + rec.mode);
    L.push("# 尺寸: " + rec.size_mm.map(function (x) { return x.toFixed(1); }).join(" x ") + " mm  体积: " + rec.volume_cm3.toFixed(1) + " cm3");
    L.push("# 打印机: " + p.name + "  材料: " + m.name);
    L.push("# 估算: 约 " + est.grams.toFixed(0) + " g / " + (est.minutes / 60).toFixed(1) + " h（粗略）");
    if (!ft.ok) L.push("# !! 警告: 模型超出热床 " + ft.bed.join("x") + " mm，请缩放后再切片");
    L.push("# " + rec.support_reason + " | " + rec.brim_why);
    L.push("");
    L.push("layer_height = " + rec.layer_height);
    L.push("first_layer_height = " + rec.first_layer_height);
    L.push("perimeters = " + rec.perimeters);
    L.push("top_solid_layers = " + rec.top_layers);
    L.push("bottom_solid_layers = " + rec.bottom_layers);
    L.push("fill_density = " + rec.infill + "%");
    L.push("fill_pattern = gyroid");
    L.push("support_material = " + (rec.supports ? 1 : 0));
    L.push("support_material_auto = " + (rec.supports ? 1 : 0));
    L.push("support_material_threshold = 45");
    L.push("brim_type = " + (rec.brim_mm > 0 ? "outer_only" : "no_brim"));
    L.push("brim_width = " + rec.brim_mm);
    L.push("skirts = 1");
    L.push("temperature = " + m.nozzle);
    L.push("first_layer_temperature = " + m.nozzleFirst);
    L.push("bed_temperature = " + m.bed);
    L.push("first_layer_bed_temperature = " + m.bedFirst);
    L.push("min_fan_speed = " + m.fanMin);
    L.push("max_fan_speed = " + m.fanMax);
    L.push("nozzle_diameter = " + p.nozzle);
    L.push("bed_shape = 0x0," + p.bed[0] + "x0," + p.bed[0] + "x" + p.bed[1] + ",0x" + p.bed[1]);
    L.push("max_print_height = " + p.bed[2]);
    if (m.slow) {
      L.push("perimeter_speed = 25");
      L.push("infill_speed = 30");
      L.push("first_layer_speed = 15");
    } else if (p.fast) {
      L.push("perimeter_speed = 120");
      L.push("infill_speed = 200");
      L.push("first_layer_speed = 50");
    } else {
      L.push("perimeter_speed = 45");
      L.push("infill_speed = 60");
      L.push("first_layer_speed = 20");
    }
    return L.join("\n") + "\n";
  }

  /* 中文可读参数卡（.txt） */
  function exportTXT(rec, printerId, matId, name) {
    var p = byId(PRINTERS, printerId), m = byId(MATERIALS, matId);
    var est = estimate(rec, m);
    var ft = fit(rec, p);
    var L = [];
    L.push("========================================");
    L.push(" SnapPrint 咔印3D · 切片参数推荐卡");
    L.push("========================================");
    L.push("模型　　：" + (name || "model") + "（" + rec.mode + " 模式）");
    L.push("尺寸　　：" + rec.size_mm.map(function (x) { return x.toFixed(1); }).join(" × ") + " mm");
    L.push("体积　　：" + rec.volume_cm3.toFixed(1) + " cm³");
    L.push("打印机　：" + p.name + "（热床 " + p.bed.join("×") + " mm）");
    L.push("材料　　：" + m.name);
    L.push("----------------------------------------");
    L.push("层高　　：" + rec.layer_height + " mm（" + rec.layer_why + "）");
    L.push("壁厚　　：" + rec.perimeters + " 圈壁 / 顶 " + rec.top_layers + " 层 / 底 " + rec.bottom_layers + " 层");
    L.push("填充　　：" + rec.infill + "%（gyroid 螺旋二十四面体）");
    L.push("支撑　　：" + (rec.supports ? "✅ 开启（阈值 45°）" : "❌ 不需要") + " —— " + rec.support_reason);
    L.push("Brim　 ：" + (rec.brim_mm > 0 ? rec.brim_mm + " mm" : "关闭") + " —— " + rec.brim_why);
    L.push("温度　　：喷嘴 " + m.nozzle + "°C（首层 " + m.nozzleFirst + "°C）/ 热床 " + m.bed + "°C");
    L.push("估算　　：约 " + est.grams.toFixed(0) + " g 耗材 / " + (est.minutes / 60).toFixed(1) + " 小时（粗略）");
    if (!ft.ok) L.push("⚠️ 警告：模型超出热床尺寸，请先缩放！");
    L.push("----------------------------------------");
    L.push("使用方法：");
    L.push("1. PrusaSlicer：文件 → 导入 → 导入配置，选同名 .ini");
    L.push("2. OrcaSlicer ：文件 → 导入 → 导入配置");
    L.push("3. 拓竹/其它切片器：按上表手动设置即可");
    L.push("由 SnapPrint 咔印3D 生成 · https://snapprint-3d.surge.sh");
    return L.join("\n") + "\n";
  }

  global.SnapPrintPresets = {
    printers: PRINTERS,
    materials: MATERIALS,
    analyze: analyze,
    estimate: estimate,
    fit: fit,
    exportINI: exportINI,
    exportTXT: exportTXT
  };
})(typeof window !== "undefined" ? window : globalThis);
