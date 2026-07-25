"""网格后处理：水密修复、减面、摆正、缩放到毫米、导出可打印格式。

差异化点：多数「图生 3D」项目只输出裸网格，而 3D 打印真正需要的是
「水密、可切片、尺寸正确」的成品。这一层正是 SnapPrint 面向打印的护城河。
"""
from __future__ import annotations

from pathlib import Path

import trimesh


def postprocess(
    mesh: "trimesh.Trimesh",
    *,
    target_triangles: int = 60000,
    fill_holes: bool = True,
    orient_up: bool = True,
    unit_scale: float | None = None,
) -> "trimesh.Trimesh":
    """把任意网格处理成可打印状态。

    unit_scale: 若原始网格单位不是毫米，传入缩放系数（目标=毫米）。
                例如原始以「米」为单位则传 1000。
    """
    if mesh is None or len(mesh.vertices) == 0:
        raise ValueError("空网格，无法后处理")

    # 1) 合并、去重、修复缠绕方向
    mesh = mesh.process(validate=True)

    # 2) 自动补洞（保证水密，切片软件才不报错）
    if fill_holes:
        trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_winding(mesh)
        # 再次尝试封闭可能的边界
        if not mesh.is_watertight:
            trimesh.repair.fill_holes(mesh)

    # 3) 单位归一化到毫米
    if unit_scale is not None and unit_scale != 1.0:
        mesh = mesh.apply_scale(unit_scale)
    else:
        # 启发式：若尺寸远大于现实（如百位以上），假定是米->毫米
        extent = mesh.extents.max()
        if extent > 1000:
            mesh = mesh.apply_scale(0.001)  # 米 -> 毫米
        elif extent > 100:
            mesh = mesh.apply_scale(0.1)    # 分米 -> 毫米

    # 4) 摆正：底面落在 z=0，整体朝上
    if orient_up:
        # 把质心 x/y 居中、底面贴 z=0
        bounds = mesh.bounds
        offset = [-(bounds[0][0] + bounds[1][0]) / 2,
                  -(bounds[0][1] + bounds[1][1]) / 2,
                  -bounds[0][2]]
        mesh = mesh.apply_translation(offset)

    # 5) 减面（保护打印机显存与切片速度）
    if target_triangles and len(mesh.faces) > target_triangles:
        try:
            mesh = mesh.simplify_quadric_decimation(target_triangles)
        except Exception:
            # 某些网格类型不支持，跳过
            pass

    return mesh


def export_all(
    mesh: "trimesh.Trimesh",
    out_dir: "Path | str",
    name: str = "model",
    *,
    export_obj: bool = True,
    export_ply_vertex_color: bool = True,
    export_3mf: bool = True,
) -> dict:
    """导出 OBJ / PLY(顶点色) / 3MF，返回 {格式: 路径}。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}

    if export_obj:
        p = out_dir / f"{name}.obj"
        mesh.export(str(p))
        result["obj"] = str(p)

    if export_ply_vertex_color:
        p = out_dir / f"{name}.ply"
        mesh.export(str(p))
        result["ply"] = str(p)

    if export_3mf:
        try:
            p = out_dir / f"{name}.3mf"
            scene = trimesh.Scene()
            scene.add_geometry(mesh)
            scene.export(str(p))
            result["3mf"] = str(p)
        except Exception as e:  # 3MF 依赖较多，失败不影响其他格式
            result["3mf_error"] = str(e)

    return result


def mesh_stats(mesh: "trimesh.Trimesh") -> dict:
    """返回面向打印的关键统计。"""
    try:
        volume_cm3 = float(mesh.volume) / 1000.0  # mm^3 -> cm^3
    except Exception:
        volume_cm3 = 0.0
    return {
        "watertight": bool(mesh.is_watertight),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "bounds_mm": [[float(v) for v in mesh.bounds[0]],
                      [float(v) for v in mesh.bounds[1]]],
        "size_mm": [float(v) for v in mesh.extents],
        "volume_cm3": round(volume_cm3, 3),
    }
