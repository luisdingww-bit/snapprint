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

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = "请求失败";
    try { detail = (await r.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
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
    ? `<a class="btn" href="/outputs/uploads/${esc(sub.id)}${esc(sub.ext)}" download>下载模型原文件</a>`
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
  const { submission, comments } = await api(`/api/models/${id}`);
  const body = $("#detailBody");
  const size = submission.report.size_mm || [];
  body.innerHTML = `
    <h2>${esc(submission.filename)}</h2>
    <div class="muted small">@${esc(submission.author || "匿名")} · ${fmtTime(submission.created_at)}</div>
    <div class="report">${buildReport(submission.report, submission)}</div>
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
  $("#cSend").addEventListener("click", () => sendComment(id));
  $("#detail").classList.remove("hidden");
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

// ---------- 初始化 ----------
(async function init() {
  setupDropzone();
  $("#submit").addEventListener("click", submitUpload);
  $("#detailClose").addEventListener("click", () => $("#detail").classList.add("hidden"));
  $("#detail").addEventListener("click", (e) => {
    if (e.target.id === "detail") $("#detail").classList.add("hidden");
  });
  try {
    await setupPresets();
    await loadGallery();
  } catch (e) {
    $("#galleryEmpty").textContent = "加载失败：" + e.message;
  }
})();
