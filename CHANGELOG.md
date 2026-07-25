# 更新日志 Changelog

所有 notable 变更都会记录在此文件。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
- **AI 环境准备脚本**：新增 `scripts/setup_ai_models.py`，一键克隆 TripoSR、
  安装 hy3dgen，并 `--check` 查看各后端可用性，降低「AI 模式」上手门槛。

### 文档
- README 增补 `SNAPRINT_CORS_ORIGINS` / `SNAPRINT_TASK_PERSIST` 说明与
  `setup_ai_models.py` 用法。

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
