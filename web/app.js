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

  /** 二进制 GLB (glTF 2.0)：Z-up毫米 → Y-up米，带顶点色(COLOR_0)。
   *  手机/Windows"3D查看器"/网页 <model-viewer>/AR 可直接打开 */
  function exportGLB(V, F, C) {
    var n = V.length, nf = F.length;
    // 索引 (uint32)
    var idx = new Uint32Array(nf * 3);
    for (var i = 0; i < nf; i++) { idx[i*3] = F[i][0]; idx[i*3+1] = F[i][1]; idx[i*3+2] = F[i][2]; }
    // 位置：mm(Z-up) → m(Y-up)： x'=x, y'=z, z'=-y  （再整体平移由查看器处理）
    var pos = new Float32Array(n * 3);
    var mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
    for (i = 0; i < n; i++) {
      var x = V[i][0] * 0.001, y = V[i][2] * 0.001, z = -V[i][1] * 0.001;
      pos[i*3] = x; pos[i*3+1] = y; pos[i*3+2] = z;
      if (x < mn[0]) mn[0] = x; if (y < mn[1]) mn[1] = y; if (z < mn[2]) mn[2] = z;
      if (x > mx[0]) mx[0] = x; if (y > mx[1]) mx[1] = y; if (z > mx[2]) mx[2] = z;
    }
    var hasC = !!C;
    var col = null;
    if (hasC) {
      col = new Float32Array(n * 3);
      for (i = 0; i < n; i++) { col[i*3] = C[i][0]/255; col[i*3+1] = C[i][1]/255; col[i*3+2] = C[i][2]/255; }
    }
    function pad4(x) { return (x + 3) & ~3; }
    var idxBytes = idx.byteLength, posBytes = pos.byteLength, colBytes = hasC ? col.byteLength : 0;
    var idxOff = 0, posOff = pad4(idxBytes), colOff = posOff + pad4(posBytes);
    var binLen = colOff + pad4(colBytes);
    var bin = new ArrayBuffer(binLen);
    new Uint8Array(bin).set(new Uint8Array(idx.buffer), idxOff);
    new Uint8Array(bin).set(new Uint8Array(pos.buffer), posOff);
    if (hasC) new Uint8Array(bin).set(new Uint8Array(col.buffer), colOff);

    var bufferViews = [
      { buffer: 0, byteOffset: idxOff, byteLength: idxBytes, target: 34963 },
      { buffer: 0, byteOffset: posOff, byteLength: posBytes, target: 34962 }
    ];
    var accessors = [
      { bufferView: 0, componentType: 5125, count: nf * 3, type: "SCALAR" },
      { bufferView: 1, componentType: 5126, count: n, type: "VEC3", min: mn, max: mx }
    ];
    var attributes = { POSITION: 1 };
    if (hasC) {
      bufferViews.push({ buffer: 0, byteOffset: colOff, byteLength: colBytes, target: 34962 });
      accessors.push({ bufferView: 2, componentType: 5126, count: n, type: "VEC3" });
      attributes.COLOR_0 = 2;
    }
    var gltf = {
      asset: { version: "2.0", generator: "SnapPrint (browser)" },
      scene: 0,
      scenes: [{ nodes: [0] }],
      nodes: [{ mesh: 0, name: "SnapPrint" }],
      meshes: [{ primitives: [{ attributes: attributes, indices: 0, mode: 4, material: 0 }] }],
      materials: [{ pbrMetallicRoughness: { metallicFactor: 0.0, roughnessFactor: 0.9 }, doubleSided: false }],
      buffers: [{ byteLength: binLen }],
      bufferViews: bufferViews,
      accessors: accessors
    };
    var jsonStr = JSON.stringify(gltf);
    var enc = (typeof TextEncoder !== "undefined") ? new TextEncoder().encode(jsonStr)
              : (function(s){ var b=Buffer.from(s,"utf8"); return new Uint8Array(b.buffer,b.byteOffset,b.length); })(jsonStr);
    var jsonLen = pad4(enc.length);
    var total = 12 + 8 + jsonLen + 8 + binLen;
    var out = new ArrayBuffer(total);
    var dv = new DataView(out);
    var u8 = new Uint8Array(out);
    dv.setUint32(0, 0x46546C67, true);   // 'glTF'
    dv.setUint32(4, 2, true);
    dv.setUint32(8, total, true);
    dv.setUint32(12, jsonLen, true);
    dv.setUint32(16, 0x4E4F534A, true);  // 'JSON'
    u8.set(enc, 20);
    for (var p = 20 + enc.length; p < 20 + jsonLen; p++) u8[p] = 0x20; // 空格填充
    var binStart = 20 + jsonLen;
    dv.setUint32(binStart, binLen, true);
    dv.setUint32(binStart + 4, 0x004E4942, true); // 'BIN'
    u8.set(new Uint8Array(bin), binStart + 8);
    return out;
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
    exportGLB: exportGLB,
    stats: stats
  };
})(typeof window !== "undefined" ? window : globalThis);
