/**
 * SnapPrint 模型画廊 —— 内置精选模型（程序化生成，原创、Apache-2.0，可自由商用）
 *
 * 每个条目提供 heightmap(cols,rows) => {hts, cls}：
 *   hts: 0~1 高度数组(行优先)，cls: [r,g,b] 颜色数组
 * 由 SnapPrintCore.buildRelief 转成水密可打印网格。
 *
 * 说明：不直接内嵌第三方网站的模型文件（版权/许可不可控），
 *       外部灵感社区以链接形式在页面导航区提供。
 */
(function (global) {
  "use strict";

  /* ---------- 小工具 ---------- */
  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
  function smooth(t) { return t * t * (3 - 2 * t); }
  function mix(a, b, t) { return a + (b - a) * t; }

  /** 确定性伪随机（同一模型每次生成完全一致） */
  function makeRand(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  /** 值噪声 + fBm（用于地形类模型） */
  function makeNoise(seed) {
    var rand = makeRand(seed);
    var G = 64, grid = new Array(G * G);
    for (var i = 0; i < G * G; i++) grid[i] = rand();
    function at(ix, iy) { return grid[((iy % G + G) % G) * G + ((ix % G + G) % G)]; }
    function noise(x, y) {
      var ix = Math.floor(x), iy = Math.floor(y);
      var fx = smooth(x - ix), fy = smooth(y - iy);
      return mix(mix(at(ix, iy), at(ix + 1, iy), fx),
                 mix(at(ix, iy + 1), at(ix + 1, iy + 1), fx), fy);
    }
    return function fbm(x, y, oct) {
      var v = 0, amp = 0.5, f = 1;
      for (var o = 0; o < (oct || 4); o++) { v += amp * noise(x * f, y * f); amp *= 0.5; f *= 2; }
      return v;
    };
  }

  /** 通用包装：以中心归一坐标 (u,v ∈ -1..1) 求高度和颜色 */
  function fromUV(cols, rows, fn) {
    var n = cols * rows, hts = new Array(n), cls = new Array(n);
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var u = (c / (cols - 1)) * 2 - 1;
        var v = (r / (rows - 1)) * 2 - 1;
        var res = fn(u, v);
        var i = r * cols + c;
        hts[i] = clamp01(res[0]);
        cls[i] = res[1];
      }
    }
    return { hts: hts, cls: cls };
  }

  /* ---------- 9 个精选模型 ---------- */

  /** 1. 爱心浮雕 —— 情人节挂件/冰箱贴 */
  function heart(cols, rows) {
    return fromUV(cols, rows, function (u, v) {
      var x = u * 1.3, y = -v * 1.3 + 0.15;
      // 心形隐式方程 (x^2+y^2-1)^3 - x^2*y^3 <= 0
      var f = Math.pow(x * x + y * y - 1, 3) - x * x * y * y * y;
      if (f <= 0) {
        var d = clamp01(-f * 1.6);                 // 越靠内越高
        var h = 0.35 + 0.65 * Math.pow(d, 0.45);
        return [h, [232, mix(46, 90, h), mix(74, 110, h)]];
      }
      return [0.06, [250, 235, 238]];
    });
  }

  /** 2. 五角星奖章 —— 奖励/徽章 */
  function star(cols, rows) {
    return fromUV(cols, rows, function (u, v) {
      var r = Math.sqrt(u * u + v * v), a = Math.atan2(v, u);
      // 五角星极径
      var k = Math.PI / 5;
      var m = ((a + Math.PI / 2) % (2 * k) + 2 * k) % (2 * k) - k;
      var starR = 0.82 * Math.cos(k) / Math.cos(m);
      var inStar = r < starR * 0.92;
      var ring = r > 0.88 && r < 0.99;              // 外圈环
      if (ring) return [0.55, [212, 175, 55]];
      if (inStar) {
        var d = clamp01(1 - r / (starR * 0.92));
        var h = 0.45 + 0.55 * Math.pow(d, 0.6);
        return [h, [255, mix(196, 226, d), mix(64, 120, d)]];
      }
      if (r < 0.99) return [0.28, [64, 82, 130]];   // 底盘
      return [0.05, [240, 243, 248]];
    });
  }

  /** 3. 层峦山地 —— 桌面地形摆件 */
  function mountains(cols, rows) {
    var fbm = makeNoise(20260724);
    return fromUV(cols, rows, function (u, v) {
      var e = fbm(u * 2.2 + 5, v * 2.2 + 9, 5);
      e = Math.pow(clamp01((e - 0.28) / 0.62), 1.25);
      var edge = clamp01(1.4 - Math.max(Math.abs(u), Math.abs(v)) * 1.45); // 边缘渐低
      var h = 0.08 + 0.9 * e * smooth(edge);
      var col;
      if (h < 0.22) col = [64, 118, 168];            // 湖水
      else if (h < 0.4) col = [96, 156, 92];         // 草甸
      else if (h < 0.62) col = [122, 112, 92];       // 山坡
      else if (h < 0.82) col = [150, 140, 128];      // 岩石
      else col = [245, 248, 250];                    // 雪顶
      return [h, col];
    });
  }

  /** 4. 水波涟漪 —— 杯垫（同心波+干涉） */
  function ripple(cols, rows) {
    return fromUV(cols, rows, function (u, v) {
      var d1 = Math.sqrt((u - 0.35) * (u - 0.35) + (v - 0.25) * (v - 0.25));
      var d2 = Math.sqrt((u + 0.4) * (u + 0.4) + (v + 0.3) * (v + 0.3));
      var w = Math.sin(d1 * 18) * 0.5 + Math.sin(d2 * 15) * 0.5;
      var r = Math.sqrt(u * u + v * v);
      if (r > 0.98) return [0.04, [235, 242, 248]];
      var h = 0.35 + 0.3 * w * clamp01(1.15 - r);
      var t = clamp01((w + 1) / 2);
      return [h, [mix(38, 120, t), mix(110, 190, t), mix(180, 235, t)]];
    });
  }

  /** 5. 工业齿轮 —— 机械风挂件 */
  function gear(cols, rows) {
    var TEETH = 12;
    return fromUV(cols, rows, function (u, v) {
      var r = Math.sqrt(u * u + v * v), a = Math.atan2(v, u);
      var tooth = 0.78 + 0.13 * (Math.abs(((a * TEETH / (2 * Math.PI)) % 1) * 2 - 1) < 0.52 ? 1 : 0);
      if (r < 0.16) return [0.15, [50, 56, 66]];                 // 轴孔
      if (r < 0.30) return [0.85, [188, 196, 206]];              // 轴毂
      if (r < 0.42) {
        // 减重孔(6个)
        var hole = Math.abs(((a * 3 / Math.PI + 0.5) % 1) * 2 - 1) < 0.45 && r > 0.33;
        return hole ? [0.15, [50, 56, 66]] : [0.62, [150, 158, 170]];
      }
      if (r < tooth) return [0.85, [188, 196, 206]];             // 齿身
      return [0.05, [32, 36, 44]];
    });
  }

  /** 6. 蜂窝六边形 —— 几何杯垫/收纳垫 */
  function honeycomb(cols, rows) {
    function hexDist(x, y) {  // 到最近六边形中心的归一距离
      var q = (x * Math.sqrt(3) / 3 - y / 3), rr = y * 2 / 3;
      var cx = q, cz = rr, cy = -cx - cz;
      var rx = Math.round(cx), ry = Math.round(cy), rz = Math.round(cz);
      var dx = Math.abs(rx - cx), dy = Math.abs(ry - cy), dz = Math.abs(rz - cz);
      if (dx > dy && dx > dz) rx = -ry - rz; else if (dy <= dz) rz = -rx - ry;
      var hx = Math.sqrt(3) * (rx + rz / 2), hy = 1.5 * rz;
      var px = x - hx, py = y - hy;
      // 六边形边距（点到边）
      px = Math.abs(px); py = Math.abs(py);
      return Math.max(px * Math.sqrt(3) / 2 + py / 2, py) / 0.866;
    }
    return fromUV(cols, rows, function (u, v) {
      var s = 4.2;
      var d = hexDist(u * s, v * s);
      var wall = d > 0.78 && d < 1.0;
      var rim = Math.max(Math.abs(u), Math.abs(v)) > 0.96;
      if (rim) return [0.5, [240, 170, 60]];
      if (wall) return [0.85, [240, 170, 60]];
      var t = clamp01(1 - d);
      return [0.3 + 0.1 * t, [mix(52, 84, t), mix(46, 62, t), mix(40, 46, t)]];
    });
  }

  /** 7. 曼陀罗花纹 —— 装饰浮雕盘 */
  function mandala(cols, rows) {
    return fromUV(cols, rows, function (u, v) {
      var r = Math.sqrt(u * u + v * v), a = Math.atan2(v, u);
      if (r > 0.98) return [0.05, [246, 240, 250]];
      var w = Math.sin(a * 8) * Math.sin(r * 14 - 1.2) +
              0.6 * Math.sin(a * 16 + r * 6) +
              0.8 * Math.cos(r * 9);
      var t = clamp01((w + 2.4) / 4.8);
      var petal = Math.pow(t, 1.3);
      var h = 0.25 + 0.6 * petal * clamp01(1.25 - r);
      return [h, [mix(96, 214, petal), mix(56, 120, petal), mix(148, 226, petal)]];
    });
  }

  /** 8. 月球表面 —— 陨石坑浮雕（教学/摆件） */
  function moon(cols, rows) {
    var rand = makeRand(19690720);
    var craters = [];
    for (var i = 0; i < 26; i++) {
      craters.push({ x: rand() * 2 - 1, y: rand() * 2 - 1, r: 0.05 + rand() * 0.22, d: 0.35 + rand() * 0.65 });
    }
    var fbm = makeNoise(11);
    return fromUV(cols, rows, function (u, v) {
      var R = Math.sqrt(u * u + v * v);
      if (R > 0.97) return [0.05, [16, 18, 26]];
      var h = 0.55 + 0.12 * fbm(u * 3 + 7, v * 3 + 3, 4);
      for (var k = 0; k < craters.length; k++) {
        var cr = craters[k];
        var d = Math.sqrt((u - cr.x) * (u - cr.x) + (v - cr.y) * (v - cr.y)) / cr.r;
        if (d < 1.25) {
          if (d < 0.85) h -= cr.d * 0.28 * (1 - smooth(d / 0.85));          // 坑底
          else h += cr.d * 0.10 * (1 - Math.abs(d - 1.0) / 0.25);           // 坑缘环
        }
      }
      h *= smooth(clamp01((0.97 - R) / 0.18)) * 0.85 + 0.15;                 // 球面收边
      var g = Math.round(mix(120, 208, clamp01(h)));
      return [clamp01(h), [g, g, Math.round(g * 0.96)]];
    });
  }

  /** 9. 火山岛 —— 环形山+海岸地形 */
  function volcano(cols, rows) {
    var fbm = makeNoise(8848);
    return fromUV(cols, rows, function (u, v) {
      var r = Math.sqrt(u * u + v * v);
      var cone = clamp01(1 - r * 1.15);                       // 圆锥体
      var h = Math.pow(cone, 1.4);
      var crater = clamp01(1 - r / 0.22);                     // 火山口下凹
      h -= 0.38 * Math.pow(crater, 1.6);
      h += 0.14 * (fbm(u * 3.5 + 2, v * 3.5 + 8, 4) - 0.5);   // 地表细节
      h = clamp01(h * 0.92 + 0.08);
      var col;
      if (r > 0.995) col = [40, 90, 150];
      else if (h < 0.16) col = [52, 110, 170];                // 海
      else if (h < 0.24) col = [222, 202, 150];               // 沙滩
      else if (h < 0.45) col = [80, 130, 70];                 // 植被
      else if (crater > 0.35) col = [216, 84, 40];            // 岩浆口
      else col = [92, 76, 68];                                // 火山岩
      return [h, col];
    });
  }

  /* ---------- 画廊清单 ---------- */
  var GALLERY = [
    { id: "heart",     name: "爱心浮雕",   desc: "情人节挂件 · 冰箱贴",   tag: "礼物",  gen: heart,     opt: { widthMM: 60, baseMM: 2,   reliefMM: 5 } },
    { id: "star",      name: "五角星奖章", desc: "小奖励 · 徽章胸牌",     tag: "徽章",  gen: star,      opt: { widthMM: 55, baseMM: 2,   reliefMM: 4 } },
    { id: "mountains", name: "层峦山地",   desc: "雪山湖泊 · 桌面地形",   tag: "地形",  gen: mountains, opt: { widthMM: 80, baseMM: 3,   reliefMM: 12 } },
    { id: "ripple",    name: "水波涟漪",   desc: "双源干涉波 · 杯垫",     tag: "杯垫",  gen: ripple,    opt: { widthMM: 90, baseMM: 2.5, reliefMM: 3 } },
    { id: "gear",      name: "工业齿轮",   desc: "12 齿 · 机械风挂件",    tag: "机械",  gen: gear,      opt: { widthMM: 60, baseMM: 2,   reliefMM: 5 } },
    { id: "honeycomb", name: "蜂窝网格",   desc: "六边形矩阵 · 隔热垫",   tag: "几何",  gen: honeycomb, opt: { widthMM: 90, baseMM: 2,   reliefMM: 4 } },
    { id: "mandala",   name: "曼陀罗盘",   desc: "对称花纹 · 装饰浮雕",   tag: "装饰",  gen: mandala,   opt: { widthMM: 80, baseMM: 2.5, reliefMM: 4 } },
    { id: "moon",      name: "月球表面",   desc: "26 座陨石坑 · 教学摆件", tag: "天文",  gen: moon,      opt: { widthMM: 80, baseMM: 3,   reliefMM: 8 } },
    { id: "volcano",   name: "火山岛",     desc: "环形山口 · 海岸地形",   tag: "地形",  gen: volcano,   opt: { widthMM: 80, baseMM: 3,   reliefMM: 14 } }
  ];

  /** 外部灵感社区（仅导航链接，模型版权归各平台/作者） */
  var COMMUNITIES = [
    { name: "MakerWorld",  url: "https://makerworld.com.cn/zh",      desc: "拓竹官方社区 · 中文 · 海量免费模型" },
    { name: "Printables",  url: "https://www.printables.com/",       desc: "Prusa 官方 · 高质量免费模型" },
    { name: "Thingiverse", url: "https://www.thingiverse.com/",      desc: "老牌最大 3D 打印模型库" },
    { name: "Sketchfab",   url: "https://sketchfab.com/3d-models?features=downloadable&sort_by=-likeCount", desc: "可下载的高质量 3D 模型（看清许可）" },
    { name: "Thangs",      url: "https://thangs.com/",               desc: "几何搜索 · 免费模型聚合" },
    { name: "Cults3D",     url: "https://cults3d.com/zh",            desc: "设计师社区 · 免费+付费精品" }
  ];

  /** 生成某个画廊条目的网格（依赖 SnapPrintCore）。
   *  opt 可覆盖默认参数：{ quality, widthMM, depthMM, baseMM, reliefMM } */
  function buildItem(item, opt) {
    var S = global.SnapPrintCore;
    if (!S) throw new Error("SnapPrintCore 未加载");
    opt = opt || {};
    var quality = opt.quality || 180;
    var cols = quality, rows = quality;
    var d = item.gen(cols, rows);
    var mopt = {
      widthMM:  (opt.widthMM  != null) ? opt.widthMM  : item.opt.widthMM,
      depthMM:  (opt.depthMM  != null) ? opt.depthMM  : item.opt.widthMM,
      baseMM:   (opt.baseMM   != null) ? opt.baseMM   : item.opt.baseMM,
      reliefMM: (opt.reliefMM != null) ? opt.reliefMM : item.opt.reliefMM
    };
    var mesh = S.buildRelief(d.hts, cols, rows, d.cls, mopt);
    mesh.name = item.id;
    return mesh;
  }

  /** 渲染缩略图到 canvas（高度着色 + 简单光照，无需 three.js） */
  function drawThumb(item, canvas, size) {
    var px = size || 96;
    canvas.width = px; canvas.height = px;
    var d = item.gen(px, px);
    var ctx = canvas.getContext("2d");
    var im = ctx.createImageData(px, px);
    for (var y = 0; y < px; y++) {
      for (var x = 0; x < px; x++) {
        var i = y * px + x;
        var h = d.hts[i];
        var hr = d.hts[y * px + Math.min(px - 1, x + 1)];
        var hd = d.hts[Math.min(px - 1, y + 1) * px + x];
        var shade = 0.62 + 0.38 * clamp01(0.5 + (hr - h) * 2.5 + (h - hd) * 2.5);
        var c = d.cls[i];
        var o = i * 4;
        im.data[o]     = Math.round(c[0] * shade);
        im.data[o + 1] = Math.round(c[1] * shade);
        im.data[o + 2] = Math.round(c[2] * shade);
        im.data[o + 3] = 255;
      }
    }
    ctx.putImageData(im, 0, 0);
  }

  global.SnapPrintGallery = {
    items: GALLERY,
    communities: COMMUNITIES,
    buildItem: buildItem,
    drawThumb: drawThumb
  };
})(typeof window !== "undefined" ? window : globalThis);
