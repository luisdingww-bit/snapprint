/*!
 * SnapPrint · 3DGS 高斯泼溅模块（纯浏览器，零后端）
 * - fromImage：照片 → 高斯点云（按亮度生成深度，保留像素颜色）
 * - scenes：8 个程序化泼溅场景（确定性随机种子，秒级生成）
 * - exportPLY：标准 3DGS .ply（INRIA 格式，可导入 SuperSplat / Polycam / 各类 splat 查看器）
 * - exportSplat：.splat 紧凑格式（antimatter15 viewer 兼容，每点 32 字节）
 * Apache-2.0 · Copyright 2026 luisdingww-bit
 */
(function (global) {
  "use strict";

  /* ── 工具 ── */
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gaussOf(rnd) {            // Box-Muller
    return function () {
      var u = Math.max(1e-9, rnd()), v = rnd();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    };
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function mix(c1, c2, t) {
    return [Math.round(lerp(c1[0], c2[0], t)), Math.round(lerp(c1[1], c2[1], t)), Math.round(lerp(c1[2], c2[2], t))];
  }

  /** 点云容器：pos(mm, Z-up)、col(RGBA)、scale(mm, 各向) */
  function makeSplat(n) {
    return {
      n: n,
      pos: new Float32Array(n * 3),
      col: new Uint8Array(n * 4),
      scale: new Float32Array(n * 3)
    };
  }
  function setPt(s, i, x, y, z, r, g, b, a, sx, sy, sz) {
    s.pos[i * 3] = x; s.pos[i * 3 + 1] = y; s.pos[i * 3 + 2] = z;
    s.col[i * 4] = r; s.col[i * 4 + 1] = g; s.col[i * 4 + 2] = b; s.col[i * 4 + 3] = a;
    s.scale[i * 3] = sx; s.scale[i * 3 + 1] = sy === undefined ? sx : sy; s.scale[i * 3 + 2] = sz === undefined ? sx : sz;
  }

  /* ── 照片 → 高斯点云 ── */
  /**
   * @param px   RGBA 像素数组（Uint8ClampedArray）
   * @param cols 宽像素  @param rows 高像素
   * @param opts { widthMM, depthMM, count, pointScale, invert }
   */
  function fromImage(px, cols, rows, opts) {
    opts = opts || {};
    var widthMM = opts.widthMM || 80;
    var depthMM = opts.depthMM == null ? 15 : opts.depthMM;
    var count = opts.count || 25000;
    var ps = opts.pointScale || 1;
    var invert = !!opts.invert;
    var depthMMabs = Math.max(0.5, depthMM);

    var step = Math.max(1, Math.floor(Math.sqrt((cols * rows) / count)));
    var gx = Math.floor((cols - 1) / step) + 1, gy = Math.floor((rows - 1) / step) + 1;
    var n = gx * gy;
    var s = makeSplat(n);
    var pxMM = widthMM / cols;                    // 每像素毫米
    var spacing = pxMM * step;                    // 点间距
    var depthWorld = widthMM * (rows / cols);     // 图片纵向毫米
    var base = spacing * 0.62 * ps;               // 高斯基础尺度
    var i = 0;
    for (var yy = 0; yy < rows; yy += step) {
      for (var xx = 0; xx < cols; xx += step) {
        var k = (yy * cols + xx) * 4;
        var R = px[k], G = px[k + 1], B = px[k + 2], A = px[k + 3];
        var g = (0.299 * R + 0.587 * G + 0.114 * B) / 255;
        var h = invert ? 1 - g : g;
        setPt(s, i++,
          xx * pxMM - widthMM / 2,
          depthWorld / 2 - yy * pxMM,             // 图像 y 向下 → 世界 y 向上
          h * depthMMabs,
          R, G, B, Math.max(30, A),
          base, base, Math.max(0.2, base * 0.55));
      }
    }
    s.n = i;
    return s;
  }

  /* ── 程序化泼溅场景 ── */
  var scenes = [
    {
      id: "galaxy", name: "螺旋星系", emoji: "🌌", tag: "宇宙",
      desc: "双旋臂 · 金色核心 · 蓝白外围星带",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), R = 70, s = makeSplat(count);
        for (var i = 0; i < count; i++) {
          var halo = rnd() < 0.12;
          if (halo) {
            var hr = R * (0.5 + rnd() * 0.9);
            var th = rnd() * Math.PI * 2, ph = Math.acos(2 * rnd() - 1);
            setPt(s, i, hr * Math.sin(ph) * Math.cos(th), hr * Math.sin(ph) * Math.sin(th), hr * Math.cos(ph) * 0.5,
              150, 160, 200, 45, 1.6);
            continue;
          }
          var r = R * Math.pow(rnd(), 0.62);
          var arm = (rnd() < 0.5 ? 0 : Math.PI);
          var theta = arm + r * 0.085 + ga() * 0.22;
          var z = ga() * R * 0.035 * (1.15 - r / R * 0.85);
          var t = r / R;
          var c = t < 0.22 ? mix([255, 236, 190], [255, 210, 150], t / 0.22)
                           : (rnd() < 0.06 ? [255, 150, 190] : mix([210, 225, 255], [130, 165, 255], t));
          setPt(s, i, r * Math.cos(theta), r * Math.sin(theta), z,
            c[0], c[1], c[2], t < 0.2 ? 230 : 160, lerp(1.7, 0.9, t));
        }
        return s;
      }
    },
    {
      id: "nebula", name: "猎户星云", emoji: "☁️", tag: "宇宙",
      desc: "多团簇发射星云 · 紫粉青三色",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), s = makeSplat(count);
        var pal = [[172, 108, 255], [255, 105, 180], [90, 200, 250], [120, 120, 255], [255, 160, 120]];
        var C = [], nc = 6;
        for (var c = 0; c < nc; c++) C.push([(rnd() - 0.5) * 80, (rnd() - 0.5) * 80, (rnd() - 0.5) * 55, 10 + rnd() * 16, pal[c % pal.length]]);
        for (var i = 0; i < count; i++) {
          var cl = C[Math.floor(rnd() * nc)];
          var d = Math.abs(ga());
          var col0 = cl[4], col = mix(col0, [255, 255, 255], Math.max(0, 0.55 - d * 0.35));
          setPt(s, i, cl[0] + ga() * cl[3], cl[1] + ga() * cl[3], cl[2] + ga() * cl[3] * 0.7,
            col[0], col[1], col[2], Math.max(28, 150 - d * 55), lerp(2.6, 1.1, Math.min(1, d / 2.2)));
        }
        return s;
      }
    },
    {
      id: "fireworks", name: "烟花绽放", emoji: "🎆", tag: "节日",
      desc: "五连发空中礼花 · 金红蓝绿紫",
      gen: function (count, rnd) {
        var s = makeSplat(count);
        var cols5 = [[255, 200, 80], [255, 90, 90], [110, 170, 255], [120, 235, 140], [210, 130, 255]];
        var B = [], nb = 5;
        for (var b = 0; b < nb; b++) B.push([(rnd() - 0.5) * 90, (rnd() - 0.5) * 60, 45 + rnd() * 55, 14 + rnd() * 18, cols5[b]]);
        for (var i = 0; i < count; i++) {
          var bu = B[Math.floor(rnd() * nb)];
          var th = rnd() * Math.PI * 2, ph = Math.acos(2 * rnd() - 1);
          var t = Math.pow(rnd(), 0.42);                 // 沿射线的拖尾
          var rr = bu[3] * t;
          var dz = -t * t * bu[3] * 0.35;                // 重力下坠
          var c = mix([255, 255, 255], bu[4], Math.min(1, t * 1.3));
          setPt(s, i,
            bu[0] + rr * Math.sin(ph) * Math.cos(th),
            bu[1] + rr * Math.sin(ph) * Math.sin(th),
            bu[2] + rr * Math.cos(ph) + dz,
            c[0], c[1], c[2], Math.round(lerp(240, 60, t)), lerp(1.5, 0.55, t));
        }
        return s;
      }
    },
    {
      id: "sakura", name: "樱花树", emoji: "🌸", tag: "自然",
      desc: "棕干粉冠 · 花瓣飘落",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), s = makeSplat(count);
        var pinks = [[255, 183, 197], [255, 140, 170], [255, 214, 224], [250, 160, 190]];
        for (var i = 0; i < count; i++) {
          var u = rnd();
          if (u < 0.16) {                                 // 树干 + 分枝
            var t = rnd(), bend = Math.sin(t * 2.2) * 6;
            var rad = lerp(5.5, 1.4, t);
            setPt(s, i, bend + ga() * rad * 0.5, ga() * rad * 0.5, t * 52,
              120 + Math.round(rnd() * 25), 78 + Math.round(rnd() * 18), 48, 235, 1.6);
          } else if (u < 0.92) {                          // 花冠（3 团）
            var cx = [-14, 12, 0][Math.floor(rnd() * 3)], cy = (rnd() - 0.5) * 22;
            var cz = 58 + [0, 4, 12][Math.floor(rnd() * 3)];
            var p = pinks[Math.floor(rnd() * pinks.length)];
            setPt(s, i, cx + ga() * 15, cy + ga() * 13, cz + ga() * 10,
              p[0], p[1], p[2], 165, 1.8);
          } else {                                        // 飘落花瓣
            var p2 = pinks[Math.floor(rnd() * pinks.length)];
            setPt(s, i, (rnd() - 0.5) * 70, (rnd() - 0.5) * 70, rnd() * 55,
              p2[0], p2[1], p2[2], 120, 0.9);
          }
        }
        return s;
      }
    },
    {
      id: "heart", name: "爱心星尘", emoji: "💗", tag: "浪漫",
      desc: "立体心形点云 · 渐变粉红 + 星光",
      gen: function (count, rnd) {
        var s = makeSplat(count), i = 0, guard = 0;
        while (i < count && guard < count * 60) {
          guard++;
          var x = (rnd() * 2 - 1) * 1.4, y = (rnd() * 2 - 1) * 1.4, z = (rnd() * 2 - 1) * 1.4;
          // 心形隐式曲面 (x²+9/4·y²+z²-1)³ - x²z³ - 9/80·y²z³ ≤ 0
          var q = x * x + 2.25 * y * y + z * z - 1;
          if (q * q * q - x * x * z * z * z - 0.1125 * y * y * z * z * z > 0) continue;
          var t = (z + 1.1) / 2.2;
          var spark = rnd() < 0.05;
          var c = spark ? [255, 255, 255] : mix([255, 60, 110], [255, 170, 200], t);
          setPt(s, i++, x * 34, y * 34, z * 34 + 38,
            c[0], c[1], c[2], spark ? 255 : 175, spark ? 0.8 : 1.5);
        }
        s.n = i;
        return s;
      }
    },
    {
      id: "saturn", name: "土星环", emoji: "🪐", tag: "宇宙",
      desc: "带状星球 + 三层光环",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), s = makeSplat(count);
        for (var i = 0; i < count; i++) {
          if (rnd() < 0.55) {                             // 球体（纬度条带）
            var th = rnd() * Math.PI * 2, ph = Math.acos(2 * rnd() - 1);
            var R = 30 + ga() * 0.4;
            var lat = Math.cos(ph);
            var band = Math.sin(lat * 9) * 0.5 + 0.5;
            var c = mix([222, 195, 150], [180, 150, 110], band);
            setPt(s, i, R * Math.sin(ph) * Math.cos(th), R * Math.sin(ph) * Math.sin(th), R * lat,
              c[0], c[1], c[2], 235, 1.5);
          } else {                                        // 光环
            var rr = 40 + rnd() * 22;
            var a = rnd() * Math.PI * 2;
            var ringT = (rr - 40) / 22;
            var gap = ringT > 0.55 && ringT < 0.66;       // 卡西尼缝
            var c2 = mix([210, 190, 160], [140, 130, 120], Math.sin(ringT * 14) * 0.5 + 0.5);
            setPt(s, i, rr * Math.cos(a), rr * Math.sin(a), ga() * 0.5,
              c2[0], c2[1], c2[2], gap ? 30 : 150, 1.0);
          }
        }
        return s;
      }
    },
    {
      id: "fountain", name: "许愿喷泉", emoji: "⛲", tag: "城市",
      desc: "八股水柱抛物线 · 池面涟漪",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), s = makeSplat(count);
        for (var i = 0; i < count; i++) {
          var u = rnd();
          if (u < 0.62) {                                 // 水柱
            var jet = Math.floor(rnd() * 8), a = jet / 8 * Math.PI * 2 + 0.12 * ga();
            var t = rnd();
            var rr = t * 34;
            var z = 8 + 52 * t * (1.55 - t) * 1.4;        // 抛物线
            var c = mix([235, 250, 255], [120, 190, 245], t);
            setPt(s, i, rr * Math.cos(a) + ga() * 1.2, rr * Math.sin(a) + ga() * 1.2, z,
              c[0], c[1], c[2], Math.round(lerp(230, 110, t)), lerp(1.1, 1.9, t));
          } else if (u < 0.9) {                           // 池面
            var pr = 26 + rnd() * 16, pa = rnd() * Math.PI * 2;
            var rip = Math.sin(pr * 1.1) * 0.5 + 0.5;
            var c2 = mix([70, 140, 210], [150, 210, 250], rip);
            setPt(s, i, pr * Math.cos(pa), pr * Math.sin(pa), 1.5 + ga() * 0.4,
              c2[0], c2[1], c2[2], 190, 1.6);
          } else {                                        // 中央水花
            setPt(s, i, ga() * 3, ga() * 3, 60 + ga() * 6, 255, 255, 255, 200, 1.0);
          }
        }
        return s;
      }
    },
    {
      id: "aurora", name: "北极极光", emoji: "🌠", tag: "自然",
      desc: "三层舞动光幕 · 绿紫渐变",
      gen: function (count, rnd) {
        var ga = gaussOf(rnd), s = makeSplat(count);
        for (var i = 0; i < count; i++) {
          if (rnd() < 0.1) {                              // 星空背景
            setPt(s, i, (rnd() - 0.5) * 160, (rnd() - 0.5) * 100, 30 + rnd() * 80,
              255, 255, 255, 90 + Math.floor(rnd() * 120), 0.5);
            continue;
          }
          var layer = Math.floor(rnd() * 3);
          var x = (rnd() - 0.5) * 150;
          var wave = Math.sin(x * 0.05 + layer * 2.1) * 14 + Math.sin(x * 0.13 + layer) * 6;
          var y = layer * 16 - 16 + wave + ga() * 2.2;
          var t = Math.pow(rnd(), 1.6);                   // 底部密、顶部散
          var z = 24 + t * 85 + ga() * 3;
          var c = t < 0.4 ? mix([80, 255, 160], [60, 230, 190], t / 0.4)
                          : mix([60, 230, 190], [180, 110, 255], (t - 0.4) / 0.6);
          setPt(s, i, x, y, z, c[0], c[1], c[2],
            Math.round(lerp(190, 40, t)), lerp(1.4, 2.6, t));
        }
        return s;
      }
    }
  ];

  function byId(id) {
    for (var i = 0; i < scenes.length; i++) if (scenes[i].id === id) return scenes[i];
    return null;
  }

  /** 生成场景点云 @param opts { count, pointScale, seed } */
  function buildScene(id, opts) {
    var sc = byId(id);
    if (!sc) throw new Error("未知场景：" + id);
    opts = opts || {};
    var count = Math.max(1000, Math.min(120000, opts.count || 24000));
    var rnd = mulberry32(opts.seed == null ? 20260724 + id.length * 131 : opts.seed);
    var s = sc.gen(count, rnd);
    if (opts.pointScale && opts.pointScale !== 1) {
      for (var i = 0; i < s.n * 3; i++) s.scale[i] *= opts.pointScale;
    }
    s.name = id;
    return s;
  }

  /* ── 导出：标准 3DGS .ply（INRIA 格式，SH 0 阶） ── */
  var SH_C0 = 0.28209479177387814;
  function exportPLY(s) {
    var n = s.n;
    var header =
      "ply\nformat binary_little_endian 1.0\n" +
      "element vertex " + n + "\n" +
      "property float x\nproperty float y\nproperty float z\n" +
      "property float nx\nproperty float ny\nproperty float nz\n" +
      "property float f_dc_0\nproperty float f_dc_1\nproperty float f_dc_2\n" +
      "property float opacity\n" +
      "property float scale_0\nproperty float scale_1\nproperty float scale_2\n" +
      "property float rot_0\nproperty float rot_1\nproperty float rot_2\nproperty float rot_3\n" +
      "end_header\n";
    var hb = new TextEncoder().encode(header);
    var stride = 17 * 4;
    var buf = new ArrayBuffer(hb.length + n * stride);
    new Uint8Array(buf).set(hb, 0);
    var dv = new DataView(buf, hb.length);
    for (var i = 0; i < n; i++) {
      var o = i * stride;
      // mm Z-up → 常见 viewer 坐标（Y-down）：(x, -z, y) / 100
      dv.setFloat32(o, s.pos[i * 3] / 100, true);
      dv.setFloat32(o + 4, -s.pos[i * 3 + 2] / 100, true);
      dv.setFloat32(o + 8, s.pos[i * 3 + 1] / 100, true);
      dv.setFloat32(o + 12, 0, true); dv.setFloat32(o + 16, 0, true); dv.setFloat32(o + 20, 0, true);
      for (var c = 0; c < 3; c++)
        dv.setFloat32(o + 24 + c * 4, (s.col[i * 4 + c] / 255 - 0.5) / SH_C0, true);
      var a = Math.min(1 - 1e-4, Math.max(1e-4, s.col[i * 4 + 3] / 255));
      dv.setFloat32(o + 36, Math.log(a / (1 - a)), true);                  // inverse sigmoid
      dv.setFloat32(o + 40, Math.log(Math.max(1e-6, s.scale[i * 3] / 100)), true);
      dv.setFloat32(o + 44, Math.log(Math.max(1e-6, s.scale[i * 3 + 1] / 100)), true);
      dv.setFloat32(o + 48, Math.log(Math.max(1e-6, s.scale[i * 3 + 2] / 100)), true);
      dv.setFloat32(o + 52, 1, true); dv.setFloat32(o + 56, 0, true);      // 单位四元数
      dv.setFloat32(o + 60, 0, true); dv.setFloat32(o + 64, 0, true);
    }
    return buf;
  }

  /* ── 导出：.splat 紧凑格式（antimatter15，每点 32 字节） ── */
  function exportSplat(s) {
    var n = s.n;
    var buf = new ArrayBuffer(n * 32);
    var dv = new DataView(buf);
    var u8 = new Uint8Array(buf);
    for (var i = 0; i < n; i++) {
      var o = i * 32;
      dv.setFloat32(o, s.pos[i * 3] / 100, true);
      dv.setFloat32(o + 4, -s.pos[i * 3 + 2] / 100, true);
      dv.setFloat32(o + 8, s.pos[i * 3 + 1] / 100, true);
      dv.setFloat32(o + 12, s.scale[i * 3] / 100, true);
      dv.setFloat32(o + 16, s.scale[i * 3 + 1] / 100, true);
      dv.setFloat32(o + 20, s.scale[i * 3 + 2] / 100, true);
      u8[o + 24] = s.col[i * 4]; u8[o + 25] = s.col[i * 4 + 1];
      u8[o + 26] = s.col[i * 4 + 2]; u8[o + 27] = s.col[i * 4 + 3];
      u8[o + 28] = 255; u8[o + 29] = 128; u8[o + 30] = 128; u8[o + 31] = 128;  // 单位四元数
    }
    return buf;
  }

  /** 点云包围盒尺寸（mm）与点数 */
  function statsSplat(s) {
    var mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
    for (var i = 0; i < s.n; i++)
      for (var c = 0; c < 3; c++) {
        var v = s.pos[i * 3 + c];
        if (v < mn[c]) mn[c] = v;
        if (v > mx[c]) mx[c] = v;
      }
    return { points: s.n, size_mm: [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]] };
  }

  global.SnapPrintSplat = {
    fromImage: fromImage,
    scenes: scenes,
    byId: byId,
    buildScene: buildScene,
    exportPLY: exportPLY,
    exportSplat: exportSplat,
    statsSplat: statsSplat
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
