/* SnapPrint Web Core — 纯浏览器浮雕生成（零后端、零依赖）
 * 输入：灰度高度图(rows*cols, 0..1) + 可选顶点颜色
 * 输出：水密封闭网格 + OBJ / PLY(带色) / STL(二进制) 导出
 * Apache-2.0
 */
(function (global) {
  "use strict";

  /** 构建浮雕实体网格（顶面位移 + 底面 + 四周侧壁，封闭水密） */
  function buildRelief(heights, cols, rows, colors, opt) {
    var W = opt.widthMM, D = opt.depthMM, B = opt.baseMM, R = opt.reliefMM;
    var dx = W / (cols - 1), dy = D / (rows - 1);
    var nTop = rows * cols;
    var V = new Array(2 * nTop);
    var C = colors ? new Array(2 * nTop) : null;
    var r, c, i;
    for (r = 0; r < rows; r++) {
      for (c = 0; c < cols; c++) {
        i = r * cols + c;
        var x = c * dx, y = (rows - 1 - r) * dy;
        V[i] = [x, y, B + heights[i] * R];       // 顶面
        V[nTop + i] = [x, y, 0];                  // 底面
        if (C) { C[i] = colors[i]; C[nTop + i] = colors[i]; }
      }
    }
    var F = [];
    function quad(a, b, c2, d) { F.push([a, b, c2]); F.push([a, c2, d]); }
    // 顶面(+z) 与 底面(-z)
    for (r = 0; r < rows - 1; r++) {
      for (c = 0; c < cols - 1; c++) {
        var v00 = r * cols + c, v01 = v00 + 1, v10 = v00 + cols, v11 = v10 + 1;
        quad(v00, v10, v11, v01);
        quad(nTop + v00, nTop + v01, nTop + v11, nTop + v10);
      }
    }
    // 侧壁：前后(+y/-y)
    for (c = 0; c < cols - 1; c++) {
      var a = c, b = c + 1;
      quad(a, b, nTop + b, nTop + a);                       // r=0 → y=D，外法线 +y
      var a2 = (rows - 1) * cols + c, b2 = a2 + 1;
      quad(b2, a2, nTop + a2, nTop + b2);                   // r=rows-1 → y=0，外法线 -y
    }
    // 侧壁：左右(-x/+x)
    for (r = 0; r < rows - 1; r++) {
      var la = r * cols, lb = (r + 1) * cols;
      quad(lb, la, nTop + la, nTop + lb);                   // c=0 → x=0，外法线 -x
      var ra = r * cols + cols - 1, rb = ra + cols;
      quad(ra, rb, nTop + rb, nTop + ra);                   // c=cols-1 → x=W，外法线 +x
    }
    if (signedVolume(V, F) < 0) {
      for (i = 0; i < F.length; i++) { var t = F[i][1]; F[i][1] = F[i][2]; F[i][2] = t; }
    }
    return { V: V, F: F, C: C };
  }

  /** 有向体积（mm³），封闭网格应为正 */
  function signedVolume(V, F) {
    var vol = 0;
    for (var i = 0; i < F.length; i++) {
      var a = V[F[i][0]], b = V[F[i][1]], c = V[F[i][2]];
      vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6;
    }
    return vol;
  }

  /** 水密检查：每条无向边必须恰好被 2 个三角形使用 */
  function isWatertight(V, F) {
    var edges = Object.create(null);
    for (var i = 0; i < F.length; i++) {
      var f = F[i];
      for (var e = 0; e < 3; e++) {
        var u = f[e], w = f[(e + 1) % 3];
        var key = u < w ? u + "_" + w : w + "_" + u;
        edges[key] = (edges[key] || 0) + 1;
      }
    }
    for (var k in edges) { if (edges[k] !== 2) return false; }
    return true;
  }

  function exportOBJ(V, F) {
    var out = ["# SnapPrint (browser) OBJ"];
    for (var i = 0; i < V.length; i++) {
      out.push("v " + V[i][0].toFixed(4) + " " + V[i][1].toFixed(4) + " " + V[i][2].toFixed(4));
    }
    for (i = 0; i < F.length; i++) {
      out.push("f " + (F[i][0] + 1) + " " + (F[i][1] + 1) + " " + (F[i][2] + 1));
    }
    return out.join("\n");
  }

  function exportPLY(V, F, C) {
    var hasC = !!C;
    var head = ["ply", "format ascii 1.0", "comment SnapPrint (browser)",
      "element vertex " + V.length,
      "property float x", "property float y", "property float z"];
    if (hasC) head.push("property uchar red", "property uchar green", "property uchar blue");
    head.push("element face " + F.length, "property list uchar int vertex_indices", "end_header");
    var out = [head.join("\n")];
    for (var i = 0; i < V.length; i++) {
      var line = V[i][0].toFixed(4) + " " + V[i][1].toFixed(4) + " " + V[i][2].toFixed(4);
      if (hasC) line += " " + C[i][0] + " " + C[i][1] + " " + C[i][2];
      out.push(line);
    }
    for (i = 0; i < F.length; i++) {
      out.push("3 " + F[i][0] + " " + F[i][1] + " " + F[i][2]);
    }
    return out.join("\n");
  }

  /** 二进制 STL（切片软件通吃） */
  function exportSTL(V, F) {
    var buf = new ArrayBuffer(84 + F.length * 50);
    var dv = new DataView(buf);
    dv.setUint32(80, F.length, true);
    var off = 84;
    for (var i = 0; i < F.length; i++) {
      var a = V[F[i][0]], b = V[F[i][1]], c = V[F[i][2]];
      var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
      var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
      var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      var len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
      dv.setFloat32(off, nx / len, true); dv.setFloat32(off + 4, ny / len, true); dv.setFloat32(off + 8, nz / len, true);
      var pts = [a, b, c];
      for (var p = 0; p < 3; p++) {
        dv.setFloat32(off + 12 + p * 12, pts[p][0], true);
        dv.setFloat32(off + 16 + p * 12, pts[p][1], true);
        dv.setFloat32(off + 20 + p * 12, pts[p][2], true);
      }
      dv.setUint16(off + 48, 0, true);
      off += 50;
    }
    return buf;
  }

  /** 网格统计 */
  function stats(V, F) {
    var minX = 1e9, minY = 1e9, minZ = 1e9, maxX = -1e9, maxY = -1e9, maxZ = -1e9;
    for (var i = 0; i < V.length; i++) {
      var v = V[i];
      if (v[0] < minX) minX = v[0]; if (v[0] > maxX) maxX = v[0];
      if (v[1] < minY) minY = v[1]; if (v[1] > maxY) maxY = v[1];
      if (v[2] < minZ) minZ = v[2]; if (v[2] > maxZ) maxZ = v[2];
    }
    return {
      vertices: V.length,
      faces: F.length,
      size_mm: [maxX - minX, maxY - minY, maxZ - minZ],
      volume_cm3: Math.round(Math.abs(signedVolume(V, F)) / 1000 * 100) / 100,
      watertight: isWatertight(V, F)
    };
  }

  global.SnapPrintCore = {
    buildRelief: buildRelief,
    signedVolume: signedVolume,
    isWatertight: isWatertight,
    exportOBJ: exportOBJ,
    exportPLY: exportPLY,
    exportSTL: exportSTL,
    stats: stats
  };
})(typeof window !== "undefined" ? window : globalThis);
