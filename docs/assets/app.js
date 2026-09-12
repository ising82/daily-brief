/* 財經晨報 前端：讀取 window.BRIEF（data/latest.js 或封存檔）並渲染兩個頁面 */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const store = {
    get(k, d) { try { const v = localStorage.getItem("brief:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("brief:" + k, JSON.stringify(v)); } catch (e) { /* 無痕模式等 */ } },
  };

  const WD = "日一二三四五六";
  // 網頁用文字標籤（Windows 不顯示國旗 emoji）；推播訊息才用國旗
  const COUNTRY = { China: "中國", Japan: "日本", "Euro Zone": "歐元區", "United Kingdom": "英國", "South Korea": "韓國" };
  const REGION = { TW: "台灣", US: "美國", INTL: "國際" };
  const NEWS_TAGS = ["台股", "美股", "總經", "科技", "外匯原物料"];

  // ---------- 格式化（所有時間都已是台北時間字串，直接切字串，不受瀏覽器時區影響）
  const ymd = (iso) => iso.slice(0, 10).split("-").map(Number);
  const dow = (iso) => { const [y, m, d] = ymd(iso); return WD[new Date(y, m - 1, d).getDay()]; };
  const md = (iso) => { const [, m, d] = ymd(iso); return `${m}/${d}`; };
  const mdw = (iso) => `${md(iso)}（${dow(iso)}）`;
  const hm = (ts) => ts.slice(11, 16);
  const arrow = (v) => (v > 0 ? "▲" : v < 0 ? "▼" : "－");
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
  const num = (v, dp = 2) => Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const capUSD = (v) => (!v ? "" : v >= 1e12 ? `$${(v / 1e12).toFixed(2)}T` : `$${Math.round(v / 1e9)}B`);
  const capTWD = (v) => (!v ? "" : v >= 1e12 ? `${(v / 1e12).toFixed(1)} 兆` : `${Math.round(v / 1e8).toLocaleString()} 億`);
  const badgeOf = (e) => (e.region === "INTL" ? COUNTRY[e.country] || "國際" : REGION[e.region] || e.region);
  const badge = (e) => `<span class="badge b-${esc(e.region)}">${esc(badgeOf(e))}</span>`;
  const NO_TIME = { holiday: "全天", deadline: "全天", manual: "待定" };
  function ago(ts, ref) {
    const m = Math.round((Date.parse(ref) - Date.parse(ts)) / 60000);
    if (!isFinite(m) || m < 1) return "剛剛";
    return m < 60 ? `${m} 分鐘前` : `${Math.floor(m / 60)} 小時前`;
  }

  // ---------- 載入：?d=YYYY-MM-DD 讀封存，否則用 latest.js
  const want = new URLSearchParams(location.search).get("d");
  function boot() {
    if (want && /^\d{4}-\d{2}-\d{2}$/.test(want) && !(window.BRIEF && window.BRIEF.date === want)) {
      const s = document.createElement("script");
      s.src = `data/archive/${want}.js`;
      s.onload = () => render(window.BRIEF);
      s.onerror = () => render(window.BRIEF, `找不到 ${want} 的封存，顯示最新一期。`);
      document.head.appendChild(s);
    } else {
      render(window.BRIEF);
    }
  }

  function render(data, warn) {
    if (!data) {
      document.querySelector("main").innerHTML =
        '<div class="notice">尚無資料。請到 GitHub 的 Actions 分頁手動執行一次「每日財經晨報」。</div>';
      return;
    }
    if (want) document.querySelectorAll("[data-nav]").forEach((a) => { a.href = `${a.dataset.nav}?d=${data.date}`; });
    renderStamp(data);
    if (document.body.dataset.page === "news") renderNewsPage(data);
    else renderCalendarPage(data);
    renderFooter(data, warn);
  }

  function renderStamp(data) {
    const idx = Array.isArray(window.BRIEF_INDEX) ? window.BRIEF_INDEX : [];
    let html = `<span>${mdw(data.date)} ${hm(data.generated_at)} 更新</span>`;
    if (idx.length > 1) {
      html += `<select id="archive" aria-label="選擇日期">${idx.map((d) =>
        `<option value="${d}"${d === data.date ? " selected" : ""}>${d === idx[0] ? "最新 " : ""}${mdw(d)}</option>`).join("")}</select>`;
    }
    $("#stamp").innerHTML = html;
    const sel = $("#archive");
    if (sel) sel.onchange = () => { location.search = sel.value === idx[0] ? "" : `?d=${sel.value}`; };
  }

  function renderFooter(data, warn) {
    const errs = data.errors || [];
    $("#footer").innerHTML =
      (warn ? `<p>⚠️ ${esc(warn)}</p>` : "") +
      `資料來源：Nasdaq、行政院主計總處、公開資訊觀測站、證交所、櫃買中心、Yahoo Finance、鉅亨網、中央社、經濟日報、CNBC、WSJ、MarketWatch。` +
      `日曆時間皆為台灣時間。僅供參考，非投資建議。` +
      (errs.length ? `<details><summary>本期有 ${errs.length} 個資料來源暫時失敗</summary><ul>${errs.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></details>` : "");
  }

  // ---------- 共用：篩選按鈕
  function chips(container, options, current, onPick) {
    container.insertAdjacentHTML("beforeend", options.map(([v, label]) =>
      `<button class="chip" data-v="${esc(v)}" aria-pressed="${v === current}">${esc(label)}</button>`).join(""));
    container.addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      container.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
      onPick(b.dataset.v);
    });
  }

  // ================================================================ 頁 1：財經日曆
  function renderCalendarPage(data) {
    renderMarkets(data.markets || []);
    renderRecap(data);
    const days = data.days || [];
    if (days.length) $("#cal-range").textContent = `${mdw(days[0].date)} – ${mdw(days[days.length - 1].date)}・台灣時間`;

    let filter = store.get("calFilter", "all");
    let impOnly = store.get("calImportant", true);
    const box = $("#cal-filters");
    chips(box, [["all", "全部"], ["TW", "台灣"], ["US", "美國"], ["INTL", "國際"], ["earnings", "財報／法說"]], filter,
      (v) => { filter = v; store.set("calFilter", v); draw(); });
    box.insertAdjacentHTML("beforeend", `<label class="toggle"><input type="checkbox" id="imp"${impOnly ? " checked" : ""}> 只看重要</label>`);
    $("#imp").onchange = (ev) => { impOnly = ev.target.checked; store.set("calImportant", impOnly); draw(); };

    function pass(e) {
      if (impOnly && e.importance < 2) return false;
      if (filter === "all") return true;
      if (filter === "earnings") return e.kind === "earnings";
      return e.region === filter;
    }
    function draw() {
      $("#calendar").innerHTML = days.map((d, i) => {
        const evs = (data.events || []).filter((e) => e.date === d.date && pass(e));
        const tag = i === 0 ? '<span class="tag-today">今天</span>' : i === 1 ? '<span class="tag-soft">明天</span>' : "";
        return `<div class="day${i === 0 ? " is-today" : ""}"><div class="day-head"><b>${mdw(d.date)}</b>${tag}` +
          `<span class="day-count">${evs.length} 項</span></div>` +
          (evs.length ? evs.map(evRow).join("") : '<div class="empty">沒有符合條件的事件</div>') + "</div>";
      }).join("");
    }
    draw();
  }

  function renderMarkets(list) {
    $("#markets").innerHTML = list.map((m) => {
      const pct = m.unit === "%";
      const price = pct ? `${m.price.toFixed(2)}%` : num(m.price);
      let chg = "";
      if (m.change != null) {
        chg = pct ? `${arrow(m.change)} ${Math.abs(m.change * 100).toFixed(1)}bp`
                  : `${arrow(m.change)} ${num(Math.abs(m.change))}（${Math.abs(m.pct).toFixed(2)}%）`;
      }
      return `<div class="mk"><div class="mk-name"><span>${esc(m.name)}</span><span class="mk-date">${md(m.date)}</span></div>` +
        `<div class="mk-price num">${price}</div><div class="mk-chg num ${cls(m.change)}">${chg}</div></div>`;
    }).join("");
  }

  function renderRecap(data) {
    const rel = data.released || [];
    const res = (data.earnings_results || []).filter((r) => r.importance >= 2);
    if (!rel.length && !res.length) return;
    const relHtml = rel.length ? rel.map((e) =>
      `<li><span class="when num">${md(e.ts)} ${hm(e.ts)}</span><span class="what">${badge(e)} ${esc(e.title)}</span>` +
      `<span class="val num">公布 <b>${esc(e.actual)}</b>${e.forecast ? `｜預期 ${esc(e.forecast)}` : ""}</span></li>`).join("")
      : '<li class="empty">無</li>';
    const resHtml = res.length ? res.map((r) => {
      const s = parseFloat(r.surprise);
      return `<li><span class="when">${esc(r.session)}</span><span class="what"><span class="ev-title"><span class="sym">${esc(r.symbol)}</span></span>${esc(r.name)}</span>` +
        `<span class="val num">EPS <b>${esc(r.eps)}</b>${r.forecast ? `｜預期 ${esc(r.forecast)}` : ""}` +
        (isFinite(s) ? `｜<span class="${cls(s)}">${s > 0 ? "+" : ""}${s.toFixed(1)}%</span>` : "") + "</span></li>";
    }).join("") : '<li class="empty">無</li>';
    $("#recap").innerHTML = `<section class="panel"><div class="panel-head"><h2>昨夜回顧<span class="sub">已公布的數據與財報</span></h2></div>` +
      `<div class="panel-body grid2"><div><p class="sec-title">經濟數據</p><ul class="rows">${relHtml}</ul></div>` +
      `<div><p class="sec-title">美股財報（EPS 實際 vs 預期）</p><ul class="rows">${resHtml}</ul></div></div></section>`;
  }

  function evRow(e) {
    let time = e.time;
    if (!time) time = e.kind === "earnings" ? (e.session || "—") : NO_TIME[e.kind] || "—";
    let title = esc(e.title);
    if (e.kind === "earnings" && e.symbol) title = `<span class="sym">${esc(e.symbol)}</span>${title}`;

    const meta = [];
    if (e.kind === "earnings" && e.region === "US") {
      if (e.eps) meta.push(`公布 EPS <b>${esc(e.eps)}</b>`);
      if (e.forecast) meta.push(`預估 EPS ${esc(e.forecast)}`);
      if (e.mcap) meta.push(`市值 ${capUSD(e.mcap)}`);
      if (e.us_date) meta.push(`美東 ${md(e.us_date)} ${esc(e.session || "")}`);
    } else if (e.kind === "earnings") {
      if (e.market) meta.push(esc(e.market));
      if (e.mcap) meta.push(`市值 ${capTWD(e.mcap)}`);
      if (e.range) meta.push(esc(e.range));
      if (e.detail) meta.push(esc(e.detail));
    } else {
      if (e.actual) meta.push(`公布 <b>${esc(e.actual)}</b>`);
      if (e.forecast) meta.push(`預期 ${esc(e.forecast)}`);
      if (e.previous) meta.push(`前值 ${esc(e.previous)}`);
      if (e.detail) meta.push(esc(e.detail));
      if (e.title_en && e.title_en !== e.title) meta.push(`<span lang="en">${esc(e.title_en)}</span>`);
    }
    const imp = Math.max(1, Math.min(3, e.importance || 1));
    const rowCls = ["ev", e.kind === "holiday" ? "holiday" : "", imp === 1 ? "minor" : ""].join(" ").trim();
    return `<div class="${rowCls}"><div class="ev-time num">${esc(time)}</div>` +
      `<div class="badge-col">${badge(e)}</div>` +
      `<div><div class="ev-title" data-region="${esc(badgeOf(e))}">${title}</div>` +
      (meta.length ? `<div class="ev-meta">${meta.join(" · ")}</div>` : "") + "</div>" +
      `<div class="imp" title="重要度 ${imp}/3">${"★".repeat(imp)}<span class="off">${"★".repeat(3 - imp)}</span></div></div>`;
  }

  // ================================================================ 頁 2：24 小時快訊
  function renderNewsPage(data) {
    const news = data.news || [];
    const ref = data.generated_at;
    const byId = Object.fromEntries(news.map((n) => [n.id, n]));
    const top = (data.top_news || []).map((id) => byId[id]).filter(Boolean);
    const meta = (n) => `<div class="n-meta"><span class="n-src">${esc(n.source)}</span><span class="num">${hm(n.ts)}・${ago(n.ts, ref)}</span>` +
      (n.also && n.also.length ? `<span>另見 ${esc(n.also.join("、"))}</span>` : "") +
      (n.tags || []).map((t) => `<span class="n-tag">${esc(t)}</span>`).join("") + "</div>";
    const link = (n) => `<a class="n-title" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>`;

    $("#top-news").innerHTML = top.length
      ? top.map((n) => `<li><div>${link(n)}${meta(n)}${n.summary ? `<div class="n-sum">${esc(n.summary)}</div>` : ""}</div></li>`).join("")
      : '<li class="empty">無</li>';

    let tag = store.get("newsTag", "all");
    let zhOnly = store.get("newsZh", false);
    let q = "";
    const box = $("#news-filters");
    chips(box, [["all", "全部"]].concat(NEWS_TAGS.map((t) => [t, t])), tag, (v) => { tag = v; store.set("newsTag", v); draw(); });
    box.insertAdjacentHTML("beforeend",
      `<label class="toggle"><input type="checkbox" id="zh"${zhOnly ? " checked" : ""}> 只看中文</label>` +
      `<input class="search" id="q" type="search" placeholder="搜尋標題，例如 台積電、Fed">`);
    $("#zh").onchange = (ev) => { zhOnly = ev.target.checked; store.set("newsZh", zhOnly); draw(); };
    $("#q").oninput = (ev) => { q = ev.target.value.trim().toLowerCase(); draw(); };

    function draw() {
      const list = news.filter((n) => (tag === "all" || (n.tags || []).includes(tag)) && (!zhOnly || n.lang === "zh") &&
        (!q || (n.title + " " + (n.summary || "")).toLowerCase().includes(q)));
      $("#news-count").textContent = `共 ${list.length} 則`;
      let html = "", hour = "";
      for (const n of list) {
        const h = n.ts.slice(0, 13);
        if (h !== hour) { hour = h; html += `<div class="hour">${mdw(n.ts)} ${n.ts.slice(11, 13)}:00</div>`; }
        html += `<li><div class="n-time num">${hm(n.ts)}</div><div>${link(n)}${meta(n)}` +
          (n.summary ? `<div class="n-sum">${esc(n.summary)}</div>` : "") + "</div></li>";
      }
      $("#news-list").innerHTML = list.length ? `<ul class="news-list">${html}</ul>` : '<div class="empty">沒有符合條件的新聞</div>';
    }
    draw();
  }

  boot();
})();
