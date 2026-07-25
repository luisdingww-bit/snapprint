"""SnapPrint 可打印性 / 支撑建议分析（面向 FDM 打印）。

给定一个 trimesh.Trimesh（单位 mm，Z-up，最好是水密网格），
输出结构化的切片与支撑建议。后端 /api/analyze 与 Blender / ComfyUI
客户端都复用本模块，保证建议口径一致（浏览器端等价的实现见
web/presets.js）。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

# —— 常见打印机（热床 mm、喷嘴 mm）—— 与 web/presets.js 保持一致
PRINTERS: list[dict] = [
    {"id": "bambu_a1",     "name": "拓竹 Bambu Lab A1",      "bed": [256, 256, 256], "nozzle": 0.4},
    {"id": "bambu_a1mini", "name": "拓竹 Bambu Lab A1 mini", "bed": [180, 180, 180], "nozzle": 0.4},
    {"id": "bambu_p1s",    "name": "拓竹 P1S / X1C",         "bed": [256, 256, 256], "nozzle": 0.4},
    {"id": "ender3v3",     "name": "创想三维 Ender-3 V3",    "bed": [220, 220, 250], "nozzle": 0.4},
    {"id": "k1c",          "name": "创想三维 K1C",           "bed": [220, 220, 250], "nozzle": 0.4},
    {"id": "prusa_mk4s",   "name": "Prusa MK4S",             "bed": [250, 210, 220], "nozzle": 0.4},
    {"id": "neptune4",     "name": "Elegoo Neptune 4 Pro",   "bed": [225, 225, 265], "nozzle": 0.4},
    {"id": "kobra3",       "name": "Anycubic Kobra 3",       "bed": [250, 250, 260], "nozzle": 0.4},
    {"id": "generic",      "name": "通用 FDM（0.4 喷嘴）",    "bed": [220, 220, 250], "nozzle": 0.4},
]

MATERIALS: list[dict] = [
    {"id": "pla",  "name": "PLA",     "nozzle": 215, "bed": 60, "density": 1.24},
    {"id": "petg", "name": "PETG",    "nozzle": 245, "bed": 75, "density": 1.27},
    {"id": "tpu",  "name": "TPU 95A", "nozzle": 225, "bed": 45, "density": 1.21},
]

OVERHANG_DEG = 45  # 悬垂判定的临界角度（与切片软件常用阈值一致）


def _by_id(items: list[dict], _id: str) -> dict:
    for it in items:
        if it["id"] == _id:
            return it
    return items[-1]


def analyze(mesh: "trimesh.Trimesh", mode: str = "relief") -> dict:
    """几何分析 → 结构化切片与支撑建议。

    参数 mode：relief / extrude / solid3d / import。
    浮雕/拉伸通常天然自支撑，其余按悬垂占比判定。
    """
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=int)

    bounds = mesh.bounds  # (min, max)
    bed_z = float(bounds[0][2])
    size = bounds[1] - bounds[0]
    max_dim = float(size.max())
    foot_min = float(min(size[0], size[1]))

    # 每面法线（trimesh 保证水密网格法线朝外）
    normals = np.asarray(mesh.face_normals, dtype=float)
    face_area = np.asarray(mesh.area_faces, dtype=float)
    total_area = float(face_area.sum())
    if total_area <= 0:
        total_area = 1e-9

    # 每面顶点最小 z（判断是否贴床）
    face_min_z = verts[faces].min(axis=1)[:, 2]

    cos_down = -normals[:, 2]  # 与 -Z 夹角余弦（朝下程度）
    cos_thr = math.cos(math.radians(OVERHANG_DEG))

    overhang_mask = (cos_down > cos_thr) & (face_min_z - bed_z > 1.0)
    overhang_area = float(face_area[overhang_mask].sum())
    overhang_ratio = overhang_area / total_area

    contact_mask = (cos_down > 0.999) & (face_min_z - bed_z < 0.5)
    contact_area = float(face_area[contact_mask].sum())
    footprint = float(size[0] * size[1])
    contact_ratio = contact_area / footprint if footprint > 0 else 1.0

    volume_cm3 = float(abs(mesh.volume)) / 1000.0
    watertight = bool(mesh.is_watertight)

    warnings: list[str] = []
    if not watertight:
        warnings.append("网格非水密，切片前请先修复（SnapPrint 导出默认已补洞）")

    # —— 支撑判定与详细建议 ——
    supports = False
    support_reason = "自支撑几何，无需支撑"
    support_density = 0.0
    support_type = "none"
    if mode not in ("relief", "extrude"):
        if overhang_ratio > 0.03:
            supports = True
            support_reason = (
                f"悬垂(>{OVERHANG_DEG}°)面积占 {overhang_ratio*100:.1f}%，建议开启支撑"
            )
            # 悬垂越大，密度越高；悬垂分散 → 树状支撑更省料
            if overhang_ratio > 0.20:
                support_density = 0.30
            elif overhang_ratio > 0.10:
                support_density = 0.20
            else:
                support_density = 0.15
            support_type = "tree" if overhang_ratio > 0.15 else "normal"
        else:
            support_reason = (
                f"悬垂面积仅 {overhang_ratio*100:.1f}%，可免支撑"
            )

    # —— 层高 ——
    layer = 0.2
    layer_why = "标准精度"
    if max_dim <= 45 or mode == "relief":
        layer = 0.12
        layer_why = "小尺寸/浮雕细节优先" if mode == "relief" else "小尺寸模型，提升细节"
    elif max_dim >= 150:
        layer = 0.28
        layer_why = "大件提速"

    # —— 填充 ——
    infill = 15
    if volume_cm3 >= 80:
        infill = 10
    elif volume_cm3 <= 2:
        infill = 25

    # —— Brim ——
    tall_ratio = foot_min > 0 and size[2] / foot_min or 0.0
    brim = 0.0
    brim_why = "接触面充足，无需 brim"
    if contact_ratio < 0.15 or tall_ratio > 2.5:
        brim = 5.0
        brim_why = (
            f"贴床面积小({contact_ratio*100:.0f}%)，加 5mm brim 防翘"
            if contact_ratio < 0.15
            else f"细高件(高/宽={tall_ratio:.1f})，加 5mm brim 防倒"
        )

    # —— 摆放建议 ——
    orientation_advice = ""
    if supports:
        orientation_advice = (
            "若可，将悬垂特征旋转至 45° 以内或朝下，可显著减少支撑用量与后处理。"
        )
    elif contact_ratio < 0.15:
        orientation_advice = "平放最宽面朝下以增大贴床接触，或加 brim / raft 防翘边。"

    solid_factor = 0.30 + 0.70 * (infill / 100.0)

    return {
        "mode": mode,
        "size_mm": [float(size[0]), float(size[1]), float(size[2])],
        "volume_cm3": round(volume_cm3, 2),
        "watertight": watertight,
        "overhang_ratio": round(overhang_ratio, 4),
        "contact_ratio": round(contact_ratio, 4),
        "tall_ratio": round(tall_ratio, 2),
        # 切片参数
        "layer_height": layer,
        "first_layer_height": max(layer, 0.2),
        "infill": infill,
        "perimeters": 2,
        "top_layers": 4,
        "bottom_layers": 3,
        # 支撑建议（FDM）
        "supports": supports,
        "support_reason": support_reason,
        "support_density": support_density,
        "support_type": support_type,
        "support_threshold_deg": OVERHANG_DEG,
        "orientation_advice": orientation_advice,
        # brim
        "brim_mm": brim,
        "brim_why": brim_why,
        "solid_factor": solid_factor,
        "warnings": warnings,
    }


def fit(rec: dict, printer: dict) -> dict:
    """判断模型是否落入某打印机热床（允许水平旋转）。"""
    s = rec["size_mm"]
    b = printer["bed"]
    f1 = max(s[0], s[1])
    f2 = min(s[0], s[1])
    b1 = max(b[0], b[1])
    b2 = min(b[0], b[1])
    ok = f1 <= b1 and f2 <= b2 and s[2] <= b[2]
    return {"ok": ok, "bed": b}


def estimate(rec: dict, mat: dict) -> dict:
    grams = rec["volume_cm3"] * mat["density"] * rec["solid_factor"]
    mm3 = rec["volume_cm3"] * 1000 * rec["solid_factor"]
    minutes = mm3 / 12 / 60 + rec["size_mm"][2] / rec["layer_height"] * 0.02
    return {"grams": round(grams, 1), "minutes": round(minutes, 1)}


# 社区主线只接受用户「自己已有的模型」文件；图片→浮雕生成已不再是主线。
SUPPORTED_EXT = (".stl", ".obj", ".ply", ".3mf", ".glb", ".gltf", ".off")


def analyze_upload(
    data: bytes,
    *,
    filename: str = "",
    printer: str = "",
    material: str = "",
    content_type: str = "",
) -> dict:
    """从上传的模型文件字节得到可打印性建议 dict。

    仅接受网格文件（stl/obj/ply/3mf/glb/gltf/off）。图片→浮雕的图生 3D
    能力已不再是 SnapPrint 社区版的主线；这里聚焦「上传已有模型 → 分析」。
    """
    import io

    ext = ""
    low = filename.lower()
    for e in SUPPORTED_EXT:
        if low.endswith(e):
            ext = e[1:]
            break
    if not ext:
        raise ValueError(
            "不支持的文件格式，请上传 .stl / .obj / .ply / .3mf / .glb / .gltf / .off"
        )

    try:
        mesh = trimesh.load(io.BytesIO(data), file_type=ext or None, force="mesh")
    except Exception as e:  # pragma: no cover - 无法解析的文件
        raise ValueError(f"无法解析模型文件: {e}")

    if mesh is None or getattr(mesh, "is_empty", True):
        raise ValueError("模型文件为空或无法解析")

    rec = analyze(mesh, "import")

    if printer:
        p = _by_id(PRINTERS, printer)
        ft = fit(rec, p)
        if not ft["ok"]:
            rec.setdefault("warnings", []).append(
                f"模型超出热床 {p['name']}（{p['bed']} mm），请缩放或旋转后再切片"
            )
        rec["printer"] = {"id": p["id"], "name": p["name"], "fit": ft["ok"]}

    if material:
        m = _by_id(MATERIALS, material)
        rec["material"] = {"id": m["id"], "name": m["name"]}
        rec.update(estimate(rec, m))

    rec["score"] = score(rec)
    return rec


def score(rec: dict) -> int:
    """可打印性综合评分 0-100（越高越省心）。

    权重：水密性(基础) > 悬垂占比 > 是否需支撑 > 贴床接触。
    """
    s = 100
    if not rec.get("watertight"):
        s -= 35
    s -= min(30, rec.get("overhang_ratio", 0) * 100 * 0.8)
    if rec.get("supports"):
        s -= 10
    if rec.get("contact_ratio", 1.0) < 0.1:
        s -= 10
    return int(max(0, min(100, round(s))))
