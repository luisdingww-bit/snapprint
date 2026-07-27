"use strict";

// ---------- 工具 ----------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
const fmtTime = (ts) =>
  new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
const scoreClass = (s) => (s >= 80 ? "score-ok" : s >= 60 ? "score-mid" : "score-bad");
const scoreColor = (s) => (s >= 80 ? "var(--accent-2)" : s >= 60 ? "var(--warn)" : "var(--bad)");

let selectedStars = 0; // 当前选中的评分星级
let currentBoardSort = "community"; // 榜单排序维度

const API_BASE = (window.SNAPRINT_CONFIG && window.SNAPRINT_CONFIG.API_BASE) || "";

async function api(path, opts) {
  const r = await fetch(API_BASE + path, opts);
  if (!r.ok) {
    let detail = "请求失败";
    try { detail = (await r.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}

// 探测后端是否在线；离线时显示提示横幅
async function checkBackend() {
  const banner = $("#backendBanner");
  if (!banner) return;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const r = await fetch(API_BASE + "/api/health", { signal: ctrl.signal });
    clearTimeout(t);
    banner.style.display = r.ok ? "none" : "block";
  } catch {
    banner.style.display = "block";
  }
}

// ---------- 报告渲染 ----------
function buildReport(rec, sub) {
  const s = rec;
  const size = s.size_mm || [0, 0, 0];
  const maxDim = Math.max(...size, 1);
  const bars = [
    ["X", size[0]], ["Y", size[1]], ["Z", size[2]],
  ]
    .map(
      ([k, v]) => `<div class="bar-row"><span>${k}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(v / maxDim) * 100}%"></div></div>
        <span>${v.toFixed(1)}</span></div>`
    )
    .join("");

  const overhang = ((s.overhang_ratio || 0) * 100).toFixed(1);
  const chips = [];
  chips.push(
    s.watertight
      ? `<span class="chip good">✓ 水密</span>`
      : `<span class="chip bad">✕ 非水密</span>`
  );
  chips.push(
    s.supports
      ? `<span class="chip warn">需支撑</span>`
      : `<span class="chip good">免支撑</span>`
  );
  if (s.material) chips.push(`<span class="chip">材料 ${esc(s.material.name)}</span>`);
  if (s.printer) chips.push(
    s.printer.fit
      ? `<span class="chip good">适配 ${esc(s.printer.name)}</span>`
      : `<span class="chip bad">超出 ${esc(s.printer.name)} 热床</span>`
  );

  const kv = [];
  kv.push(["层高", `${s.layer_height} mm`]);
  kv.push(["填充", `${s.infill}%`]);
  kv.push(["轮廓层数", s.perimeters]);
  kv.push(["顶/底层", `${s.top_layers}/${s.bottom_layers}`]);
  if (s.grams != null) kv.push(["预估重量", `${s.grams} g`]);
  if (s.minutes != null) kv.push(["预估时长", `${s.minutes} min`]);
  if (s.brim_mm) kv.push(["Brim", `${s.brim_mm} mm`]);

  let warns = "";
  if (s.warnings && s.warnings.length) {
    warns = `<ul class="warn-list">${s.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
  }

  const dl = sub
    ? `<a class="btn" href="${API_BASE}/outputs/uploads/${esc(sub.id)}${esc(sub.ext)}" download>下载模型原文件</a>`
    : "";

  return `
    <div class="report-top">
      <div class="score-big ${scoreClass(s.score)}" style="color:${scoreColor(s.score)}">${s.score}</div>
      <div>
        <div style="font-weight:600">可打印性评分 / 100</div>
        <div class="chips" style="margin-top:6px">${chips.join("")}</div>
      </div>
    </div>
    <div class="bars">
      <div class="bar-row"><span>尺寸(mm)</span><div></div><span>${size.map((v)=>v.toFixed(1)).join(" × ")}</span></div>
      ${bars}
    </div>
    <div class="bar-row"><span>悬垂占比</span>
      <div class="bar-track"><div class="bar-fill over" style="width:${Math.min(100, overhang)}%"></div></div>
      <span>${overhang}%</span></div>
    <div class="kv">${kv.map(([k, v]) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
    ${s.support_reason ? `<div class="muted small" style="margin-top:6px">支撑：${esc(s.support_reason)}</div>` : ""}
    ${s.orientation_advice ? `<div class="muted small">摆放：${esc(s.orientation_advice)}</div>` : ""}
    ${warns}
    <div style="margin-top:14px">${dl}</div>
  `;
}

// ---------- 画廊 ----------
function buildTile(it) {
  const size = (it.report && it.report.size_mm) || null;
  const dim = size ? `${size.map((v) => v.toFixed(0)).join("×")} mm` : "";
  return `<div class="tile" data-id="${esc(it.id)}">
    <div class="score-badge ${scoreClass(it.score)}">${it.score}</div>
    <div class="ext">${esc((it.ext || "").replace(".", "").toUpperCase())}</div>
    <div class="fname">${esc(it.filename)}</div>
    <div class="by">@${esc(it.author || "匿名")}</div>
    <div class="dim">${dim}</div>
    <div class="cmt">💬 ${it.comments ?? 0}</div>
  </div>`;
}

async function loadGallery() {
  const { items, total } = await api("/api/gallery?limit=60");
  const grid = $("#grid");
  // 用详情接口拿评论数会很多请求，这里用 size_bytes? 改为本地计数；
  // 简单起见先用 list 返回的字段（无评论数时显示 0）
  grid.innerHTML = items.map(buildTile).join("");
  $$(".tile", grid).forEach((t) =>
    t.addEventListener("click", () => openDetail(t.dataset.id))
  );
  $("#galleryCount").textContent = `共 ${total} 个模型`;
  $("#galleryEmpty").style.display = items.length ? "none" : "block";
}

// ---------- 详情 + 评论 ----------
async function openDetail(id) {
  const { submission, comments, rating } = await api(`/api/models/${id}`);
  selectedStars = 0;
  const body = $("#detailBody");
  const fallback = { count: 0, avg: 0, dist: {}, printability: submission.score };
  body.innerHTML = `
    <h2>${esc(submission.filename)}</h2>
    <div class="muted small">@${esc(submission.author || "匿名")} · ${fmtTime(submission.created_at)}</div>
    <div class="report">${buildReport(submission.report, submission)}</div>
    ${buildRating(rating || fallback, submission)}
    <div class="comments">
      <h3 style="margin:0 0 8px">社区评论 (${comments.length})</h3>
      <div id="clist">${comments
        .map(
          (c) => `<div class="comment"><div class="ca">@${esc(c.author || "匿名")}</div>
          <div class="cb">${esc(c.body)}</div></div>`
        )
        .join("")}</div>
      <div class="comment-form">
        <input id="cAuthor" placeholder="昵称（可选）" maxlength="24" />
        <input id="cBody" placeholder="说点什么…" maxlength="500" />
        <button class="btn primary" id="cSend">发送</button>
      </div>
    </div>`;
  $$("#rateStars .star", body).forEach((sp) =>
    sp.addEventListener("click", () => {
      selectedStars = +sp.dataset.s;
      $$("#rateStars .star", body).forEach((x) =>
        x.classList.toggle("on", +x.dataset.s <= selectedStars)
      );
    })
  );
  $("#rateSend", body).addEventListener("click", () => sendRating(id));
  $("#cSend", body).addEventListener("click", () => sendComment(id));
  $("#detail").classList.remove("hidden");
}

// 社区评分面板（均值 + 星级分布 + 洞察 + 评分表单）
function buildRating(rating, sub) {
  const avg = rating.avg || 0;
  const cnt = rating.count || 0;
  const dist = rating.dist || {};
  const bars = [5, 4, 3, 2, 1]
    .map((s) => {
      const n = dist[String(s)] || 0;
      const pct = cnt ? (n / cnt) * 100 : 0;
      return `<div class="dist-row"><span>${s}★</span>
        <div class="dist-track"><div class="dist-fill" style="width:${pct}%"></div></div>
        <span>${n}</span></div>`;
    })
    .join("");
  const p = rating.printability != null ? rating.printability : (sub && sub.score) || 0;
  const verdict =
    p >= 80 ? "推荐直接打印" : p >= 60 ? "打印可行，注意支撑" : "打印难度较高，建议先优化模型";
  const insight = cnt
    ? `社区评分 ${avg.toFixed(1)}★（${cnt} 人评） · 可打印性 ${p} · ${verdict}`
    : `还没有评分 · 可打印性 ${p}（等你来评）`;
  const bayesTxt = rating.bayes != null ? rating.bayes : "—";
  return `
    <div class="rating-panel">
      <h3 style="margin:0 0 8px">社区评分 <span class="muted small">（1–5 星 + 文字评价，每作者限评一次）</span></h3>
      <div class="rating-summary">
        <div class="rating-avg ${scoreClass(p)}">${cnt ? avg.toFixed(1) : "—"}<span class="small">★</span></div>
        <div class="rating-meta">
          <div class="muted small">${cnt ? cnt + " 人评价" : "还没有评价"} · 贝叶斯调整分 ${bayesTxt}</div>
          <div class="dist">${bars}</div>
        </div>
      </div>
      <div class="muted small" style="margin:8px 0">${insight}</div>
      <div class="rating-form">
        <div class="stars" id="rateStars">
          ${[1, 2, 3, 4, 5].map((s) => `<span class="star" data-s="${s}">★</span>`).join("")}
        </div>
        <input id="rateAuthor" placeholder="昵称（必填，不可匿名）" maxlength="24" />
        <textarea id="rateReview" placeholder="说说你的打印体验或改进建议（至少 10 字）" maxlength="500"></textarea>
        <button class="btn primary" id="rateSend">提交评分</button>
        <span id="rateMsg" class="msg small"></span>
      </div>
    </div>`;
}

async function sendRating(id) {
  const author = $("#rateAuthor").value.trim();
  const review = $("#rateReview").value.trim();
  const msg = $("#rateMsg");
  msg.className = "msg small";
  msg.textContent = "";
  if (!selectedStars) {
    msg.className = "msg small err";
    msg.textContent = "请先点选 1–5 星";
    return;
  }
  if (!author) {
    msg.className = "msg small err";
    msg.textContent = "昵称必填（不可匿名）";
    return;
  }
  if (review.length < 10) {
    msg.className = "msg small err";
    msg.textContent = "评价至少 10 个字";
    return;
  }
  try {
    await api(`/api/models/${id}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ author, stars: String(selectedStars), review }),
    });
    await openDetail(id);
    await loadStats();
    await loadBoard(currentBoardSort);
  } catch (e) {
    msg.className = "msg small err";
    msg.textContent = "✕ " + e.message;
  }
}

async function sendComment(id) {
  const body = $("#cBody").value.trim();
  if (!body) return;
  const author = $("#cAuthor").value.trim();
  try {
    await api(`/api/models/${id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ author, body }),
    });
    await openDetail(id);
  } catch (e) {
    alert(e.message);
  }
}

// ---------- 上传 ----------
let pickedFile = null;
function setupDropzone() {
  const dz = $("#dropzone");
  const input = $("#file");
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    pickedFile = input.files[0];
    $("#fileName").textContent = pickedFile ? pickedFile.name : "未选择文件";
    $("#submit").disabled = !pickedFile;
  });
  ["dragover", "dragenter"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); })
  );
  dz.addEventListener("drop", (e) => {
    pickedFile = e.dataTransfer.files[0];
    if (pickedFile) {
      $("#fileName").textContent = pickedFile.name;
      $("#submit").disabled = false;
    }
  });
}

async function setupPresets() {
  const { printers, materials } = await api("/api/presets");
  const ps = $("#printer"), ms = $("#material");
  printers.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.name; ps.appendChild(o);
  });
  materials.forEach((m) => {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.name; ms.appendChild(o);
  });
}

async function submitUpload() {
  if (!pickedFile) return;
  const btn = $("#submit");
  btn.disabled = true;
  $("#uploadMsg").className = "msg";
  $("#uploadMsg").textContent = "分析中…";
  const fd = new FormData();
  fd.append("file", pickedFile);
  const author = $("#author").value.trim();
  const printer = $("#printer").value;
  const material = $("#material").value;
  if (author) fd.append("author", author);
  if (printer) fd.append("printer", printer);
  if (material) fd.append("material", material);
  try {
    const res = await api("/api/upload", { method: "POST", body: fd });
    $("#result").innerHTML = `<div class="report-head"><h3>分析完成 · 已发布到社区</h3></div>
      <div class="report">${buildReport(res.report, { id: res.id, ext: (pickedFile.name.match(/\.[^.]+$/)||[""])[0] })}</div>`;
    $("#uploadMsg").className = "msg ok";
    $("#uploadMsg").textContent = "✓ 已加入社区画廊，下方可看到你的模型。";
    pickedFile = null; $("#file").value = ""; $("#fileName").textContent = "未选择文件";
    await loadGallery();
  } catch (e) {
    $("#uploadMsg").className = "msg err";
    $("#uploadMsg").textContent = "✕ " + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------- 照片生成 3D ----------
let genPickedFile = null;
async function setupGenerate() {
  const dz = $("#genDropzone");
  const input = $("#genFile");
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    genPickedFile = input.files[0];
    $("#genFileName").textContent = genPickedFile ? genPickedFile.name : "未选择文件";
    $("#genSubmit").disabled = !genPickedFile;
  });
  ["dragover", "dragenter"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); })
  );
  dz.addEventListener("drop", (e) => {
    genPickedFile = e.dataTransfer.files[0];
    if (genPickedFile) {
      $("#genFileName").textContent = genPickedFile.name;
      $("#genSubmit").disabled = false;
    }
  });

  // 模式下拉：默认 relief（永远可用），其余来自模型动物园
  try {
    const { models } = await api("/api/models");
    const sel = $("#genMode");
    models.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id || m.backend;
      const tag = m.available ? "" : "（需 GPU+权重）";
      o.textContent = `${m.name}${tag}`;
      sel.appendChild(o);
    });
  } catch (e) {
    /* 后端离线时下拉仅保留默认浮雕项，无伤大雅 */
  }

  // 复用上传区的打印机/材料预设
  try {
    const { printers, materials } = await api("/api/presets");
    const ps = $("#genPrinter"), ms = $("#genMaterial");
    printers.forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id; o.textContent = p.name; ps.appendChild(o);
    });
    materials.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.name; ms.appendChild(o);
    });
  } catch (e) { /* ignore */ }

  $("#genSubmit").addEventListener("click", submitGenerate);
}

async function submitGenerate() {
  if (!genPickedFile) return;
  const btn = $("#genSubmit");
  btn.disabled = true;
  $("#genMsg").className = "msg";
  $("#genMsg").textContent = "生成中…（浮雕模式秒级，AI 模式可能较慢）";
  const fd = new FormData();
  fd.append("file", genPickedFile);
  fd.append("mode", $("#genMode").value);
  const author = $("#genAuthor").value.trim();
  const printer = $("#genPrinter").value;
  const material = $("#genMaterial").value;
  if (author) fd.append("author", author);
  if (printer) fd.append("printer", printer);
  if (material) fd.append("material", material);
  try {
    const res = await api("/api/generate", { method: "POST", body: fd });
    $("#genResult").innerHTML = `<div class="report-head"><h3>生成完成 · 已发布到社区（${esc(res.mode)}）</h3></div>
      <div class="report">${buildReport(res.report, { id: res.id, ext: ".stl" })}</div>`;
    $("#genMsg").className = "msg ok";
    $("#genMsg").textContent = "✓ 已加入社区画廊，下方可看到你的模型。";
    genPickedFile = null; $("#genFile").value = ""; $("#genFileName").textContent = "未选择文件";
    await loadGallery();
  } catch (e) {
    $("#genMsg").className = "msg err";
    $("#genMsg").textContent = "✕ " + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------- 内置模型实例库 ----------
let shapePicked = null; // { id, name, emoji, defaults }
async function setupShapes() {
  let shapes = [];
  try {
    ({ shapes } = await api("/api/shapes"));
  } catch (e) {
    return; // 后端离线：区块保持空，横幅已提示
  }
  const grid = $("#shapeGrid");
  grid.innerHTML = shapes
    .map(
      (s) => `<div class="shape-tile" data-id="${esc(s.id)}" title="${esc(s.name)}">
        <div class="shape-emoji">${s.emoji}</div>
        <div class="shape-name">${esc(s.name)}</div>
        <div class="shape-tag muted small">${esc(s.tag)}</div>
      </div>`
    )
    .join("");
  $$(".shape-tile", grid).forEach((t) =>
    t.addEventListener("click", () => {
      $$(".shape-tile", grid).forEach((x) => x.classList.remove("sel"));
      t.classList.add("sel");
      shapePicked = shapes.find((s) => s.id === t.dataset.id);
      const d = shapePicked.defaults;
      $("#shH").value = d.H;
      $("#shD").value = d.D;
      $("#shTwist").value = d.twist;
      $("#shLobes").value = d.lobes;
      $("#shapeParams").style.display = "";
      $("#shSubmit").disabled = false;
      $("#shSubmit").textContent = `生成「${shapePicked.name}」并发布到社区`;
    })
  );
  $("#shSubmit").addEventListener("click", submitShape);
}

async function submitShape() {
  if (!shapePicked) return;
  const btn = $("#shSubmit");
  btn.disabled = true;
  $("#shMsg").className = "msg";
  $("#shMsg").textContent = "生成中…（纯参数几何，秒级）";
  const fd = new FormData();
  const H = parseFloat($("#shH").value), D = parseFloat($("#shD").value);
  const tw = parseFloat($("#shTwist").value), lb = parseInt($("#shLobes").value, 10);
  if (H > 0) fd.append("H", H);
  if (D > 0) fd.append("D", D);
  if (!Number.isNaN(tw)) fd.append("twist", tw);
  if (!Number.isNaN(lb) && lb >= 0) fd.append("lobes", lb);
  const author = $("#shAuthor").value.trim();
  if (author) fd.append("author", author);
  try {
    const res = await api(`/api/shapes/${shapePicked.id}/generate`, { method: "POST", body: fd });
    $("#shResult").innerHTML = `<div class="report-head"><h3>${res.shape.emoji} ${esc(res.shape.name)} · 生成完成，已发布到社区</h3></div>
      <div class="report">${buildReport(res.report, { id: res.id, ext: ".stl" })}</div>`;
    $("#shMsg").className = "msg ok";
    $("#shMsg").textContent = "✓ 已加入社区画廊，下方可看到你的模型。";
    await loadGallery();
  } catch (e) {
    $("#shMsg").className = "msg err";
    $("#shMsg").textContent = "✕ " + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------- 社区统计 / 榜单 ----------
async function loadStats() {
  try {
    const g = await api("/api/stats");
    const top = g.top_authors && g.top_authors[0] ? g.top_authors[0].author : "—";
    const avgTxt = g.avg_rating ? g.avg_rating.toFixed(1) + "★" : "—";
    $("#statsStrip").innerHTML = `
      <div class="stat"><b>${g.total_submissions}</b><span>作品</span></div>
      <div class="stat"><b>${g.total_ratings}</b><span>评价</span></div>
      <div class="stat"><b>${avgTxt}</b><span>平均社区评分</span></div>
      <div class="stat"><b>${esc(top)}</b><span>最活跃评价者</span></div>`;
  } catch (e) {
    /* 后端离线时静默 */
  }
}

async function loadBoard(sort) {
  currentBoardSort = sort || currentBoardSort;
  try {
    const { items } = await api(`/api/scoreboard?sort=${currentBoardSort}&limit=20`);
    $("#boardList").innerHTML = items
      .map(
        (it, i) => `
        <li class="board-item" data-id="${esc(it.id)}">
          <span class="rank">${i + 1}</span>
          <div class="bi-main">
            <div class="bi-name">${esc(it.filename)}</div>
            <div class="muted small">@${esc(it.author || "匿名")}</div>
          </div>
          <div class="bi-score">
            ${
              currentBoardSort === "printability"
                ? `<span class="score-badge ${scoreClass(it.score)}">${it.score}</span>`
                : `<b>${it.community_rating != null ? it.community_rating.toFixed(1) : "—"}★</b><span class="muted small">（${it.rating_count || 0} 评）</span>`
            }
          </div>
        </li>`
      )
      .join("");
    $$(".board-item", $("#boardList")).forEach((t) =>
      t.addEventListener("click", () => openDetail(t.dataset.id))
    );
  } catch (e) {
    /* 离线静默 */
  }
}

// ---------- 初始化 ----------
(async function init() {
  setupDropzone();
  setupGenerate();
  setupShapes();
  $("#submit").addEventListener("click", submitUpload);
  $("#detailClose").addEventListener("click", () => $("#detail").classList.add("hidden"));
  $("#detail").addEventListener("click", (e) => {
    if (e.target.id === "detail") $("#detail").classList.add("hidden");
  });
  await checkBackend();
  try {
    await setupPresets();
  } catch (e) {
    /* 后端离线时预设加载失败无关紧要，横幅已提示 */
  }
  try {
    await loadGallery();
  } catch (e) {
    $("#galleryEmpty").textContent = "社区后端未连接，画廊暂不可用。";
  }
  try { await loadStats(); } catch (e) {}
  try { await loadBoard("community"); } catch (e) {}
  $$("#boardSort button").forEach((b) =>
    b.addEventListener("click", () => {
      $$("#boardSort button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      loadBoard(b.dataset.sort);
    })
  );
})();
