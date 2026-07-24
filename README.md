# SnapPrint · 咔印3D

> 一张照片，生成一个**可直接 3D 打印**的模型。
> 开源 · 中文友好 · Apache-2.0 商用友好。

![mode](https://img.shields.io/badge/license-Apache--2.0-green) ![mode](https://img.shields.io/badge/mode-离线浮雕%20%7C%20Hunyuan3D%20%7C%20TripoSR-blue) [![demo](https://img.shields.io/badge/在线体验-snapprint--3d.surge.sh-ff5a3c)](https://snapprint-3d.surge.sh)

**🌐 在线体验（无需安装）：<https://snapprint-3d.surge.sh>** — 纯浏览器版，照片→水密浮雕模型→STL/OBJ/PLY 下载，全程本地计算、图片不上传任何服务器。

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
- 🌐 **中文界面与文档**，面向国内 3D 打印爱好者与创作者

## 快速开始（3 种方式）

### 方式一：一键脚本（推荐新手）
```bash
# Linux / macOS
bash scripts/run.sh
# Windows
scripts\install_windows.bat
```
浏览器打开 http://localhost:8000

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
│   ├── backends.py       # 离线浮雕 + AI 模式适配层
│   ├── postprocess.py    # 水密/减面/摆正/缩放/导出（打印护城河）
│   └── config.py         # 默认参数（毫米级）
├── frontend/index.html   # 中文 Web UI（零构建）
├── scripts/              # 一键启动脚本
├── docs/                 # 部署 / 贡献 / 路线图
├── outputs/              # 生成的 3D 文件
└── Dockerfile / docker-compose.yml
```

## 路线图

见 [docs/路线图.md](docs/路线图.md)：自动支撑生成、Blender/ComfyUI 插件、批量处理、模型动物园、在线 Demo。

## 许可证

[Apache-2.0](LICENSE) —— 商用友好，欢迎二次开发与集成。

---

⭐ 如果你觉得这个项目有用，欢迎 Star、提 Issue、发 PR。让「照片变手办」对每个人都很简单。
