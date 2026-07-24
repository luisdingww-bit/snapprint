/* SnapPrint Model IO — 纯浏览器 3D 模型文件解析（上传自己的模型 → 预览/缩放/格式转换）
 * 支持：STL（二进制 & ASCII）、OBJ、PLY（ascii & binary_little_endian，含顶点色）、GLB（glTF 2.0）
 * 输出统一为 { V:[[x,y,z]…](mm, Z-up), F:[[a,b,c]…], C:[[r,g,b]…]|null }
 * Apache-2.0
 */
(function (global) {
  "use strict";

  /* ── 工具 ── */
  function td(buf, off, len) {
    var u8 = new Uint8Array(buf, off || 0, len === undefined ? undefined : len);
    if (typeof TextDecoder !== "undefined") return new TextDecoder("utf-8").decode(u8);
    var s = "";
    for (var i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
    return s;
  }

  /** 焊接重复顶点（STL 每个三角形独立存点，必须合并才能判断水密） */
  function weld(positions, colors) {
    var map = Object.create(null);
    var V = [], C = colors ? [] : null, remap = new Int32Array(positions.length / 3);
    for (var i = 0; i < positions.length / 3; i++) {
      var x = positions[i * 3], y = positions[i * 3 + 1], z = positions[i * 3 + 2];
      var key = x.toPrecision(7) + "_" + y.toPrecision(7) + "_" + z.toPrecision(7);
      var idx = map[key];
      if (idx === undefined) {
        idx = V.length;
        map[key] = idx;
        V.push([x, y, z]);
        if (C) C.push(colors[i]);
      }
      remap[i] = idx;
    }
    return { V: V, C: C, remap: remap };
  }

  /* ── STL ── */
  function parseSTL(buf) {
    var u8 = new Uint8Array(buf);
    // ASCII 判定：以 "solid" 开头且文件内含 "facet"
    var head = td(buf, 0, Math.min(512, u8.length)).toLowerCase();
    var isAscii = head.indexOf("solid") === 0 && head.indexOf("facet") !== -1;
    if (!isAscii && u8.length >= 84) {
      var dv = new DataView(buf);
      var nf = dv.getUint32(80, true);
      if (84 + nf * 50 === u8.length) return parseSTLBinary(buf, nf);
      // 长度不匹配但也不是 ASCII → 按二进制尽力解析
      if (head.indexOf("facet") === -1) return parseSTLBinary(buf, Math.floor((u8.length - 84) / 50));
    }
    if (isAscii || head.indexOf("facet") !== -1) return parseSTLAscii(td(buf));
    // 兜底二进制
    return parseSTLBinary(buf, Math.floor((u8.length - 84) / 50));
  }
  function parseSTLBinary(buf, nf) {
    if (nf <= 0) throw new Error("STL 文件为空或损坏");
    var dv = new DataView(buf);
    var pos = new Float32Array(nf * 9);
    var off = 84;
    for (var i = 0; i < nf; i++) {
      for (var p = 0; p < 9; p++) pos[i * 9 + p] = dv.getFloat32(off + 12 + p * 4, true);
      off += 50;
    }
    return finishTriSoup(pos, nf);
  }
  function parseSTLAscii(text) {
    var re = /vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)/g;
    var arr = [], m;
    while ((m = re.exec(text)) !== null) {
      arr.push(parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3]));
    }
    var nf = Math.floor(arr.length / 9);
    if (nf <= 0) throw new Error("ASCII STL 中未找到三角形");
    return finishTriSoup(new Float32Array(arr.slice(0, nf * 9)), nf);
  }
  function finishTriSoup(pos, nf) {
    var w = weld(pos, null);
    var F = new Array(nf);
    for (var i = 0; i < nf; i++) F[i] = [w.remap[i * 3], w.remap[i * 3 + 1], w.remap[i * 3 + 2]];
    return { V: w.V, F: F, C: null };
  }

  /* ── OBJ ── */
  function parseOBJ(text) {
    var V = [], C = null, F = [];
    var lines = text.split(/\r?\n/);
    for (var li = 0; li < lines.length; li++) {
      var ln = lines[li].trim();
      if (ln.length < 2) continue;
      var tk = ln.split(/\s+/);
      if (tk[0] === "v") {
        V.push([parseFloat(tk[1]), parseFloat(tk[2]), parseFloat(tk[3])]);
        if (tk.length >= 7) {              // 扩展格式：v x y z r g b
          if (!C) { C = []; for (var q = C.length; q < V.length - 1; q++) C.push([204, 204, 204]); }
          C.push([Math.round(parseFloat(tk[4]) * 255), Math.round(parseFloat(tk[5]) * 255), Math.round(parseFloat(tk[6]) * 255)]);
        } else if (C) C.push([204, 204, 204]);
      } else if (tk[0] === "f") {
        var idxs = [];
        for (var i = 1; i < tk.length; i++) {
          var a = parseInt(tk[i].split("/")[0], 10);
          idxs.push(a > 0 ? a - 1 : V.length + a);
        }
        for (i = 1; i + 1 < idxs.length; i++) F.push([idxs[0], idxs[i], idxs[i + 1]]); // 扇形三角化
      }
    }
    if (!V.length || !F.length) throw new Error("OBJ 中未找到顶点或面");
    return { V: V, F: F, C: C };
  }

  /* ── PLY ── */
  function parsePLY(buf) {
    var headText = td(buf, 0, Math.min(4096, buf.byteLength));
    var hEnd = headText.indexOf("end_header");
    if (hEnd === -1) throw new Error("PLY 头不完整");
    // 计算 end_header 之后换行的字节偏移
    var headStr = headText.slice(0, hEnd) + "end_header";
    var bodyOff = 0, u8 = new Uint8Array(buf);
    // 找到 "end_header" 后的第一个 \n
    for (var i = hEnd; i < Math.min(4096 + 16, u8.length); i++) {
      if (u8[i] === 10) { bodyOff = i + 1; break; }
    }
    var lines = headStr.split(/\r?\n/);
    var format = "", nV = 0, nF = 0, props = [], cur = "";
    for (i = 0; i < lines.length; i++) {
      var tk = lines[i].trim().split(/\s+/);
      if (tk[0] === "format") format = tk[1];
      else if (tk[0] === "element") { cur = tk[1]; if (cur === "vertex") nV = parseInt(tk[2], 10); if (cur === "face") nF = parseInt(tk[2], 10); }
      else if (tk[0] === "property" && cur === "vertex") props.push({ type: tk[1], name: tk[tk.length - 1] });
    }
    if (!nV || !nF) throw new Error("PLY 缺少 vertex/face 元素");
    var hasColor = props.some(function (p) { return p.name === "red"; });
    var V = new Array(nV), C = hasColor ? new Array(nV) : null, F = [];
    var SZ = { char: 1, uchar: 1, int8: 1, uint8: 1, short: 2, ushort: 2, int16: 2, uint16: 2,
               int: 4, uint: 4, int32: 4, uint32: 4, float: 4, float32: 4, double: 8, float64: 8 };
    if (format === "ascii") {
      var body = td(buf, bodyOff).split(/\r?\n/).filter(function (l) { return l.trim().length; });
      for (i = 0; i < nV; i++) {
        var vt = body[i].trim().split(/\s+/), rec = {};
        for (var p = 0; p < props.length; p++) rec[props[p].name] = parseFloat(vt[p]);
        V[i] = [rec.x, rec.y, rec.z];
        if (C) C[i] = [rec.red | 0, rec.green | 0, rec.blue | 0];
      }
      for (i = 0; i < nF; i++) {
        var ft = body[nV + i].trim().split(/\s+/).map(Number);
        for (p = 2; p + 1 <= ft[0]; p++) F.push([ft[1], ft[p], ft[p + 1]]);
      }
    } else if (format === "binary_little_endian") {
      var dv = new DataView(buf);
      var off = bodyOff;
      function rd(type) {
        var v;
        switch (type) {
          case "char": case "int8": v = dv.getInt8(off); off += 1; break;
          case "uchar": case "uint8": v = dv.getUint8(off); off += 1; break;
          case "short": case "int16": v = dv.getInt16(off, true); off += 2; break;
          case "ushort": case "uint16": v = dv.getUint16(off, true); off += 2; break;
          case "int": case "int32": v = dv.getInt32(off, true); off += 4; break;
          case "uint": case "uint32": v = dv.getUint32(off, true); off += 4; break;
          case "float": case "float32": v = dv.getFloat32(off, true); off += 4; break;
          default: v = dv.getFloat64(off, true); off += 8;
        }
        return v;
      }
      for (i = 0; i < nV; i++) {
        var rec2 = {};
        for (p = 0; p < props.length; p++) rec2[props[p].name] = rd(props[p].type);
        V[i] = [rec2.x, rec2.y, rec2.z];
        if (C) C[i] = [rec2.red | 0, rec2.green | 0, rec2.blue | 0];
      }
      for (i = 0; i < nF; i++) {
        var cnt = rd("uchar"), fi = [];
        for (p = 0; p < cnt; p++) fi.push(rd("int"));
        for (p = 1; p + 1 < cnt; p++) F.push([fi[0], fi[p], fi[p + 1]]);
      }
    } else {
      throw new Error("暂不支持 PLY 格式：" + format + "（支持 ascii / binary_little_endian）");
    }
    return { V: V, F: F, C: C };
  }

  /* ── GLB (glTF 2.0 binary) ── */
  function parseGLB(buf) {
    var dv = new DataView(buf);
    if (dv.getUint32(0, true) !== 0x46546C67) throw new Error("不是有效的 GLB 文件");
    var total = dv.getUint32(8, true);
    var off = 12, json = null, bin = null;
    while (off < total) {
      var len = dv.getUint32(off, true), type = dv.getUint32(off + 4, true);
      if (type === 0x4E4F534A) json = JSON.parse(td(buf, off + 8, len));
      else if (type === 0x004E4942) bin = buf.slice(off + 8, off + 8 + len);
      off += 8 + len;
    }
    if (!json || !bin) throw new Error("GLB 缺少 JSON 或 BIN 块");

    function accData(ai) {
      var acc = json.accessors[ai];
      var bv = json.bufferViews[acc.bufferView];
      var byteOff = (bv.byteOffset || 0) + (acc.byteOffset || 0);
      var compN = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[acc.type];
      var n = acc.count * compN;
      switch (acc.componentType) {
        case 5120: return { a: new Int8Array(bin, byteOff, n), norm: acc.normalized, c: compN, count: acc.count };
        case 5121: return { a: new Uint8Array(bin, byteOff, n), norm: acc.normalized, c: compN, count: acc.count };
        case 5122: return { a: new Int16Array(bin, byteOff, n), norm: acc.normalized, c: compN, count: acc.count };
        case 5123: return { a: new Uint16Array(bin, byteOff, n), norm: acc.normalized, c: compN, count: acc.count };
        case 5125: return { a: new Uint32Array(bin, byteOff, n), norm: false, c: compN, count: acc.count };
        case 5126: return { a: new Float32Array(bin, byteOff, n), norm: false, c: compN, count: acc.count };
        default: throw new Error("GLB 不支持的 componentType " + acc.componentType);
      }
    }

    var V = [], C = null, F = [], base = 0, hasAnyColor = false;
    (json.meshes || []).forEach(function (mesh) {
      (mesh.primitives || []).forEach(function (prim) {
        if (prim.mode !== undefined && prim.mode !== 4) return;   // 只取三角形
        var pd = accData(prim.attributes.POSITION);
        var n = pd.count;
        // glTF: Y-up 米 → SnapPrint: Z-up 毫米（x'=x, y'=-z, z'=y）×1000
        for (var i = 0; i < n; i++) {
          V.push([pd.a[i * 3] * 1000, -pd.a[i * 3 + 2] * 1000, pd.a[i * 3 + 1] * 1000]);
        }
        var cAttr = prim.attributes.COLOR_0;
        if (cAttr !== undefined) {
          hasAnyColor = true;
          if (!C) { C = []; for (i = 0; i < base; i++) C.push([204, 204, 204]); }
          var cd = accData(cAttr);
          var scale = (cd.a instanceof Float32Array) ? 255 :
                      (cd.a instanceof Uint16Array) ? 255 / 65535 : 1;
          for (i = 0; i < n; i++) {
            C.push([Math.round(cd.a[i * cd.c] * scale),
                    Math.round(cd.a[i * cd.c + 1] * scale),
                    Math.round(cd.a[i * cd.c + 2] * scale)]);
          }
        } else if (C) {
          for (i = 0; i < n; i++) C.push([204, 204, 204]);
        }
        if (prim.indices !== undefined) {
          var id = accData(prim.indices);
          for (i = 0; i + 2 < id.a.length; i += 3) F.push([base + id.a[i], base + id.a[i + 1], base + id.a[i + 2]]);
        } else {
          for (i = 0; i + 2 < n; i += 3) F.push([base + i, base + i + 1, base + i + 2]);
        }
        base += n;
      });
    });
    if (!V.length || !F.length) throw new Error("GLB 中未找到三角网格");
    return { V: V, F: F, C: hasAnyColor ? C : null };
  }

  /** 统一入口：按文件名后缀解析 ArrayBuffer → {V,F,C}
   *  注：GLB 视为米并转 Z-up；STL/OBJ/PLY 数值按毫米原样读取。 */
  function parse(name, buf) {
    var ext = (name.split(".").pop() || "").toLowerCase();
    if (ext === "stl") return parseSTL(buf);
    if (ext === "obj") return parseOBJ(td(buf));
    if (ext === "ply") return parsePLY(buf);
    if (ext === "glb") return parseGLB(buf);
    if (ext === "gltf") throw new Error("请导出为 .glb（二进制）后再上传");
    throw new Error("不支持的模型格式：." + ext + "（支持 STL / OBJ / PLY / GLB）");
  }

  /** 等比缩放：把模型最长边缩放到 targetMM 毫米，并把最低点落到 z=0、水平居中到原点 */
  function normalize(mesh, targetMM) {
    var V = mesh.V;
    var mn = [1e18, 1e18, 1e18], mx = [-1e18, -1e18, -1e18];
    var i, k;
    for (i = 0; i < V.length; i++) {
      for (k = 0; k < 3; k++) {
        if (V[i][k] < mn[k]) mn[k] = V[i][k];
        if (V[i][k] > mx[k]) mx[k] = V[i][k];
      }
    }
    var size = [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]];
    var longest = Math.max(size[0], size[1], size[2]) || 1;
    var s = targetMM / longest;
    var cx = (mn[0] + mx[0]) / 2, cy = (mn[1] + mx[1]) / 2;
    var V2 = new Array(V.length);
    for (i = 0; i < V.length; i++) {
      V2[i] = [(V[i][0] - cx) * s, (V[i][1] - cy) * s, (V[i][2] - mn[2]) * s];
    }
    return { V: V2, F: mesh.F, C: mesh.C };
  }

  global.SnapPrintIO = {
    parse: parse,
    parseSTL: parseSTL,
    parseOBJ: parseOBJ,
    parsePLY: parsePLY,
    parseGLB: parseGLB,
    normalize: normalize,
    ACCEPT: ".stl,.obj,.ply,.glb"
  };
})(typeof window !== "undefined" ? window : globalThis);
