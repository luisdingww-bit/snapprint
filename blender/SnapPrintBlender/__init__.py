# SnapPrint 咔印3D · Blender 插件
# 在 Blender 内直接调用本地 SnapPrint 后端（照片→可打印3D），
# 并可分析当前网格的可打印性 / 支撑建议。
# 仅用标准库，无需 pip 安装任何依赖。
bl_info = {
    "name": "SnapPrint 咔印3D",
    "author": "luisdingww-bit",
    "version": (0, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D › 右侧栏 › SnapPrint",
    "description": "从图片生成可打印3D模型，并分析网格的支撑/切片建议（需本地 SnapPrint 后端）",
    "category": "3D Printing",
}

import bpy
import os
import io
import json
import time
import webbrowser
import urllib.request
import urllib.error
import tempfile

BACKEND_DEFAULT = "http://localhost:8000"
ONLINE_URL = "https://snapprint-3d.surge.sh/"

# ---------------------------------------------------------------------------
# 轻量 HTTP 辅助（标准库 multipart 上传 + JSON GET）
# ---------------------------------------------------------------------------
_BOUNDARY = "----SnapPrintBoundary7MA4YWxkTrZu0gW"


def _post_multipart(url, fields, files):
    body = []
    for k, v in fields.items():
        body.append(("--" + _BOUNDARY).encode())
        body.append(('Content-Disposition: form-data; name="%s"' % k).encode())
        body.append(b"")
        body.append(str(v).encode("utf-8"))
    for k, (fn, data, ctype) in files.items():
        body.append(("--" + _BOUNDARY).encode())
        body.append(('Content-Disposition: form-data; name="%s"; filename="%s"'
                     % (k, fn)).encode())
        body.append(("Content-Type: %s" % ctype).encode())
        body.append(b"")
        body.append(data)
    body.append(("--" + _BOUNDARY + "--").encode())
    body.append(b"")
    req = urllib.request.Request(url, data=b"\r\n".join(body), method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + _BOUNDARY)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return resp.read().decode("utf-8")


def _get_bytes(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _get_json(url, timeout=240):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# 场景属性
# ---------------------------------------------------------------------------
class SnapPrintProps(bpy.types.PropertyGroup):
    backend_url: bpy.props.StringProperty(
        name="后端地址",
        description="本地 SnapPrint 后端（python -m app.main 启动）",
        default=BACKEND_DEFAULT,
    )
    image_path: bpy.props.StringProperty(
        name="图片",
        description="用于生成的照片 / Logo",
        subtype="FILE_PATH",
    )
    mode: bpy.props.EnumProperty(
        name="模式",
        items=[
            ("relief", "浮雕", "照片灰度→浮雕高度"),
            ("solid3d", "真实3D", "旋转体/几何（忽略图片）"),
            ("extrude", "2D 拉伸", "轮廓拉伸"),
        ],
        default="relief",
    )
    report: bpy.props.StringProperty(name="报告", default="")


# ---------------------------------------------------------------------------
# 操作符
# ---------------------------------------------------------------------------
class SNAPPRINT_OT_generate(bpy.types.Operator):
    bl_idname = "snapprint.generate"
    bl_label = "从图片生成浮雕"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.snapprint
        img = bpy.path.abspath(props.image_path)
        if not img or not os.path.isfile(img):
            self.report({"ERROR"}, "请先选择一张图片")
            return {"CANCELLED"}
        base = props.backend_url.rstrip("/")
        try:
            with open(img, "rb") as f:
                data = f.read()
            ctype = "image/png" if img.lower().endswith(".png") else "image/jpeg"
            self.report({"INFO"}, "提交生成任务到 %s …" % base)
            res = json.loads(_post_multipart(
                base + "/api/generate_async",
                {"mode": props.mode},
                {"file": (os.path.basename(img), data, ctype)},
            ))
            tid = res.get("task_id")
            if not tid:
                self.report({"ERROR"}, "后端未返回 task_id: %s" % res)
                return {"CANCELLED"}

            obj_url = None
            for _ in range(360):  # 最多等 6 分钟
                t = _get_json(base + "/api/tasks/" + tid)
                if t["status"] == "done":
                    obj_url = t["result"]["files"].get("obj")
                    break
                if t["status"] == "error":
                    self.report({"ERROR"}, "生成失败: " + t.get("error", ""))
                    return {"CANCELLED"}
                time.sleep(1.0)
            if not obj_url:
                self.report({"ERROR"}, "未拿到模型文件链接")
                return {"CANCELLED"}

            obj_bytes = _get_bytes(base + obj_url)
            tmp = os.path.join(tempfile.gettempdir(), "snapprint_model.obj")
            with open(tmp, "wb") as f:
                f.write(obj_bytes)

            # 导入网格
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=tmp)
            else:  # 老版本
                bpy.ops.import_scene.obj(filepath=tmp)
            self.report({"INFO"}, "已导入 SnapPrint 模型 ✓")
            props.report = "已生成并导入网格：\n" + tmp
        except urllib.error.URLError as e:
            self.report({"ERROR"}, "无法连接后端 %s：%s" % (base, e))
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, "出错: %s" % e)
            return {"CANCELLED"}
        return {"FINISHED"}


class SNAPPRINT_OT_analyze(bpy.types.Operator):
    bl_idname = "snapprint.analyze"
    bl_label = "分析可打印性 / 支撑"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.snapprint
        objs = [o for o in context.selected_objects if o.type == "MESH"]
        if not objs:
            self.report({"ERROR"}, "请先选中一个网格物体")
            return {"CANCELLED"}
        base = props.backend_url.rstrip("/")
        try:
            # 导出选中网格为临时 STL
            tmp = os.path.join(tempfile.gettempdir(), "snapprint_analyze.stl")
            bpy.ops.export_mesh.stl(filepath=tmp, use_selection=True)
            with open(tmp, "rb") as f:
                data = f.read()
            self.report({"INFO"}, "上传网格到 %s 分析…" % base)
            res = json.loads(_post_multipart(
                base + "/api/analyze",
                {"mode": "import"},
                {"file": ("model.stl", data, "application/octet-stream")},
            ))
            lines = []
            lines.append("尺寸：%s mm" % " × ".join("%.1f" % x for x in res["size_mm"]))
            lines.append("体积：%.1f cm³" % res["volume_cm3"])
            lines.append("层高：%.2f mm" % res["layer_height"])
            lines.append("填充：%d%%" % res["infill"])
            lines.append("支撑：%s（%s）" % ("开启" if res["supports"] else "免", res["support_reason"]))
            if res["supports"]:
                lines.append("  类型：%s  密度：%.0f%%  阈值：%d°" % (
                    res["support_type"], res["support_density"] * 100, res["support_threshold_deg"]))
            lines.append("Brim：%s" % ("%g mm" % res["brim_mm"] if res["brim_mm"] else "关闭"))
            if res.get("orientation_advice"):
                lines.append("💡 " + res["orientation_advice"])
            for w in res.get("warnings", []):
                lines.append("⚠ " + w)
            props.report = "\n".join(lines)
            self.report({"INFO"}, "分析完成 ✓")
        except urllib.error.URLError as e:
            self.report({"ERROR"}, "无法连接后端 %s：%s" % (base, e))
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, "出错: %s" % e)
            return {"CANCELLED"}
        return {"FINISHED"}


class SNAPPRINT_OT_open_online(bpy.types.Operator):
    bl_idname = "snapprint.open_online"
    bl_label = "打开 SnapPrint 在线 Demo"
    bl_options = {"REGISTER"}

    def execute(self, context):
        webbrowser.open(ONLINE_URL)
        self.report({"INFO"}, "已在浏览器打开 %s" % ONLINE_URL)
        return {"FINISHED"}


class SNAPPRINT_OT_open_backend(bpy.types.Operator):
    bl_idname = "snapprint.open_backend"
    bl_label = "打开本地后端"
    bl_options = {"REGISTER"}

    def execute(self, context):
        webbrowser.open(context.scene.snapprint.backend_url.rstrip("/") + "/")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 面板
# ---------------------------------------------------------------------------
class SNAPPRINT_PT_panel(bpy.types.Panel):
    bl_label = "SnapPrint 咔印3D"
    bl_idname = "VIEW3D_PT_snapprint"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SnapPrint"

    def draw(self, context):
        layout = self.layout
        props = context.scene.snapprint

        layout.prop(props, "backend_url")
        row = layout.row(align=True)
        row.operator("snapprint.open_backend", text="本地后端", icon="WORLD")
        row.operator("snapprint.open_online", text="在线 Demo", icon="URL")

        box = layout.box()
        box.label(text="生成模型（需本地后端运行）", icon="MESH_DATA")
        box.prop(props, "image_path")
        box.prop(props, "mode")
        box.operator("snapprint.generate", icon="MOD_REMESH")

        box = layout.box()
        box.label(text="分析当前选中网格", icon="OUTLINER_OB_MESH")
        box.operator("snapprint.analyze", icon="VIEWZOOM")

        if props.report:
            box = layout.box()
            box.label(text="结果", icon="INFO")
            col = box.column(align=True)
            col.scale_y = 0.8
            for ln in props.report.split("\n"):
                col.label(text=ln)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
_CLASSES = [
    SnapPrintProps,
    SNAPPRINT_OT_generate,
    SNAPPRINT_OT_analyze,
    SNAPPRINT_OT_open_online,
    SNAPPRINT_OT_open_backend,
    SNAPPRINT_PT_panel,
]


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.snapprint = bpy.props.PointerProperty(type=SnapPrintProps)


def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.snapprint


if __name__ == "__main__":
    register()
