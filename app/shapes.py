"""SnapPrint 内置模型实例库 —— 参数化真 3D 几何（旋转体 / 圆环）。

从 v0.5 浏览器版 `web/shapes3d.js` + `SnapPrintCore` 移植到后端 Python：
无需照片、纯参数驱动，生成有完整体量的"真三维"几何体
（花瓶、宝石、球、圆环、棋子、灯笼、甜甜圈…）。

- 全部为水密封闭网格，可直接切片打印；
- 带顶点色（导出 .obj 可见彩色，.stl 为通用几何）；
- 仅依赖 numpy + trimesh（与社区版其余部分一致，零重依赖）。

对外入口：
    SHAPES              : 模型实例元数据列表（id/name/emoji/tag/defaults）
    build(id, params)   : 生成 trimesh.Trimesh（含顶点色）
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import trimesh

# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp(x: float, a: float, b: float) -> float:
    return a if x < a else (b if x > b else x)


def _col(a, b, t: float):
    """两色线性渐变（0..255 RGB）。"""
    t = _clamp(t, 0.0, 1.0)
    return [round(_lerp(a[0], b[0], t)), round(_lerp(a[1], b[1], t)), round(_lerp(a[2], b[2], t))]


def _profile_fn(H: float, NP: int, rfn: Callable[[float], float]):
    """由半径函数 r(t)（t∈0..1, z=t*H）采样出 profile [[r, z], ...]。"""
    return [[max(0.0, rfn(i / (NP - 1))), i / (NP - 1) * H] for i in range(NP)]


def _profile_pts(H: float, Rmax: float, pts):
    """由归一控制点 [[r/Rmax, z/H], …] 缩放成真实 profile（mm）。"""
    return [[max(0.0, p[0] * Rmax), p[1] * H] for p in pts]


def _signed_volume(V: np.ndarray, F: np.ndarray) -> float:
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _fix_winding(V, F):
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if _signed_volume(V, F) < 0:
        F = F[:, [0, 2, 1]]
    return V, F


# ---------------------------------------------------------------------------
# 核心构建器（移植自 SnapPrintCore.buildRevolution / buildTorus）
# ---------------------------------------------------------------------------

def build_revolution(profile, seg: int = 64, twist: float = 0.0, lobes: int = 0,
                     lobe_amt: float = 0.0, color_fn=None):
    """旋转体：把 2D 轮廓绕 Z 轴旋转成水密实体。

    profile: [[r, z], …] 由底到顶，r>=0（端点 r≈0 视为极点，自动收成一个点）。
    twist: 总扭转弧度；lobes: 棱数(0=圆)；lobe_amt: 棱深(0..1)；
    color_fn(r, z, ang, t) -> [R,G,B]，t=归一高度。
    """
    seg = max(3, int(seg))
    EPS = 1e-6
    np_ = len(profile)
    zmin, zmax = profile[0][1], profile[np_ - 1][1]
    zr = (zmax - zmin) or 1.0

    V: list = []
    C: list | None = [] if color_fn else None
    F: list = []
    ring_start = [0] * np_
    is_pole = [False] * np_

    for p in range(np_):
        r0, z = profile[p]
        t = (z - zmin) / zr
        if r0 < EPS:
            is_pole[p] = True
            ring_start[p] = len(V)
            V.append([0.0, 0.0, z])
            if C is not None:
                C.append(color_fn(0.0, z, 0.0, t))
        else:
            ring_start[p] = len(V)
            off = twist * t
            for s in range(seg):
                a = s / seg * 2 * math.pi + off
                rr = r0 * (1 + lobe_amt * math.cos(lobes * a)) if lobes else r0
                V.append([rr * math.cos(a), rr * math.sin(a), z])
                if C is not None:
                    C.append(color_fn(rr, z, a, t))

    for p in range(np_ - 1):
        a0, a1 = ring_start[p], ring_start[p + 1]
        pa, pb = is_pole[p], is_pole[p + 1]
        if pa and pb:
            continue
        if pa:  # 下极点 → 上环：扇形
            for s in range(seg):
                n = (s + 1) % seg
                F.append([a0, a1 + n, a1 + s])
        elif pb:  # 下环 → 上极点：扇形
            for s in range(seg):
                n = (s + 1) % seg
                F.append([a0 + s, a0 + n, a1])
        else:  # 环 → 环：四边形带
            for s in range(seg):
                n = (s + 1) % seg
                F.append([a0 + s, a0 + n, a1 + n])
                F.append([a0 + s, a1 + n, a1 + s])

    if not is_pole[0]:  # 底盖圆盘
        cB = len(V)
        V.append([0.0, 0.0, profile[0][1]])
        if C is not None:
            C.append(color_fn(0.0, profile[0][1], 0.0, 0.0))
        b0 = ring_start[0]
        for s in range(seg):
            n = (s + 1) % seg
            F.append([cB, b0 + n, b0 + s])
    if not is_pole[np_ - 1]:  # 顶盖圆盘
        cT = len(V)
        V.append([0.0, 0.0, profile[np_ - 1][1]])
        if C is not None:
            C.append(color_fn(0.0, profile[np_ - 1][1], 0.0, 1.0))
        tp = ring_start[np_ - 1]
        for s in range(seg):
            n = (s + 1) % seg
            F.append([cT, tp + s, tp + n])

    V, F = _fix_winding(V, F)
    return V, F, (np.asarray(C, dtype=np.uint8) if C is not None else None)


def build_torus(R: float, rt: float, seg_u: int = 64, seg_v: int = 24, color_fn=None):
    """圆环（甜甜圈/戒指）：管半径 rt 的圆截面绕主半径 R 旋转 → 水密。"""
    seg_u, seg_v = max(3, int(seg_u)), max(3, int(seg_v))
    V, C, F = [], ([] if color_fn else None), []
    for u in range(seg_u):
        au = u / seg_u * 2 * math.pi
        for v in range(seg_v):
            av = v / seg_v * 2 * math.pi
            rr = R + rt * math.cos(av)
            x, y, z = rr * math.cos(au), rr * math.sin(au), rt * math.sin(av)
            V.append([x, y, z])
            if C is not None:
                C.append(color_fn(au, av, x, y, z))

    def idx(uu, vv):
        return (uu % seg_u) * seg_v + (vv % seg_v)

    for u in range(seg_u):
        for v in range(seg_v):
            a, b = idx(u, v), idx(u + 1, v)
            c, d = idx(u + 1, v + 1), idx(u, v + 1)
            F.append([a, b, c])
            F.append([a, c, d])

    V, F = _fix_winding(V, F)
    return V, F, (np.asarray(C, dtype=np.uint8) if C is not None else None)


# ---------------------------------------------------------------------------
# 16 款模型实例（与 v0.5 浏览器版 shapes3d.js 一一对应）
# ---------------------------------------------------------------------------

def _vase(p):
    Rmax = p["D"] / 2

    def rfn(t):
        r = 0.42 + 0.42 * math.sin(math.pi * (0.10 + 0.82 * t)) - 0.14 * math.sin(math.pi * (0.05 + 1.75 * t))
        r = _clamp(r, 0.16, 1.0)
        r += 0.12 * math.exp(-((t - 1) / 0.06) ** 2)  # 顶部外翻唇口
        return Rmax * r

    return build_revolution(
        _profile_fn(p["H"], 90, rfn), seg=p["seg"], twist=math.radians(p.get("twist") or 0),
        lobes=p.get("lobes") or 0, lobe_amt=0.14 if p.get("lobes") else 0,
        color_fn=lambda r, z, a, t: _col([214, 108, 54], [250, 210, 176], t))


def _spiral(p):
    Rmax = p["D"] / 2

    def rfn(t):
        return Rmax * _clamp(0.5 + 0.42 * math.sin(math.pi * (0.08 + 0.86 * t)), 0.2, 1.0)

    return build_revolution(
        _profile_fn(p["H"], 90, rfn), seg=p["seg"], twist=math.radians(p.get("twist") or 300),
        lobes=p.get("lobes") or 7, lobe_amt=0.16,
        color_fn=lambda r, z, a, t: _col([90, 120, 210], [180, 220, 250], t))


def _gem(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [[0.00, 0.00], [0.98, 0.42], [1.00, 0.48], [0.60, 1.00]])
    return build_revolution(
        pr, seg=p["seg"], twist=math.radians(p.get("twist") or 0),
        lobes=p.get("lobes") or 0, lobe_amt=0.1 if p.get("lobes") else 0,
        color_fn=lambda r, z, a, t: _col([116, 200, 232], [236, 250, 255], t))


def _sphere(p):
    Rmax, NP = p["D"] / 2, 72
    pr = []
    for i in range(NP):
        th = i / (NP - 1) * math.pi
        pr.append([Rmax * math.sin(th), p["H"] * (1 - math.cos(th)) / 2])
    return build_revolution(
        pr, seg=p["seg"], twist=math.radians(p.get("twist") or 0),
        lobes=p.get("lobes") or 0, lobe_amt=0.08 if p.get("lobes") else 0,
        color_fn=lambda r, z, a, t: _col([96, 152, 240], [206, 228, 255], t))


def _egg(p):
    Rmax, NP = p["D"] / 2, 72
    pr = []
    for i in range(NP):
        th = i / (NP - 1) * math.pi
        r = Rmax * math.sin(th) * (1 - 0.20 * math.cos(th))  # 下大上小
        pr.append([r, p["H"] * (1 - math.cos(th)) / 2])
    return build_revolution(
        pr, seg=p["seg"],
        color_fn=lambda r, z, a, t: _col([240, 224, 196], [255, 250, 240], t))


def _ring(p):
    Rmax = p["D"] / 2
    rt = _clamp(p["H"] / 2, Rmax * 0.12, Rmax * 0.48)  # 管半径由"高度"控制
    R = Rmax - rt
    seg_v = max(12, round(p["seg"] * 0.38))
    return build_torus(R, rt, p["seg"], seg_v,
                       lambda au, av, x, y, z: _col([248, 176, 72], [255, 224, 160], (z / rt + 1) / 2))


def _pawn(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.96, 0.00], [0.96, 0.05], [0.72, 0.10], [0.44, 0.15], [0.34, 0.20],
        [0.28, 0.30], [0.26, 0.44], [0.30, 0.50], [0.50, 0.55], [0.30, 0.60],
        [0.27, 0.64], [0.34, 0.70], [0.46, 0.80], [0.42, 0.90], [0.24, 0.96], [0.00, 1.00]])
    return build_revolution(pr, seg=p["seg"],
                            color_fn=lambda r, z, a, t: _col([60, 66, 78], [150, 158, 172], t))


def _top(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.00, 0.00], [0.40, 0.22], [0.86, 0.40], [1.00, 0.46], [0.90, 0.52],
        [0.30, 0.60], [0.18, 0.74], [0.18, 0.92], [0.12, 1.00]])
    return build_revolution(
        pr, seg=p["seg"], twist=math.radians(p.get("twist") or 0),
        lobes=p.get("lobes") or 0, lobe_amt=0.1 if p.get("lobes") else 0,
        color_fn=lambda r, z, a, t: _col([232, 84, 72], [255, 196, 120], t))


def _goblet(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.90, 0.00], [0.90, 0.04], [0.34, 0.10], [0.12, 0.14], [0.10, 0.45],
        [0.11, 0.50], [0.30, 0.55], [0.60, 0.70], [0.72, 0.86], [0.68, 1.00]])
    return build_revolution(pr, seg=p["seg"],
                            color_fn=lambda r, z, a, t: _col([150, 90, 190], [226, 200, 246], t))


def _bowl(p):
    Rmax = p["D"] / 2
    # 外壁上行 → 翻过杯口 → 内壁下行 → 内底收成极点（真实空腔，可装东西）
    pr = _profile_pts(p["H"], Rmax, [
        [0.52, 0.00], [0.80, 0.10], [0.96, 0.42], [1.00, 0.82], [1.00, 1.00],
        [0.90, 1.00], [0.88, 0.90], [0.72, 0.42], [0.40, 0.22], [0.00, 0.18]])
    return build_revolution(pr, seg=p["seg"],
                            color_fn=lambda r, z, a, t: _col([70, 130, 180], [214, 236, 250], t))


def _pot(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.58, 0.00], [0.62, 0.03], [0.92, 0.84], [1.00, 0.86], [1.00, 1.00],
        [0.88, 1.00], [0.86, 0.92], [0.56, 0.14], [0.00, 0.11]])
    return build_revolution(
        pr, seg=p["seg"], lobes=p.get("lobes") or 0, lobe_amt=0.06 if p.get("lobes") else 0,
        color_fn=lambda r, z, a, t: _col([176, 96, 58], [236, 178, 132], t))


def _mushroom(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.30, 0.00], [0.26, 0.10], [0.22, 0.35], [0.24, 0.48], [0.55, 0.52],
        [0.95, 0.55], [1.00, 0.62], [0.92, 0.75], [0.62, 0.90], [0.30, 0.98], [0.00, 1.00]])

    def cf(r, z, a, t):
        if t < 0.5:
            return _col([242, 232, 212], [246, 238, 222], t * 2)
        return _col([214, 60, 48], [232, 92, 74], (t - 0.5) * 2)

    return build_revolution(pr, seg=p["seg"], color_fn=cf)


def _pin(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.55, 0.00], [0.72, 0.05], [0.97, 0.18], [1.00, 0.28], [0.90, 0.40],
        [0.62, 0.52], [0.45, 0.62], [0.40, 0.70], [0.44, 0.80], [0.52, 0.88],
        [0.50, 0.94], [0.36, 0.99], [0.00, 1.00]])

    def cf(r, z, a, t):
        # 白瓶身 + 颈部红环
        return [220, 40, 44] if 0.60 < t < 0.72 else _col([240, 240, 244], [255, 255, 255], t)

    return build_revolution(pr, seg=p["seg"], color_fn=cf)


def _tree(p):
    Rmax = p["D"] / 2
    # 树干 + 三层锥体裙摆 + 顶尖
    pr = _profile_pts(p["H"], Rmax, [
        [0.22, 0.00], [0.22, 0.08], [0.95, 0.10], [0.45, 0.34], [0.78, 0.36],
        [0.36, 0.58], [0.62, 0.60], [0.24, 0.80], [0.42, 0.82], [0.00, 1.00]])

    def cf(r, z, a, t):
        return [118, 78, 48] if t < 0.09 else _col([26, 112, 58], [92, 190, 108], t)

    return build_revolution(
        pr, seg=p["seg"], twist=math.radians(p.get("twist") or 0),
        lobes=p.get("lobes") or 0, lobe_amt=0.08 if p.get("lobes") else 0, color_fn=cf)


def _lantern(p):
    Rmax = p["D"] / 2
    pr = _profile_pts(p["H"], Rmax, [
        [0.24, 0.00], [0.26, 0.02], [0.32, 0.06], [0.85, 0.18], [1.00, 0.50],
        [0.85, 0.82], [0.32, 0.94], [0.26, 0.98], [0.24, 1.00]])

    def cf(r, z, a, t):
        if t < 0.06 or t > 0.94:
            return [250, 200, 80]
        return _col([200, 30, 30], [244, 88, 58], abs(t - 0.5) * 2)

    lobes = p["lobes"] if p.get("lobes") is not None else 12
    return build_revolution(pr, seg=p["seg"], lobes=lobes, lobe_amt=0.05, color_fn=cf)


def _donut(p):
    Rmax = p["D"] / 2
    rt = min(max(p["H"] / 2, Rmax * 0.12), Rmax * 0.48)
    R = Rmax - rt
    seg_v = max(12, round(p["seg"] * 0.4))

    def cf(au, av, x, y, z):
        # 上半是糖霜（粉），下半是面包（棕金）
        if z > rt * 0.15:
            return _col([238, 110, 160], [250, 160, 196], (math.sin(au * 7) + 1) / 2)
        return _col([206, 148, 84], [232, 186, 122], (z / rt + 1) / 2)

    return build_torus(R, rt, p["seg"], seg_v, cf)


SHAPES: list[dict] = [
    {"id": "vase", "name": "花瓶", "emoji": "🏺", "tag": "家居",
     "defaults": {"H": 120, "D": 80, "seg": 120, "twist": 0, "lobes": 0}, "build": _vase},
    {"id": "spiral", "name": "螺旋花瓶", "emoji": "🌀", "tag": "家居",
     "defaults": {"H": 130, "D": 78, "seg": 140, "twist": 300, "lobes": 7}, "build": _spiral},
    {"id": "gem", "name": "宝石", "emoji": "💎", "tag": "装饰",
     "defaults": {"H": 60, "D": 60, "seg": 8, "twist": 0, "lobes": 0}, "build": _gem},
    {"id": "sphere", "name": "球体 / 椭球", "emoji": "🔮", "tag": "摆件",
     "defaults": {"H": 70, "D": 70, "seg": 96, "twist": 0, "lobes": 0}, "build": _sphere},
    {"id": "egg", "name": "蛋形", "emoji": "🥚", "tag": "摆件",
     "defaults": {"H": 90, "D": 64, "seg": 96, "twist": 0, "lobes": 0}, "build": _egg},
    {"id": "ring", "name": "圆环 / 戒指", "emoji": "💍", "tag": "首饰",
     "defaults": {"H": 24, "D": 70, "seg": 120, "twist": 0, "lobes": 0}, "build": _ring},
    {"id": "pawn", "name": "国际象棋兵", "emoji": "♟", "tag": "桌游",
     "defaults": {"H": 110, "D": 54, "seg": 96, "twist": 0, "lobes": 0}, "build": _pawn},
    {"id": "top", "name": "陀螺", "emoji": "🎯", "tag": "玩具",
     "defaults": {"H": 80, "D": 66, "seg": 96, "twist": 0, "lobes": 0}, "build": _top},
    {"id": "goblet", "name": "高脚杯", "emoji": "🍷", "tag": "家居",
     "defaults": {"H": 120, "D": 62, "seg": 100, "twist": 0, "lobes": 0}, "build": _goblet},
    {"id": "bowl", "name": "碗（带内腔）", "emoji": "🥣", "tag": "餐具",
     "defaults": {"H": 50, "D": 110, "seg": 120, "twist": 0, "lobes": 0}, "build": _bowl},
    {"id": "pot", "name": "花盆（带内腔）", "emoji": "🪴", "tag": "园艺",
     "defaults": {"H": 90, "D": 100, "seg": 110, "twist": 0, "lobes": 0}, "build": _pot},
    {"id": "mushroom", "name": "蘑菇", "emoji": "🍄", "tag": "摆件",
     "defaults": {"H": 85, "D": 80, "seg": 100, "twist": 0, "lobes": 0}, "build": _mushroom},
    {"id": "pin", "name": "保龄球瓶", "emoji": "🎳", "tag": "玩具",
     "defaults": {"H": 130, "D": 56, "seg": 96, "twist": 0, "lobes": 0}, "build": _pin},
    {"id": "tree", "name": "圣诞树", "emoji": "🎄", "tag": "节日",
     "defaults": {"H": 130, "D": 90, "seg": 96, "twist": 0, "lobes": 0}, "build": _tree},
    {"id": "lantern", "name": "中式灯笼", "emoji": "🏮", "tag": "节日",
     "defaults": {"H": 85, "D": 95, "seg": 120, "twist": 0, "lobes": 12}, "build": _lantern},
    {"id": "donut", "name": "甜甜圈", "emoji": "🍩", "tag": "美食",
     "defaults": {"H": 30, "D": 90, "seg": 110, "twist": 0, "lobes": 0}, "build": _donut},
]


def shape_list() -> list[dict]:
    """给 API 用的元数据（不含 build 函数）。"""
    return [{k: v for k, v in s.items() if k != "build"} for s in SHAPES]


def by_id(shape_id: str) -> dict | None:
    for s in SHAPES:
        if s["id"] == shape_id:
            return s
    return None


def build(shape_id: str, params: dict | None = None) -> trimesh.Trimesh:
    """生成指定模型实例，返回带顶点色的 trimesh.Trimesh。

    params 可覆盖 defaults 中的 H（高 mm）/ D（直径 mm）/ seg（分段）/
    twist（扭转度数）/ lobes（棱数）。范围会被安全钳制。
    """
    sh = by_id(shape_id)
    if sh is None:
        raise ValueError(f"未知模型实例: {shape_id}")
    d = dict(sh["defaults"])
    p = params or {}
    merged = {
        "H": _clamp(float(p.get("H", d["H"])), 5.0, 300.0),
        "D": _clamp(float(p.get("D", d["D"])), 5.0, 300.0),
        "seg": int(_clamp(float(p.get("seg", d["seg"])), 3, 256)),
        "twist": _clamp(float(p.get("twist", d["twist"])), -1080.0, 1080.0),
        "lobes": int(_clamp(float(p.get("lobes", d["lobes"])), 0, 32)),
    }
    V, F, C = sh["build"](merged)
    mesh = trimesh.Trimesh(vertices=V, faces=F, process=False)
    if C is not None:
        rgba = np.hstack([C, np.full((len(C), 1), 255, dtype=np.uint8)])
        mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=rgba)
    return mesh
