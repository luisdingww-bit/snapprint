# SnapPrint 咔印3D · ComfyUI 自定义节点
# 把「照片 → 可打印3D」接入 ComfyUI 工作流。
# 节点直接调用本地 SnapPrint 后端（python -m app.main），无需重写模型逻辑。
import io
import os
import json
import time
import tempfile

import urllib.request
import urllib.error

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


def _tensor_to_png_bytes(image):
    """ComfyUI IMAGE: torch.Tensor [B,H,W,C] 0..1 float -> PNG bytes。"""
    import torch
    import numpy as np
    from PIL import Image

    arr = image[0].cpu().float().numpy()  # HWC
    arr = (np.clip(arr, 0.0, 1.0) * 255.0).astype("uint8")
    pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


class SnapPrintGenerate:
    """图片 → 可打印3D网格（OBJ/PLY/3MF），返回网格文件路径，可串联后续 3D 节点。"""

    OUTPUT_NODE = True
    CATEGORY = "SnapPrint"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("mesh_path",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["relief", "solid3d", "extrude"], {"default": "relief"}),
                "format": (["obj", "ply", "3mf"], {"default": "obj"}),
                "backend_url": ("STRING", {"default": "http://localhost:8000", "multiline": False}),
            }
        }

    def generate(self, image, mode, format, backend_url):
        base = backend_url.rstrip("/")
        try:
            png = _tensor_to_png_bytes(image)
            res = json.loads(_post_multipart(
                base + "/api/generate_async",
                {"mode": mode},
                {"file": ("input.png", png, "image/png")},
            ))
            tid = res.get("task_id")
            if not tid:
                return (json.dumps({"error": "no task_id: %s" % res}, ensure_ascii=False),)

            obj_url = None
            for _ in range(360):  # 最多等 6 分钟
                t = _get_json(base + "/api/tasks/" + tid)
                if t["status"] == "done":
                    obj_url = t["result"]["files"].get(format) or t["result"]["files"].get("obj")
                    break
                if t["status"] == "error":
                    return (json.dumps({"error": t.get("error", "")}, ensure_ascii=False),)
                time.sleep(1.0)
            if not obj_url:
                return (json.dumps({"error": "no mesh file"}, ensure_ascii=False),)

            data = _get_bytes(base + obj_url)
            ext = format if format in ("obj", "ply", "3mf") else "obj"
            tmp = os.path.join(tempfile.gettempdir(), "snapprint_%s.%s" % (tid, ext))
            with open(tmp, "wb") as f:
                f.write(data)
            return (tmp,)
        except urllib.error.URLError as e:
            return (json.dumps({"error": "cannot reach backend %s: %s" % (base, e)}, ensure_ascii=False),)
        except Exception as e:
            return (json.dumps({"error": str(e)}, ensure_ascii=False),)


class SnapPrintAnalyze:
    """分析网格/图片的可打印性，输出支撑/切片建议 JSON 字符串。"""

    OUTPUT_NODE = True
    CATEGORY = "SnapPrint"
    FUNCTION = "analyze"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report_json",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["relief", "solid3d", "extrude", "import"], {"default": "relief"}),
                "backend_url": ("STRING", {"default": "http://localhost:8000", "multiline": False}),
            }
        }

    def analyze(self, image, mode, backend_url):
        base = backend_url.rstrip("/")
        try:
            png = _tensor_to_png_bytes(image)
            res = json.loads(_post_multipart(
                base + "/api/analyze",
                {"mode": mode},
                {"file": ("input.png", png, "image/png")},
            ))
            return (json.dumps(res, ensure_ascii=False, indent=2),)
        except Exception as e:
            return (json.dumps({"error": str(e)}, ensure_ascii=False),)


# ComfyUI 兼容别名（部分版本会探测 NODE_CLASS_MAPPINGS）
NODE_CLASS_MAPPINGS = {
    "SnapPrintGenerate": SnapPrintGenerate,
    "SnapPrintAnalyze": SnapPrintAnalyze,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SnapPrintGenerate": "SnapPrint 生成 (图片→3D)",
    "SnapPrintAnalyze": "SnapPrint 分析 (可打印性)",
}
