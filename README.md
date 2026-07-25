# SnapPrint · 咔印3D 社区

> 上传你自己的 3D 模型，系统自动分析「它能不能打」，并分享到社区画廊让成员一起看。
> 开源 · 中文友好 · Apache-2.0 商用友好。

**🌐 在线 UI 预览（前端）：<https://e987b12ce3c541599e63f76bfc9fc8cf.app.codebuddy.work>** —— 纯静态预览，画廊 / 上传 / 评论需后端。完整社区推荐用 **Railway 一键部署**（见 [docs/部署.md 第七节](docs/部署.md)），或本地 `python -m app.main`。

---

## 它解决什么问题

「图生 3D」的工具已经很多，但真正的 3D 打印爱好者手里往往已经有一堆 `.stl / .obj`——
它们能不能打、要不要支撑、会不会翘边，却没人告诉过你。SnapPrint 社区版只做一件事：

**把你已有的模型，变成一份人人可读的「可打印性体检报告」，并放进社区一起讨论。**

- 网格不水密 → 切片报错？自动检测
- 悬垂太大、要加支撑？算出占比与建议
- 贴床接触太小、会翘边？给出 Brim 建议
- 重量、时长、尺寸对不对？按你选的打印机/材料预估

## 功能

- 📤 **上传即分析**：拖入 `.stl / .obj / .ply / .3mf / .glb / .gltf / .off`，秒级出报告
- 🩺 **可打印性报告**：水密性、悬垂占比、接触面、尺寸、体积、层高、填充、支撑建议、Brim、预估重量与时长
- 🏅 **可打印性评分 0–100**：一眼看出模型「省不省心」
- 🖼️ **社区画廊**：所有模型按时间倒序，卡片展示评分 / 尺寸 / 作者
- 💬 **评论**：成员对任意模型点评、给建议
- 📊 **评分榜**：社区里「最省心模型」排行
- 🖨️ **机型 / 材料预设**：拓竹 / 创想 / Prusa / Elegoo / Anycubic 等常见机型 + PLA/PETG/TPU，自动匹配热床与参数
- 🔐 **API Key 鉴权 + 限流**：内网 / 小团队部署可设 `SNAPRINT_API_KEY` 与 `SNAPRINT_RATE_LIMIT`

## 快速开始

### 方式一：启动脚本（推荐）
```bash
python scripts/start_backend.py
# 或自定义端口： PORT=8080 python scripts/start_backend.py
```
浏览器打开 http://localhost:8000

### 方式二：Docker
```bash
docker compose up --build
```

### 方式三：手动
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

默认完全开放（方便本地 / 公开 Demo）。无需显卡、无需任何模型权重——分析纯靠 `trimesh` 几何计算。

## API 速览

| 接口 | 说明 |
|---|---|
| `POST /api/upload` | 上传模型文件 + 自动分析，进入画廊 |
| `GET  /api/gallery` | 画廊列表（分页 `?limit=&offset=`） |
| `GET  /api/models/{id}` | 模型详情 = 分析报告 + 评论 |
| `POST /api/models/{id}/comments` | 发表评论（`author`、`body`） |
| `GET  /api/presets` | 打印机 / 材料预设（前端下拉用） |
| `GET  /api/scoreboard` | 可打印性评分排行榜 |

`POST /api/upload` 表单字段：`file`（必填）、`author`、`printer`、`material`。
分析返回 JSON 含 `score` 与完整 `report` 字段（详见 `app/advisor.py`）。

## 部署与安全

详见 [docs/部署.md](docs/部署.md)。关键环境变量：

- `SNAPRINT_API_KEY`：设置后所有 `/api/*` 需携带请求头 `X-API-Key`
- `SNAPRINT_RATE_LIMIT=N`：每客户端每分钟 N 次限流（0=不限）
- `SNAPRINT_CORS_ORIGINS`：逗号分隔的可信前端来源（默认锁定公开 Demo + 本地地址）
- `SNAPRINT_MAX_UPLOAD_MB`：单文件大小上限（默认 50）

数据落盘：`data/snapprint.db`（SQLite，社区数据库）与 `outputs/uploads/`（模型原文件），均已被 `.gitignore` 忽略。

## 项目结构

```
snapprint/
├── app/
│   ├── main.py          # FastAPI 后端（托管 web/ 静态前端 + 社区 API）
│   ├── advisor.py       # 可打印性 / 支撑建议分析 + 评分（核心引擎）
│   ├── postprocess.py   # 网格后处理工具（水密/缩放/统计）
│   └── db.py            # 社区数据层（零依赖 SQLite：模型 + 评论）
├── web/                 # 简洁单页前端：上传 → 画廊 → 详情 → 评论
├── scripts/             # start_backend.py 启动脚本
├── docs/                # 部署文档
├── data/                # SQLite 社区数据库（运行时生成，已 gitignore）
└── outputs/uploads/     # 上传的模型原文件（运行时生成，已 gitignore）
```

## 许可证

[Apache-2.0](LICENSE) —— 商用友好，欢迎二次开发与集成。

⭐ 如果你觉得有用，欢迎 Star、提 Issue、发 PR。让「模型能不能打」对每个人都是一句话的事。
