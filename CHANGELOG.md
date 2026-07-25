# 更新日志 Changelog

所有 notable 变更都会记录在此文件。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.7.0] - 2026-07-25 · 补回图生 3D（照片生成）

> 把社区版 v0.6.0 砍掉的「图生 3D」能力补回，但聚焦保留真正有用的部分：
> 离线浮雕（零依赖、保水密、可打）+ AI 模式适配层（缺权重优雅报错），并让它
> 生成即分析、进社区画廊。社区主线（上传/画廊/评论）完全不动。

### 新增
- **图生 3D 编排 `app/pipeline.py`**：照片 → 网格 → 后处理，复用原 `af389ee` 实现。
- **AI 后端适配层 `app/backends.py`**：Hunyuan3D / TripoSR / SF3D / Trellis 适配，
  缺依赖/权重时返回清晰指引，不静默失败。
- **配置 + 模型动物园 `app/config.py`**：`MODEL_ZOO`（后端清单 + 速度/贴图标签，
  本机权重可用性探测）。
- **`POST /api/generate`**：照片 → 可打印 3D。
  - `mode=relief`（默认）：离线浮雕，纯 numpy/Pillow/trimesh，任何环境秒级出网格。
  - `mode=ai` / 指定 `model`：走 AI 后端，需自备 GPU + 权重，否则返回明确指引。
  - 生成的网格自动做可打印性分析并发布到社区画廊（与上传模型同报告链路）。
- **`GET /api/models`**：模型动物园列表 + 本机权重可用性探测，前端「照片生成」面板用。
- **前端「照片生成」面板**（`web/index.html` + `web/app.js`）：图片选择 + 模式选择 +
  生成 + 复用报告渲染与下载；nav 增加「照片生成」入口；社区页面不被覆盖。

### 变更
- **依赖补回**：`requirements.txt` 加回 `Pillow>=10.0`、`scipy>=1.10`、`networkx>=3.0`
  （trimesh 的后处理需 scipy/networkx；刻意不引 `[easy]` 的 rtree/shapely/lxml 重依赖）。
- 版本号 `0.6.0` → `0.7.0`，路由文档注释与 `/api/health` 同步更新。

### 说明
- 浮雕模式零依赖可跑（无需显卡/权重）；AI 模式需自备 GPU + 权重，缺失时返回指引。
- 仅补生成能力，Surge 落地页（链接跳转 Railway 上传）与社区 API 均不受影响。

## [0.6.1] - 2026-07-25 · Railway 一键部署支持

> 让 SnapPrint 社区版零服务器运维上线：内置 Railway 配置，从 GitHub 一键部署，
> 并补上数据持久化支持与部署文档。

### 新增
- **`railway.json`**：Nixpacks 构建 + `uvicorn app.main:app` 启动 + `/api/health`
  健康检查，支持从 GitHub 仓库一键部署到 Railway 免费层。
- **`runtime.txt`**：锁定 Python 3.11，保证 `trimesh` / `FastAPI` 构建稳定。
- **`app/db.py` 支持 `SNAPRINT_DATA_DIR` 环境变量**：Railway 挂 Volume 到该目录即
  可持久化社区数据库与上传文件，默认仍用仓库内 `data/`。
- **`docs/部署.md` 新增「第七节 Railway 免费托管」**：部署步骤、ephemeral 存储限制
  与 Volume 持久化方案。

### 变更
- **依赖精简（提升 Railway 构建成功率）**：`requirements.txt` 由 `trimesh[easy]` 改为
  纯核心 `trimesh`，移除未使用的 `Pillow`。STL/OBJ/PLY/3MF/GLB/GLTF/OFF 加载与几何
  分析均为 trimesh 内置能力，无需 `[easy]` 额外轮子；原配置会拖入 scipy/rtree/
  shapely/lxml 等用不到的重依赖，在部分构建环境易致安装缓慢或失败。已在全新环境实测
  验证（trimesh 4.12.2，uvicorn 真实进程跑通上传/分析/画廊/评论全链路）。
- **新增 `Procfile`**：`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`，
  作为 railway.json startCommand 的双保险，避免个别构建器忽略配置文件启动命令。

## [0.6.0] - 2026-07-25 · 社区版重构（聚焦实质）

> 产品转向：砍掉繁杂的「图生 3D 多模式 / 模型动物园 / 批量 / Blender/ComfyUI 集成」，
> 主线收敛为「用户上传自己的模型 → 系统自动可打印性分析 → 社区画廊 → 成员评论」。
> 分析引擎（advisor）已是现成能力，本次把它扶正为主角，并套上社区层。

### 新增（社区）
- **社区数据层 `app/db.py`**：零依赖 SQLite，存储模型提交（含分析报告）与评论；
  画廊列表带评论计数，支持分页与评分榜。
- **社区 API**：`POST /api/upload`（上传即分析）、`GET /api/gallery`、
  `GET /api/models/{id}`（报告+评论）、`POST /api/models/{id}/comments`（评论）、
  `GET /api/presets`、`GET /api/scoreboard`。
- **可打印性评分 `advisor.score()`**：0–100 综合评分（水密 / 悬垂 / 支撑 / 接触面），
  画廊与详情页直观展示。
- **简洁前端 `web/`**：上传区 + 画廊网格 + 详情（报告可视化）+ 评论，单页三项文件
  （index.html / app.js / style.css），移除原 5 模式散文件。

### 移除（精简聚焦）
- 删除图生 3D 浮雕流水线 `app/pipeline.py`、AI 后端适配层 `app/backends.py`、
  配置/模型动物园 `app/config.py`（含 `MODEL_ZOO`）。
- 删除多模式接口 `generate` / `generate_async` / `batch` / `models` 及对应任务队列。
- 删除失效集成 `blender/`、`comfyui/`、`examples/`、`scripts/setup_ai_models.py`、
  `requirements-ai.txt`、过时 `docs/路线图.md`、`README.en.md`。
- 移除异步任务队列（`SNAPRINT_TASK_PERSIST` 一并失效，因上传分析为同步秒级）。

### 保留 / 沿用
- 分析引擎 `app/advisor.py`（去掉图片→浮雕分支，只收网格文件，加 `material` 预估与 `score`）。
- v0.5.0 的 CORS 收紧与可选 API Key / 限流（移至社区 API）。
- `requirements.lock.txt`（重新生成，仅含运行时依赖）。

## [0.5.0] - 2026-07-25 · 工程加固（本评估优化）

> 本次为「整合优化」版本：在 v0.5 功能完整的基础上，修复配置/健壮性短板，
> 不改变对外 API 与用户功能。

### 安全 / 配置
- **CORS 收紧（R4）**：`allow_origins` 由通配 `*` 改为可配置，默认锁定为
  `https://snapprint-3d.surge.sh` + 本地地址；鉴权基于 `X-API-Key` 请求头
  （非 Cookie），故关闭 `allow_credentials`。可用 `SNAPRINT_CORS_ORIGINS`
  （逗号分隔）按部署覆盖。内网/小团队部署建议显式列出可信前端来源。

### 健壮性 / 可靠性
- **任务队列可选持久化（R5）**：设 `SNAPRINT_TASK_PERSIST=1` 后，任务注册表
  落盘到 `outputs/.task_registry.json`，重启后端任务仍在（生成文件本就在
  `outputs/` 下）。默认仍纯内存态，重启即清空。
- **清理占位代码（R7）**：移除 `postprocess.py` 中无意义的
  `rotation_matrix(0, ...)` 占位旋转。

### 测试 / 质量
- **测试隔离（R7）**：限流测试改用 `pytest` 的 `monkeypatch` 替换模块全局，
  不再污染全局状态，可并行运行。
- CI 现有 `pytest tests/ -v` 继续覆盖 API / pipeline / advisor / 安全 / v0.5。

### 工程化
- **依赖锁定（R6）**：新增 `requirements.lock.txt`（`pip freeze` 生成，52 个
  固定版本），用于严格可复现安装；日常开发仍用 `requirements.txt`（仅下界）。
- **AI 环境准备脚本升级**：`scripts/setup_ai_models.py` 从「仅克隆/装依赖」
  升级为**真正可预置权重**——新增 `--download <HF仓库ID>`、`--hunyuan3d-mini`、
  `--triposg`、`--sf3d`、`--trellis`、`--all`、`--mirror {hf,modelscope}`，
  用 `huggingface_hub` / `huggingface-cli` / `modelscope` 把权重落到与
  `config.MODEL_ZOO` 对应的 `models/<目录>`，实现「开箱即用 / 离线预置」。
  仍保留 `--triposr`（克隆仓库）、`--hunyuan3d`（装 hy3dgen）、`--check`。

### 文档
- README 增补 `SNAPRINT_CORS_ORIGINS` / `SNAPRINT_TASK_PERSIST` 说明与
  `setup_ai_models.py` 用法。
- **`docs/部署.md` 新增「权重下载（开箱即用 / 离线预置）」章节**：汇总各后端
  HuggingFace 仓库链接、`huggingface-cli download` 一键命令、权重目录映射，
  以及国内加速镜像（`hf-mirror.com` / `ModelScope`）。原二/三节补充显式下载行。

---

## [0.5.0] - 2026-07-24 · 生成模式对齐 modly（功能基线）
- 多引擎图生 3D（10 款引擎：Hunyuan3D-2 系列 / TripoSG / SF3D / Trellis2 + 垂类）
- 生成参数 remesh / enable_texture / texture_resolution（对齐 modly）
- 统一后端托管前端（后端直接托管 `web/`）

## [0.4.0] - 2026-07-24 · 社区
- 模型动物园（垂类权重注册表 + 本地权重探测）
- 批量生成 + API Key 鉴权 + 限流
- 多语言文档（README.en.md）+ Web UI 中英切换

## [0.3.0] - 2026-07-24 · 生态
- Blender 插件、ComfyUI 节点
- 自动支撑建议（advisor）

## [0.2.0] - 2026-07-24 · 易用性
- 异步任务队列 + 在线公共 Demo
- 切片就绪预设（9 机型 × 3 材料）

## [0.1.0] - 2026-07-23 · 起点
- 离线浮雕模式、AI 模式适配层、打印级后处理、OBJ/PLY/3MF 导出、中文 Web UI
