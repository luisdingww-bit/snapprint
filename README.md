# SnapPrint · 咔印3D

> 一张照片，生成一个**可直接 3D 打印**的模型。
> 开源 · 中文友好 · Apache-2.0 商用友好。

![mode](https://img.shields.io/badge/license-Apache--2.0-green) ![mode](https://img.shields.io/badge/mode-离线浮雕%20%7C%20Hunyuan3D%20%7C%20TripoSR-blue) [![demo](https://img.shields.io/badge/在线体验-snapprint--3d.surge.sh-ff5a3c)](https://snapprint-3d.surge.sh)

**🌐 在线公共 Demo（无需安装）：<https://snapprint-3d.surge.sh>** — 纯浏览器版：照片浮雕 / 2D轮廓拉伸 / 真实3D几何 / 模型导入 / 3DGS高斯泼溅五模式 + 33 款内置模型库 + 切片就绪预设，全程本地计算、文件不上传任何服务器。

---

## 它解决什么问题

「图生 3D」的开源项目已经不少（TripoSR、InstantMesh、Wonder3D、Hunyuan3D…），但它们大多止步于**输出一个裸网格**。真正想拿去 3D 打印的人，还要自己面对一堆麻烦：

- 网格不水密 → 切片软件报错
- 单位不对、方向歪了 → 打出来尺寸错、要加支撑
- 没有颜色 → 只能打单色
- 环境难配、要显卡 → 普通人跑不起来

**SnapPrint 的差异点就是：不跟你比「谁的 3D 最通用」，而是把「照片 → 可打印成品」这一公里走完。**

## 核心差异化

| 维度 | 多数图生 3D 项目 | SnapPrint |
|------|----------------|-----------|
| **定位** | 通用 3D 生成 | 垂直做 **3D 打印**（手办 / 玩具 / 浮雕刻印） |
| **输出** | 裸网格 | **水密、可切片、按毫米定尺、带颜色** |
| **开箱即用** | 常需 GPU + 复杂环境 | 内置**离线浮雕模式**，零模型依赖，CPU 也能跑 |
| **友好度** | 英文为主 | **中文 Web UI + 中文文档 + 国内可下载权重** |
| **许可证** | 不少是「非商业」 | **Apache-2.0 商用友好**（吸引二次开发与商用） |

## 功能

- 🖼️ **上传照片 → 一键生成**，浏览器里完成，参数（尺寸/底座/浮雕高度）实时可调
- 🧊 **离线浮雕模式**：把照片亮度转成带颜色的浮雕刻印，零依赖、保证可跑
- 🤖 **AI 模式（可插拔）**：统一接口接入 Hunyuan3D / TripoSR 等开源权重，获得更立体的模型
- 🔧 **打印级后处理**：自动水密修复、减面、摆正、缩放到毫米
- 📦 **多格式导出**：`OBJ`（几何，全切片器兼容）/ `PLY`（顶点颜色）/ `3MF`（颜色 + 打印元数据）
- ⏳ **异步任务队列**：AI 模式耗时长时提交即返回 `task_id`，前端轮询显示分阶段进度条（解码 → 生成 → 后处理 → 导出）
- 🖨️ **切片就绪预设**：按拓竹 / 创想 / Prusa / Elegoo / Anycubic 等常见机型 + PLA/PETG/TPU 材料，基于模型几何自动推荐层高、填充、支撑与 Brim，一键导出 PrusaSlicer / OrcaSlicer 可导入的 `.ini`（在线 Demo 内置）
- 🌐 **中文界面与文档**，面向国内 3D 打印爱好者与创作者

## 快速开始（3 种方式）

### 方式一：一键脚本（推荐新手）
```bash
# Linux / macOS
bash scripts/run.sh
# Windows
scripts\install_windows.bat
```
浏览器打开 http://localhost:8000 （不想本地部署？直接用[在线 Demo](https://snapprint-3d.surge.sh)）

### 方式二：Docker
```bash
docker compose up --build
```

### 方式三：手动
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

> 默认即用**离线浮雕模式**，不需要显卡、不需要下载任何模型权重。

## 接入 AI 模式（可选）

想获得更立体的「照片 → 真实 3D 模型」效果，把开源权重与推理代码放到 `models/` 下，
按 `docs/部署.md` 接入 Hunyuan3D 或 TripoSR 即可。SnapPrint 只定义统一接口，不捆绑任何一家。

## 项目结构

```
snapprint/
├── app/
│   ├── main.py          # FastAPI Web 后端
│   ├── pipeline.py       # 主流水线入口 run()
│   ├── advisor.py        # 可打印性 / 支撑建议分析
│   ├── backends.py       # 离线浮雕 + AI 模式适配层
│   ├── postprocess.py    # 水密/减面/摆正/缩放/导出（打印护城河）
│   └── config.py         # 默认参数（毫米级）
├── frontend/index.html   # 中文 Web UI（零构建）
├── web/                  # 纯浏览器版（surge 托管）：五模式 + 模型库 + 切片预设
├── blender/SnapPrintBlender/  # Blender 插件（调本地后端）
├── comfyui/SnapPrintNode/     # ComfyUI 自定义节点
├── scripts/              # 一键启动脚本
├── docs/                 # 部署 / 贡献 / 路线图
├── outputs/              # 生成的 3D 文件
└── Dockerfile / docker-compose.yml
```

## 集成：Blender 插件 / ComfyUI 节点

SnapPrint 把「照片 → 可打印3D」做成可嵌入其他工具的能力，枢纽是**本地后端**
（`python scripts/start_backend.py` → `http://localhost:8000`），提供：

| 接口 | 说明 |
|---|---|
| `POST /api/generate_async` | 提交生成，立即返回 `task_id` |
| `GET  /api/tasks/{id}` | 轮询状态 / 分阶段进度 / 结果（含下载链接） |
| `POST /api/analyze` | 上传图片或网格（stl/obj/ply/3mf），返回可打印性 / 支撑建议 JSON |

### Blender 插件
1. 先把 `blender/SnapPrintBlender/` 整个文件夹复制到 Blender 的 `scripts/addons/` 目录；
2. 编辑 → 偏好设置 → 插件 → 搜索 `SnapPrint` → 启用；
3. 右侧栏出现 **SnapPrint** 面板：填本地后端地址、选图片与模式，点「从图片生成浮雕」即自动生成并导入网格；选中网格点「分析可打印性 / 支撑」查看层高、填充、支撑（类型/密度/阈值）与摆放建议。

### ComfyUI 节点
1. 把 `comfyui/SnapPrintNode/` 整个文件夹放入 ComfyUI 的 `custom_nodes/` 目录，重启 ComfyUI；
2. 节点搜索 `SnapPrint` 即可看到 **SnapPrint 生成 (图片→3D)** 与 **SnapPrint 分析 (可打印性)**；
3. 前者接收 `IMAGE` 输出网格文件路径（可串联后续 3D 节点），后者输出支撑/切片建议 JSON。

> 所有集成共享同一套几何口径（悬垂角阈值 45°、支撑密度/类型、Brim、层高/填充），与 Web 切片预设面板一致。

## 路线图

见 [docs/路线图.md](docs/路线图.md)。v0.2（异步任务队列 / 在线公共 Demo / 切片就绪预设）与 v0.3（自动支撑建议 / Blender 插件 / ComfyUI 节点）均已完成 ✅。

## 许可证

[Apache-2.0](LICENSE) —— 商用友好，欢迎二次开发与集成。

---

⭐ 如果你觉得这个项目有用，欢迎 Star、提 Issue、发 PR。让「照片变手办」对每个人都很简单。
