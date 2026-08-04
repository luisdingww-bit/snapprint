/* SnapPrint 着陆页「两段合一」滚动合并脚本
 *
 * 目标：把「电影感首屏 + 内嵌工作台」合成一个连续可滚动的页面。
 * 做法：
 *   1. 把 iframe 从线上跨域地址改指本地同源副本 ./tool.html，
 *      从而可以读取内容高度、桥接锚点导航；
 *   2. 根据工具页真实内容高度撑开 iframe（覆盖原来的 h-screen 一屏），
 *      外层页面只剩一根滚动条，从首屏一路滑到底；
 *   3. 工具页内部的锚点导航（#make / #gallery-sec / #gs-sec 等）
 *      桥接到外层滚动，不产生 iframe 内部滚动；
 *   4. 工具页内容高度变化（生成结果、筛选、窗口缩放）自动重新测高。
 */
(function () {
  "use strict";

  var HEIGHT_MSG = "snap-print-tool-height";
  var TOOL_ANCHOR = {
    "创作": "#make",
    "模型库": "#gallery-sec",
    "高斯泼溅": "#gs-sec",
  };

  function findFrame() {
    return document.querySelector('iframe[title="SnapPrint 工作台"]');
  }

  function init(f) {
    // 1) 指向本地同源副本（保留 #generate 等锚点）
    var src = f.getAttribute("src") || "";
    if (src.indexOf("snapprint-3d.surge.sh") !== -1) {
      var hash = "";
      var i = src.indexOf("#");
      if (i !== -1) hash = src.slice(i);
      f.setAttribute("src", "./tool.html" + (hash || "#generate"));
    }

    function setHeight(h) {
      if (!h) return;
      f.style.height = h + "px"; // 内联样式覆盖 Tailwind 的 h-screen
      f.style.maxHeight = "none";
      f.setAttribute("scrolling", "no");
    }

    function measure() {
      try {
        var doc = f.contentDocument;
        if (doc && doc.documentElement) {
          setHeight(doc.documentElement.scrollHeight);
        }
      } catch (e) {
        /* 跨域时依赖 tool.html 内的 postMessage 上报 */
      }
    }

    // 2) 高度自适应：加载后测高 + 短暂轮询稳定 + 窗口缩放重测
    f.addEventListener("load", function () {
      measure();
      try { bridgeToolAnchors(f.contentDocument); } catch (e) {}
      var tries = 0;
      var iv = setInterval(function () {
        if (++tries > 40) { clearInterval(iv); return; }
        measure();
      }, 200);
    });
    window.addEventListener("resize", measure);
    window.addEventListener("message", function (e) {
      var d = e.data;
      if (d && d.type === HEIGHT_MSG && typeof d.height === "number") {
        setHeight(d.height);
      }
    });

    // 3) 工具页内部锚点 -> 外层滚动桥
    function bridgeToolAnchors(doc) {
      if (!doc || doc.__snapBridge) return;
      doc.__snapBridge = true;
      doc.addEventListener("click", function (e) {
        var el = e.target;
        var a = el && el.closest ? el.closest('a[href^="#"]') : null;
        if (!a) return;
        var id = a.getAttribute("href");
        if (!id || id === "#") return;
        var target = doc.querySelector(id);
        if (!target) return;
        e.preventDefault();
        scrollParentTo(target);
      }, true);
    }

    // 4) 着陆页导航（创作 / 模型库 / 高斯泼溅）改在合并页内滚动；
    //    原站这些链接 target=_blank 会新开标签，合并后直接在页内定位
    document.querySelectorAll('a[href*="snapprint-3d.surge.sh"]').forEach(function (a) {
      a.addEventListener("click", function (e) {
        var label = (a.textContent || "").trim();
        var anchor = TOOL_ANCHOR[label];
        if (!anchor) return; // 社区/进入工作台等外链保持原样
        e.preventDefault();
        try {
          var doc = f.contentDocument;
          var target = doc && doc.querySelector(anchor);
          if (target) scrollParentTo(target);
        } catch (err) { /* 同源后才能桥接 */ }
      });
    });

    function scrollParentTo(target) {
      var navH = 60; // 工具页 sticky 导航高度
      var top =
        target.getBoundingClientRect().top +
        f.getBoundingClientRect().top +
        window.scrollY -
        navH;
      window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
  }

  // React 挂载完成后 iframe 才存在：轮询等待
  var tries = 0;
  (function wait() {
    var f = findFrame();
    if (f) { init(f); return; }
    if (++tries > 300) return;
    setTimeout(wait, 100);
  })();
})();
