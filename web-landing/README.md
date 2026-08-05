# web-landing · 品牌着陆页 + 图生3D 创作工具

对应线上两个站点：

- `https://snapprint.surge.sh/` — 品牌着陆页（电影感首屏 + 内嵌工作台，两段合一滚动版）
- `https://snapprint-3d.surge.sh/` — 图生3D 创作工具（本目录里的 `tool.html` + 同名 JS）

## 目录

```
web-landing/
├── index.html          # 着陆页（含 merge-fix.js 引用）
├── merge-fix.js        # 滚动合并：iframe 高度自适应 + 锚点桥接
├── assets/             # 着陆页打包资源（Vite 产物，未改动）
├── tool.html           # 创作工具页（内联样式 + 高度上报脚本）
├── gallery.js / shapes3d.js / modelio.js / splat.js / presets.js / app.js
│                       # 创作工具源码（未压缩）
└── vendor/three.min.js # three.js（创作工具依赖，MIT）
```

## 部署

两个站点各自独立部署（同一份 tool.html + JS 是工具站的源码）：

```bash
# 着陆页（含内嵌工作台，必须整目录部署）
surge web-landing snapprint.surge.sh

# 创作工具（单独部署时只推工具页文件）
surge web-landing/tool.html web-landing/app.js ... snapprint-3d.surge.sh
```

> 本地预览：`python -m http.server 8848` 在本目录运行，访问 `http://localhost:8848`。

## 合并滚动原理（merge-fix.js）

1. 把 iframe 从线上跨域地址改指同源副本 `./tool.html`；
2. 按工具页真实内容高度撑开 iframe（覆盖原来的 `h-screen`），外层只剩一根滚动条；
3. 工具页内部锚点与着陆页导航（创作 / 模型库 / 高斯泼溅）桥接到外层滚动；
4. 工具页内容高度变化（生成结果 / 筛选 / 窗口缩放）自动重新测高。

## 说明

- 着陆页原始 React 工程未保留（线上只有 Vite 打包产物，无 sourcemap），
  这里收录的是**可部署版本**；如需改着陆页结构，直接改 `index.html` +
  `merge-fix.js`，或用打包产物反推。
- 创作工具的 `gallery.js` 等为原始未压缩源码，可直接修改。
- 视频与字体从 CDN 加载，离线预览时首屏视频不可用。
