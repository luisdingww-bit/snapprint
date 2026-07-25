// SnapPrint 前端运行配置
// ---------------------------------------------------------------------------
// API_BASE 指定后端地址：
//   - 留空 ""      → 同源（前端与后端同一 origin）。
//                    适用于：本地 `python -m app.main`、或 Docker 自托管
//                    （后端同时托管本前端）。
//   - 填具体地址   → 前端部署在静态托管（Surge / CloudStudio），后端跑在别处。
//                    例如："https://snapprint-api.your-host.com"
//
// 当前配置：前端托管在 CloudStudio 静态页，后端跑在 Railway。
// 已在本仓库部署（见 app/main.py 的 CORS 白名单放行此 CloudStudio 域名）。
window.SNAPRINT_CONFIG = {
  API_BASE: "https://snapprint-production.up.railway.app",
};
