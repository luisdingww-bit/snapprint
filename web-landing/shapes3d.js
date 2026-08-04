/**
 * SnapPrint 真实 3D 几何模型库 —— 参数化立体（旋转体 / 圆环）
 *
 * 与浮雕/拉伸不同：这里生成的是有完整体量的"真三维"几何体
 * （花瓶、宝石、球、圆环、棋子…），无需照片，纯参数驱动。
 * 全部为水密封闭网格，可直接切片打印，Apache-2.0，可自由商用。
 *
 * 依赖 SnapPrintCore.buildRevolution / buildTorus。
 */
(function (global) {
  "use strict";

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }
  function col(a, b, t) {
    t = clamp(t, 0, 1);
    return [Math.round(lerp(a[0], b[0], t)), Math.round(lerp(a[1], b[1], t)), Math.round(lerp(a[2], b[2], t))];
  }

  /** 由半径函数 r(t)（t∈0..1, z=t*H）采样出 profile */
  function profileFn(H, NP, rfn) {
    var pr = [];
    for (var i = 0; i < NP; i++) { var t = i / (NP - 1); pr.push([Math.max(0, rfn(t)), t * H]); }
    return pr;
  }
  /** 由归一控制点 [[r/Rmax, z/H], …] 缩放成真实 profile（mm） */
  function profilePts(H, Rmax, pts) {
    return pts.map(function (p) { return [Math.max(0, p[0] * Rmax), p[1] * H]; });
  }

  var SHAPES = [
    {
      id: "vase", name: "花瓶", emoji: "🏺", tag: "家居",
      defaults: { H: 120, D: 80, seg: 120, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profileFn(p.H, 90, function (t) {
          var r = 0.42 + 0.42 * Math.sin(Math.PI * (0.10 + 0.82 * t)) - 0.14 * Math.sin(Math.PI * (0.05 + 1.75 * t));
          r = clamp(r, 0.16, 1.0);
          r += 0.12 * Math.exp(-Math.pow((t - 1) / 0.06, 2));   // 顶部外翻唇口
          return Rmax * r;
        });
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 0) * Math.PI / 180, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.14 : 0,
          colorFn: function (r, z, a, t) { return col([214, 108, 54], [250, 210, 176], t); }
        });
      }
    },
    {
      id: "spiral", name: "螺旋花瓶", emoji: "🌀", tag: "家居",
      defaults: { H: 130, D: 78, seg: 140, twist: 300, lobes: 7 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profileFn(p.H, 90, function (t) {
          var r = 0.5 + 0.42 * Math.sin(Math.PI * (0.08 + 0.86 * t));
          return Rmax * clamp(r, 0.2, 1.0);
        });
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 300) * Math.PI / 180, lobes: p.lobes || 7, lobeAmt: 0.16,
          colorFn: function (r, z, a, t) { return col([90, 120, 210], [180, 220, 250], t); }
        });
      }
    },
    {
      id: "gem", name: "宝石", emoji: "💎", tag: "装饰",
      defaults: { H: 60, D: 60, seg: 8, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        // 亭部(尖底)→腰围→冠部台面：低分段 → 明显刻面
        var pr = profilePts(p.H, Rmax, [
          [0.00, 0.00], [0.98, 0.42], [1.00, 0.48], [0.60, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 0) * Math.PI / 180, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.1 : 0,
          colorFn: function (r, z, a, t) { return col([116, 200, 232], [236, 250, 255], t); }
        });
      }
    },
    {
      id: "sphere", name: "球体 / 椭球", emoji: "🔮", tag: "摆件",
      defaults: { H: 70, D: 70, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2, NP = 72, pr = [];
        for (var i = 0; i < NP; i++) {
          var th = i / (NP - 1) * Math.PI;
          pr.push([Rmax * Math.sin(th), p.H * (1 - Math.cos(th)) / 2]);
        }
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 0) * Math.PI / 180, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.08 : 0,
          colorFn: function (r, z, a, t) { return col([96, 152, 240], [206, 228, 255], t); }
        });
      }
    },
    {
      id: "egg", name: "蛋形", emoji: "🥚", tag: "摆件",
      defaults: { H: 90, D: 64, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2, NP = 72, pr = [];
        for (var i = 0; i < NP; i++) {
          var th = i / (NP - 1) * Math.PI;
          var r = Rmax * Math.sin(th) * (1 - 0.20 * Math.cos(th));   // 下大上小
          pr.push([r, p.H * (1 - Math.cos(th)) / 2]);
        }
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) { return col([240, 224, 196], [255, 250, 240], t); }
        });
      }
    },
    {
      id: "ring", name: "圆环 / 戒指", emoji: "💍", tag: "首饰",
      defaults: { H: 24, D: 70, seg: 120, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var rt = clamp(p.H / 2, Rmax * 0.12, Rmax * 0.48);   // 管半径由"高度"控制
        var R = Rmax - rt;                                   // 外径 = D
        var segV = Math.max(12, Math.round(p.seg * 0.38));
        return S.buildTorus(R, rt, p.seg, segV, function (au, av, x, y, z) {
          return col([248, 176, 72], [255, 224, 160], (z / rt + 1) / 2);
        });
      }
    },
    {
      id: "pawn", name: "国际象棋兵", emoji: "♟", tag: "桌游",
      defaults: { H: 110, D: 54, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.96, 0.00], [0.96, 0.05], [0.72, 0.10], [0.44, 0.15], [0.34, 0.20],
          [0.28, 0.30], [0.26, 0.44], [0.30, 0.50], [0.50, 0.55], [0.30, 0.60],
          [0.27, 0.64], [0.34, 0.70], [0.46, 0.80], [0.42, 0.90], [0.24, 0.96], [0.00, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) { return col([60, 66, 78], [150, 158, 172], t); }
        });
      }
    },
    {
      id: "top", name: "陀螺", emoji: "🎯", tag: "玩具",
      defaults: { H: 80, D: 66, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.00, 0.00], [0.40, 0.22], [0.86, 0.40], [1.00, 0.46], [0.90, 0.52],
          [0.30, 0.60], [0.18, 0.74], [0.18, 0.92], [0.12, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 0) * Math.PI / 180, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.1 : 0,
          colorFn: function (r, z, a, t) { return col([232, 84, 72], [255, 196, 120], t); }
        });
      }
    },
    {
      id: "goblet", name: "高脚杯", emoji: "🍷", tag: "家居",
      defaults: { H: 120, D: 62, seg: 100, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.90, 0.00], [0.90, 0.04], [0.34, 0.10], [0.12, 0.14], [0.10, 0.45],
          [0.11, 0.50], [0.30, 0.55], [0.60, 0.70], [0.72, 0.86], [0.68, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) { return col([150, 90, 190], [226, 200, 246], t); }
        });
      }
    },
    {
      id: "bowl", name: "碗（带内腔）", emoji: "🥣", tag: "餐具",
      defaults: { H: 50, D: 110, seg: 120, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        // 外壁上行 → 翻过杯口 → 内壁下行 → 内底收成极点（真实空腔，可装东西）
        var pr = profilePts(p.H, Rmax, [
          [0.52, 0.00], [0.80, 0.10], [0.96, 0.42], [1.00, 0.82], [1.00, 1.00],
          [0.90, 1.00], [0.88, 0.90], [0.72, 0.42], [0.40, 0.22], [0.00, 0.18]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) { return col([70, 130, 180], [214, 236, 250], t); }
        });
      }
    },
    {
      id: "pot", name: "花盆（带内腔）", emoji: "🪴", tag: "园艺",
      defaults: { H: 90, D: 100, seg: 110, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.58, 0.00], [0.62, 0.03], [0.92, 0.84], [1.00, 0.86], [1.00, 1.00],
          [0.88, 1.00], [0.86, 0.92], [0.56, 0.14], [0.00, 0.11]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.06 : 0,
          colorFn: function (r, z, a, t) { return col([176, 96, 58], [236, 178, 132], t); }
        });
      }
    },
    {
      id: "mushroom", name: "蘑菇", emoji: "🍄", tag: "摆件",
      defaults: { H: 85, D: 80, seg: 100, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.30, 0.00], [0.26, 0.10], [0.22, 0.35], [0.24, 0.48], [0.55, 0.52],
          [0.95, 0.55], [1.00, 0.62], [0.92, 0.75], [0.62, 0.90], [0.30, 0.98], [0.00, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) {
            return t < 0.5 ? col([242, 232, 212], [246, 238, 222], t * 2)
                           : col([214, 60, 48], [232, 92, 74], (t - 0.5) * 2);
          }
        });
      }
    },
    {
      id: "pin", name: "保龄球瓶", emoji: "🎳", tag: "玩具",
      defaults: { H: 130, D: 56, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.55, 0.00], [0.72, 0.05], [0.97, 0.18], [1.00, 0.28], [0.90, 0.40],
          [0.62, 0.52], [0.45, 0.62], [0.40, 0.70], [0.44, 0.80], [0.52, 0.88],
          [0.50, 0.94], [0.36, 0.99], [0.00, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg,
          colorFn: function (r, z, a, t) {
            // 白瓶身 + 颈部红环
            return (t > 0.60 && t < 0.72) ? [220, 40, 44] : col([240, 240, 244], [255, 255, 255], t);
          }
        });
      }
    },
    {
      id: "tree", name: "圣诞树", emoji: "🎄", tag: "节日",
      defaults: { H: 130, D: 90, seg: 96, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        // 树干 + 三层锥体裙摆 + 顶尖
        var pr = profilePts(p.H, Rmax, [
          [0.22, 0.00], [0.22, 0.08], [0.95, 0.10], [0.45, 0.34], [0.78, 0.36],
          [0.36, 0.58], [0.62, 0.60], [0.24, 0.80], [0.42, 0.82], [0.00, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg, twist: (p.twist || 0) * Math.PI / 180, lobes: p.lobes || 0, lobeAmt: p.lobes ? 0.08 : 0,
          colorFn: function (r, z, a, t) {
            return t < 0.09 ? [118, 78, 48] : col([26, 112, 58], [92, 190, 108], t);
          }
        });
      }
    },
    {
      id: "lantern", name: "中式灯笼", emoji: "🏮", tag: "节日",
      defaults: { H: 85, D: 95, seg: 120, twist: 0, lobes: 12 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var pr = profilePts(p.H, Rmax, [
          [0.24, 0.00], [0.26, 0.02], [0.32, 0.06], [0.85, 0.18], [1.00, 0.50],
          [0.85, 0.82], [0.32, 0.94], [0.26, 0.98], [0.24, 1.00]
        ]);
        return S.buildRevolution(pr, {
          seg: p.seg, lobes: p.lobes != null ? p.lobes : 12, lobeAmt: 0.05,
          colorFn: function (r, z, a, t) {
            return (t < 0.06 || t > 0.94) ? [250, 200, 80] : col([200, 30, 30], [244, 88, 58], Math.abs(t - 0.5) * 2);
          }
        });
      }
    },
    {
      id: "donut", name: "甜甜圈", emoji: "🍩", tag: "美食",
      defaults: { H: 30, D: 90, seg: 110, twist: 0, lobes: 0 },
      build: function (p) {
        var S = global.SnapPrintCore, Rmax = p.D / 2;
        var rt = Math.min(Math.max(p.H / 2, Rmax * 0.12), Rmax * 0.48);
        var R = Rmax - rt;
        var segV = Math.max(12, Math.round(p.seg * 0.4));
        return S.buildTorus(R, rt, p.seg, segV, function (au, av, x, y, z) {
          // 上半是糖霜（粉），下半是面包（棕金）
          return z > rt * 0.15 ? col([238, 110, 160], [250, 160, 196], (Math.sin(au * 7) + 1) / 2)
                               : col([206, 148, 84], [232, 186, 122], (z / rt + 1) / 2);
        });
      }
    }
  ];

  function byId(id) { for (var i = 0; i < SHAPES.length; i++) if (SHAPES[i].id === id) return SHAPES[i]; return null; }

  /** 生成指定形状网格。params: { H, D, seg, twist, lobes } */
  function build(id, params) {
    var sh = byId(id);
    if (!sh) throw new Error("未知形状：" + id);
    var d = sh.defaults, p = params || {};
    var mesh = sh.build({
      H: p.H != null ? p.H : d.H,
      D: p.D != null ? p.D : d.D,
      seg: p.seg != null ? p.seg : d.seg,
      twist: p.twist != null ? p.twist : d.twist,
      lobes: p.lobes != null ? p.lobes : d.lobes
    });
    mesh.name = id;
    return mesh;
  }

  global.SnapPrint3D = { shapes: SHAPES, byId: byId, build: build };
})(typeof window !== "undefined" ? window : globalThis);
