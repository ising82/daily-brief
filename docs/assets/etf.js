/* 台灣 ETF 績效比較：讀取 window.ETF_DATA（data/etf.js），所有期間／含息／風險指標在瀏覽器端計算 */
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const DAY = 86400000;
  const QUICK = [["1w", "1週"], ["1m", "1月"], ["3m", "3月"], ["6m", "6月"], ["ytd", "今年"], ["1y", "1年"],
                 ["3y", "3年"], ["5y", "5年"], ["10y", "10年"], ["max", "上市以來"]];
  const UNITS = { td: "個交易日", d: "天", w: "週", m: "個月", y: "年" };
  const MODES = { price: "不含息（價格報酬）", tr: "含息（配息再投入）", trx: "含息（配息不再投入）" };
  const CATS = ["市值型", "高股息", "主題/產業", "海外股票", "債券", "槓桿/反向", "商品/期貨", "多重資產/其他"];
  const COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
  const MAX_SEL = 8;

  // ---------- 日期工具（全部用「自 1970 起的天數」整數，避免時區問題）
  const toDay = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Math.round(Date.UTC(y, m - 1, d) / DAY); };
  const fromDay = (n) => new Date(n * DAY).toISOString().slice(0, 10);
  const ymdOf = (n) => { const t = new Date(n * DAY); return [t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()]; };
  function shiftMonths(n, months) {            // 往前 months 個月，日數超過月底則取月底
    const [y, m, d] = ymdOf(n);
    const first = new Date(Date.UTC(y, m - months, 1));
    const dim = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
    return Math.round(Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), Math.min(d, dim)) / DAY);
  }
  const upperBound = (arr, v) => { let lo = 0, hi = arr.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] <= v) lo = mid + 1; else hi = mid; } return lo; };
  const lastIdxLE = (arr, v) => upperBound(arr, v) - 1;

  // ---------- 格式
  const pct = (v, dp = 2) => (v == null || !isFinite(v) ? '<span class="na">—</span>'
    : `<span class="${v > 0 ? "up" : v < 0 ? "down" : "flat"}">${v > 0 ? "+" : ""}${(v * 100).toFixed(dp)}%</span>`);
  const pctPlain = (v, dp = 2) => (v == null || !isFinite(v) ? "" : (v * 100).toFixed(dp));
  const num = (v, dp = 2) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }));

  // ---------- 資料準備
  const DATA = window.ETF_DATA;
  if (!DATA || !DATA.etfs || !DATA.etfs.length) {
    $("#main").innerHTML = '<div class="notice">尚無 ETF 資料。請到 GitHub 的 Actions 分頁手動執行一次「台灣 ETF 績效資料」。</div>';
    return;
  }
  function prep(e) {
    const dates = new Array(e.dd.length);
    let d = toDay(e.d0);
    for (let i = 0; i < e.dd.length; i++) { d += e.dd[i]; dates[i] = d; }
    const c = e.c, n = c.length;
    const divAt = new Float64Array(n);
    (e.div || []).forEach(([i, a]) => { if (i > 0 && i < n) divAt[i] += a; });
    const tr = new Float64Array(n), cd = new Float64Array(n);   // 含息指數、累計配息
    tr[0] = c[0];
    for (let i = 1; i < n; i++) { tr[i] = tr[i - 1] * (c[i] + divAt[i]) / c[i - 1]; cd[i] = cd[i - 1] + divAt[i]; }
    const divs = (e.div || []).filter(([i]) => i < n).map(([i, a]) => ({ day: dates[i], amount: a, close: c[i] }));
    return Object.assign({}, e, { dates, c, tr, cd, divs, n });
  }
  const ETFS = DATA.etfs.map(prep);
  const BENCH = (DATA.bench || []).map(prep);
  const byCode = {};
  ETFS.concat(BENCH).forEach((e) => { byCode[e.code] = e; });
  const ASOF = toDay(DATA.asof);

  // ---------- 期間解析：回傳 {s, e} 索引，或 null（資料不足）
  function resolve(etf, period) {
    const dates = etf.dates;
    let endDay = ASOF;
    if (period.kind === "range") endDay = Math.min(ASOF, toDay(period.to));
    const en = lastIdxLE(dates, endDay);
    if (en < 1) return null;
    let s;
    if (period.kind === "quick" && period.key === "max") s = 0;
    else if (period.kind === "custom" && period.unit === "td") s = en - period.n;
    else {
      let startDay;
      const end = dates[en];
      if (period.kind === "range") startDay = toDay(period.from);
      else if (period.kind === "quick") {
        const k = period.key;
        if (k === "ytd") startDay = toDay(`${ymdOf(end)[0] - 1}-12-31`);
        else if (k.endsWith("w")) startDay = end - 7 * parseInt(k, 10);
        else if (k.endsWith("m")) startDay = shiftMonths(end, parseInt(k, 10));
        else startDay = shiftMonths(end, 12 * parseInt(k, 10));
      } else {
        const n = period.n, u = period.unit;
        startDay = u === "d" ? end - n : u === "w" ? end - 7 * n : u === "m" ? shiftMonths(end, n) : shiftMonths(end, 12 * n);
      }
      if (startDay >= end) return null;
      s = lastIdxLE(dates, startDay);
      if (s < 0) return null;
      if (period.kind !== "range" && dates[s] < startDay - 10) return null;  // 起點前有長期缺資料（例如暫停交易）
    }
    if (s < 0 || s >= en) return null;
    return { s, e: en };
  }

  function metrics(etf, r, mode) {
    const { s, e } = r;
    const c = etf.c, tr = etf.tr, cd = etf.cd;
    const ret = mode === "price" ? c[e] / c[s] - 1 : mode === "tr" ? tr[e] / tr[s] - 1 : (c[e] + cd[e] - cd[s]) / c[s] - 1;
    const days = etf.dates[e] - etf.dates[s];
    const ann = days >= 365 ? Math.pow(1 + ret, 365.25 / days) - 1 : null;
    const ser = mode === "price" ? c : tr;
    let sum = 0, sum2 = 0, k = 0, peak = ser[s], mdd = 0;
    for (let i = s + 1; i <= e; i++) {
      const lr = Math.log(ser[i] / ser[i - 1]); sum += lr; sum2 += lr * lr; k++;
      if (ser[i] > peak) peak = ser[i];
      const dd = ser[i] / peak - 1; if (dd < mdd) mdd = dd;
    }
    const vol = k >= 10 ? Math.sqrt(Math.max(0, (sum2 - sum * sum / k) / (k - 1)) * 252) : null;
    const divSum = cd[e] - cd[s];
    return { ret, ann, days, vol, mdd, divSum, start: etf.dates[s], end: etf.dates[e] };
  }
  function yield12(etf) {
    const e = etf.n - 1, since = etf.dates[e] - 365;
    let sum = 0, cnt = 0;
    etf.divs.forEach((d) => { if (d.day > since && d.day <= etf.dates[e]) { sum += d.amount; cnt++; } });
    return { y: sum / etf.c[e], cnt };
  }

  // ---------- 狀態
  const state = {
    period: { kind: "quick", key: "1y" }, mode: "tr", ann: false,
    q: "", type: "all", cats: new Set(CATS), market: "all", minVol: 0, hideShort: true,
    sort: { key: "ret", dir: -1 }, sel: [], bench: new Set(["^TWII"]),
  };
  function periodLabel(p) {
    if (p.kind === "quick") return Object.fromEntries(QUICK)[p.key];
    if (p.kind === "custom") return `${p.n} ${UNITS[p.unit]}`;
    return `${p.from} ～ ${p.to}`;
  }
  function periodCode(p) { return p.kind === "quick" ? p.key : p.kind === "custom" ? `c${p.n}${p.unit}` : `r${p.from}_${p.to}`; }
  function parsePeriod(s) {
    if (!s) return null;
    if (QUICK.some(([k]) => k === s)) return { kind: "quick", key: s };
    let m = /^c(\d+)(td|d|w|m|y)$/.exec(s);
    if (m) return { kind: "custom", n: +m[1], unit: m[2] };
    m = /^r(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/.exec(s);
    if (m) return { kind: "range", from: m[1], to: m[2] };
    return null;
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    const p = parsePeriod(h.get("p")); if (p) state.period = p;
    if (MODES[h.get("m")]) state.mode = h.get("m");
    if (h.get("a") === "1") state.ann = true;
    if (["all", "passive", "active"].includes(h.get("t"))) state.type = h.get("t");
    if (h.get("c")) state.cats = new Set(h.get("c").split(",").filter((c) => CATS.includes(c)));
    if (h.get("q")) state.q = h.get("q");
    if (h.get("s")) state.sel = h.get("s").split(",").filter((c) => byCode[c]).slice(0, MAX_SEL);
    if (h.has("b")) state.bench = new Set(h.get("b").split(",").filter(Boolean));
    if (h.get("v")) state.minVol = +h.get("v") || 0;
    if (h.get("h") === "0") state.hideShort = false;
    if (h.get("o")) { const [k, d] = h.get("o").split("."); state.sort = { key: k, dir: d === "a" ? 1 : -1 }; }
  }
  function writeHash() {
    const h = new URLSearchParams();
    h.set("p", periodCode(state.period)); h.set("m", state.mode);
    if (state.ann) h.set("a", "1");
    if (state.type !== "all") h.set("t", state.type);
    if (state.cats.size !== CATS.length) h.set("c", [...state.cats].join(","));
    if (state.q) h.set("q", state.q);
    if (state.sel.length) h.set("s", state.sel.join(","));
    if (!(state.bench.size === 1 && state.bench.has("^TWII"))) h.set("b", [...state.bench].join(","));
    if (state.minVol) h.set("v", String(state.minVol));
    if (!state.hideShort) h.set("h", "0");
    if (!(state.sort.key === "ret" && state.sort.dir === -1)) h.set("o", `${state.sort.key}.${state.sort.dir > 0 ? "a" : "d"}`);
    history.replaceState(null, "", "#" + h.toString());
  }

  // ---------- 控制列
  function renderControls() {
    $("#quick").innerHTML = QUICK.map(([k, l]) =>
      `<button class="chip" data-q="${k}" aria-pressed="${state.period.kind === "quick" && state.period.key === k}">${l}</button>`).join("");
    if (state.period.kind === "custom") { $("#c-n").value = state.period.n; $("#c-unit").value = state.period.unit; }
    if (state.period.kind === "range") { $("#r-from").value = state.period.from; $("#r-to").value = state.period.to; }
    else if (!$("#r-to").value) { $("#r-to").value = DATA.asof; $("#r-from").value = fromDay(shiftMonths(ASOF, 12)); }
    document.querySelectorAll("#mode .chip").forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === state.mode));
    document.querySelectorAll("#type .chip").forEach((b) => b.setAttribute("aria-pressed", b.dataset.type === state.type));
    $("#ann").checked = state.ann; $("#q").value = state.q; $("#market").value = state.market;
    $("#minvol").value = state.minVol; $("#hide-short").checked = state.hideShort;
    const counts = {};
    ETFS.forEach((e) => { counts[e.cat] = (counts[e.cat] || 0) + 1; });
    $("#cats").innerHTML = CATS.map((c) =>
      `<button class="chip" data-cat="${esc(c)}" aria-pressed="${state.cats.has(c)}">${esc(c)}<span class="cnt">${counts[c] || 0}</span></button>`).join("") +
      `<button class="chip" data-cat="*">全選／全不選</button>`;
    const benchOpts = BENCH.map((b) => [b.code, b.name]).concat([["0050", "0050"], ["0056", "0056"], ["006208", "006208"]]).filter(([c]) => byCode[c]);
    $("#bench").innerHTML = benchOpts.map(([c, l]) =>
      `<button class="chip" data-bench="${esc(c)}" aria-pressed="${state.bench.has(c)}">對照 ${esc(l)}</button>`).join("");
  }

  // ---------- 排行表
  const COLS = [
    { key: "rank", label: "#", cls: "rank" },
    { key: "sel", label: "", cls: "c" },
    { key: "code", label: "ETF", cls: "l", sortable: true },
    { key: "type", label: "類型", cls: "c hide-sm" },
    { key: "cat", label: "分類", cls: "l hide-sm", sortable: true },
    { key: "last", label: "收盤", sortable: true },
    { key: "ret", label: "期間報酬", sortable: true },
    { key: "vol", label: "年化波動", sortable: true },
    { key: "mdd", label: "最大回撤", sortable: true },
    { key: "divSum", label: "期間配息", sortable: true },
    { key: "y12", label: "近12月配息率", sortable: true },
    { key: "vol20", label: "20日均量(張)", sortable: true },
    { key: "listed", label: "上市日", sortable: true, cls: "hide-sm" },
  ];
  let rowsCache = [];
  function computeRows() {
    const q = state.q.trim().toLowerCase();
    return ETFS.filter((e) =>
      (state.type === "all" || (state.type === "active") === !!e.active) &&
      state.cats.has(e.cat) &&
      (state.market === "all" || e.market === state.market) &&
      (!state.minVol || e.vol20 / 1000 >= state.minVol) &&
      (!q || e.code.toLowerCase().includes(q) || e.name.toLowerCase().includes(q)))
    .map((e) => {
      const r = resolve(e, state.period);
      const m = r ? metrics(e, r, state.mode) : null;
      const y = yield12(e);
      return { e, m, y12: y.y, cnt12: y.cnt, retShown: m ? (state.ann && m.ann != null ? m.ann : m.ret) : null };
    });
  }
  function sortRows(rows) {
    const { key, dir } = state.sort;
    const val = (r) => {
      switch (key) {
        case "code": return r.e.code; case "cat": return r.e.cat; case "listed": return r.e.listed || "";
        case "last": return r.e.last; case "vol20": return r.e.vol20; case "y12": return r.y12;
        case "ret": return r.retShown; case "vol": return r.m ? r.m.vol : null;
        case "mdd": return r.m ? r.m.mdd : null; case "divSum": return r.m ? r.m.divSum : null;
        default: return null;
      }
    };
    rows.sort((a, b) => {
      const x = val(a), y = val(b);
      const xn = x == null || x === "" || (typeof x === "number" && !isFinite(x)), yn = y == null || y === "" || (typeof y === "number" && !isFinite(y));
      if (xn && yn) return a.e.code < b.e.code ? -1 : 1;
      if (xn) return 1; if (yn) return -1;
      if (typeof x === "string") return dir * x.localeCompare(y, "zh-Hant");
      return dir * (x - y);
    });
  }
  function renderTable() {
    let rows = computeRows();
    const short = rows.filter((r) => !r.m).length;
    if (state.hideShort) rows = rows.filter((r) => r.m);
    sortRows(rows);
    rowsCache = rows;
    const annMode = state.ann;
    const retLabel = `${periodLabel(state.period)}${annMode ? "年化" : ""}報酬`;
    const head = COLS.map((c) => {
      const sorted = state.sort.key === c.key;
      const label = c.key === "ret" ? retLabel : c.label;
      const arrow = sorted ? (state.sort.dir > 0 ? " ▲" : " ▼") : "";
      return `<th class="${c.cls || ""}${sorted ? " sorted" : ""}" ${c.sortable ? `data-sort="${c.key}"` : ""}>${esc(label)}${arrow}</th>`;
    }).join("");
    const selSet = new Set(state.sel);
    const body = rows.map((r, i) => {
      const e = r.e, m = r.m;
      return `<tr class="${selSet.has(e.code) ? "is-sel" : ""}" data-code="${esc(e.code)}">
        <td class="rank">${i + 1}</td>
        <td class="c"><input type="checkbox" data-sel="${esc(e.code)}" ${selSet.has(e.code) ? "checked" : ""} ${!selSet.has(e.code) && state.sel.length >= MAX_SEL ? "disabled" : ""}></td>
        <td class="l"><span class="name" data-detail="${esc(e.code)}"><span class="code">${esc(e.code)}</span>${esc(e.name)}</span></td>
        <td class="c hide-sm"><span class="tag ${e.active ? "active" : "passive"}">${e.active ? "主動" : "被動"}</span></td>
        <td class="l hide-sm">${esc(e.cat)}</td>
        <td class="num">${num(e.last)}</td>
        <td class="num">${m ? pct(r.retShown) : `<span class="na">資料不足</span>`}</td>
        <td class="num">${m && m.vol != null ? (m.vol * 100).toFixed(1) + "%" : '<span class="na">—</span>'}</td>
        <td class="num">${m ? pct(m.mdd, 1) : '<span class="na">—</span>'}</td>
        <td class="num">${m ? (m.divSum ? num(m.divSum, 3) : '<span class="na">0</span>') : '<span class="na">—</span>'}</td>
        <td class="num">${r.y12 ? `${(r.y12 * 100).toFixed(2)}% <span class="na">(${r.cnt12}次)</span>` : '<span class="na">—</span>'}</td>
        <td class="num">${e.vol20 ? Math.round(e.vol20 / 1000).toLocaleString() : '<span class="na">—</span>'}</td>
        <td class="hide-sm">${esc(e.listed || "")}</td>
      </tr>`;
    }).join("");
    $("#tbl").innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
    $("#rank-sub").textContent = `${rows.length} 檔｜${MODES[state.mode]}｜${periodLabel(state.period)}`;
    const notes = [];
    if (short) notes.push(state.hideShort ? `另有 ${short} 檔因上市未滿此期間（或期間內無資料）未列出，取消「隱藏資料不足」可顯示。` : `${short} 檔資料不足，排在最後。`);
    if (state.period.kind === "quick" && state.period.key === "max") notes.push("「上市以來」各檔起點不同，不宜直接相互比較。");
    if (annMode) notes.push("年化報酬只對期間 ≥ 1 年者顯示，其餘仍為累積報酬。");
    if (!rows.length) notes.push("沒有符合條件的 ETF。");
    $("#tbl-note").textContent = notes.join(" ");
  }

  // ---------- 比較圖
  function seriesFor(etf, mode) { return mode === "price" ? etf.c : etf.tr; }
  function renderCompare() {
    const picks = state.sel.map((c) => byCode[c]).filter(Boolean);
    const benches = [...state.bench].map((c) => byCode[c]).filter((b) => b && !state.sel.includes(b.code));
    const all = picks.concat(benches);
    const host = $("#chart");
    $("#cmp-sub").textContent = `${MODES[state.mode]}｜${periodLabel(state.period)}${state.mode !== "price" ? "｜加權指數為價格指數（不含息）" : ""}`;
    if (!picks.length) {
      host.innerHTML = '<div class="hint">在下方排行勾選最多 8 檔 ETF，這裡會畫出同一起點（0%）的走勢比較。</div>';
      $("#cmp-table").innerHTML = "";
      return;
    }
    const lines = [];
    let x0 = Infinity, x1 = -Infinity, y0 = 0, y1 = 0;
    all.forEach((etf, i) => {
      const r = resolve(etf, state.period);
      if (!r) { lines.push({ etf, pts: null, isBench: i >= picks.length, color: i < picks.length ? COLORS[i % COLORS.length] : "--bench" }); return; }
      const ser = seriesFor(etf, state.mode), base = ser[r.s];
      const pts = [];
      const mode = state.mode;
      for (let k = r.s; k <= r.e; k++) {
        const v = mode === "trx" ? (etf.c[k] + etf.cd[k] - etf.cd[r.s]) / etf.c[r.s] - 1 : ser[k] / base - 1;
        pts.push([etf.dates[k], v]);
        if (v < y0) y0 = v; if (v > y1) y1 = v;
      }
      x0 = Math.min(x0, pts[0][0]); x1 = Math.max(x1, pts[pts.length - 1][0]);
      lines.push({ etf, pts, isBench: i >= picks.length, color: i < picks.length ? COLORS[i % COLORS.length] : "--bench" });
    });
    const W = 860, H = 320, L = 52, R = 14, T = 12, B = 26;
    if (!isFinite(x0) || x1 <= x0) { host.innerHTML = '<div class="hint">所選 ETF 在此期間都沒有足夠資料。</div>'; $("#cmp-table").innerHTML = ""; return; }
    const pad = (y1 - y0) * 0.06 || 0.01; y0 -= pad; y1 += pad;
    const sx = (x) => L + (x - x0) / (x1 - x0) * (W - L - R);
    const sy = (y) => T + (y1 - y) / (y1 - y0) * (H - T - B);
    const yt = niceTicks(y0, y1, 5), xt = dateTicks(x0, x1, 6);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="走勢比較圖"><g class="grid">`;
    yt.forEach((v) => { svg += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" ${Math.abs(v) < 1e-9 ? 'class="zero"' : ""}/>`; });
    svg += `</g><g class="axis">`;
    yt.forEach((v) => { svg += `<text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${(v * 100).toFixed(Math.abs(y1 - y0) < 0.1 ? 1 : 0)}%</text>`; });
    xt.forEach((d) => { svg += `<text x="${sx(d)}" y="${H - 8}" text-anchor="middle">${fromDay(d).slice(0, 7)}</text>`; });
    svg += `</g>`;
    lines.forEach((ln) => {
      if (!ln.pts) return;
      const d = ln.pts.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
      svg += `<path class="line${ln.isBench ? " bench" : ""}" stroke="var(${ln.color})" d="${d}"/>`;
    });
    svg += `<line class="cursor" id="cursor" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/></svg>`;
    const legend = lines.map((ln) => `<span><i class="sw" style="background:var(${ln.color})"></i>${esc(ln.etf.code)} ${esc(ln.etf.name)}${ln.pts ? "" : "（資料不足）"}${ln.isBench ? "" : `<span class="x" data-unsel="${esc(ln.etf.code)}" title="移除">✕</span>`}</span>`).join("");
    host.innerHTML = svg + `<div class="legend">${legend}</div><div class="tip" id="tip" hidden></div>`;
    hookHover(host, lines, sx, x0, x1, W, L, R);

    // 比較表：所選各檔在標準期間的報酬
    const cols = QUICK.filter(([k]) => k !== "max");
    let t = `<table class="cmp"><thead><tr><th class="l">ETF</th><th>目前期間</th>${cols.map(([, l]) => `<th>${l}</th>`).join("")}<th>期間波動</th><th>期間回撤</th></tr></thead><tbody>`;
    all.forEach((etf, i) => {
      const cur = resolve(etf, state.period), m = cur ? metrics(etf, cur, state.mode) : null;
      t += `<tr><td class="l"><i class="sw" style="background:var(${i < picks.length ? COLORS[i % COLORS.length] : "--bench"})"></i>${esc(etf.code)} ${esc(etf.name)}</td>`;
      t += `<td>${m ? pct(state.ann && m.ann != null ? m.ann : m.ret) : '<span class="na">—</span>'}</td>`;
      cols.forEach(([k]) => { const r = resolve(etf, { kind: "quick", key: k }); t += `<td>${r ? pct(metrics(etf, r, state.mode).ret) : '<span class="na">—</span>'}</td>`; });
      t += `<td>${m && m.vol != null ? (m.vol * 100).toFixed(1) + "%" : "—"}</td><td>${m ? pct(m.mdd, 1) : "—"}</td></tr>`;
    });
    $("#cmp-table").innerHTML = t + "</tbody></table>";
  }
  function niceTicks(a, b, n) {
    const raw = (b - a) / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
    const out = []; for (let v = Math.ceil(a / step) * step; v <= b + 1e-12; v += step) out.push(+v.toFixed(10)); return out;
  }
  function dateTicks(a, b, n) { const out = []; for (let i = 0; i <= n; i++) out.push(Math.round(a + (b - a) * i / n)); return out; }
  function hookHover(host, lines, sx, x0, x1, W, L, R) {
    const svg = host.querySelector("svg"), tip = host.querySelector("#tip"), cur = host.querySelector("#cursor");
    const show = (clientX) => {
      const rect = svg.getBoundingClientRect();
      const x = (clientX - rect.left) / rect.width * W;
      if (x < L || x > W - R) { tip.hidden = true; cur.setAttribute("visibility", "hidden"); return; }
      const day = Math.round(x0 + (x - L) / (W - L - R) * (x1 - x0));
      let html = `<b>${fromDay(day)}</b>`;
      lines.forEach((ln) => {
        if (!ln.pts) return;
        const i = lastIdxLE(ln.pts.map((p) => p[0]), day);
        if (i < 0) return;
        html += `<div class="row"><span><i class="sw" style="background:var(${ln.color})"></i>${esc(ln.etf.code)}</span>${pct(ln.pts[i][1])}</div>`;
      });
      tip.innerHTML = html; tip.hidden = false;
      const px = (x - L) / (W - L - R);
      tip.style.left = px > 0.6 ? "8px" : "auto"; tip.style.right = px > 0.6 ? "auto" : "8px";
      cur.setAttribute("x1", sx(day)); cur.setAttribute("x2", sx(day)); cur.setAttribute("visibility", "visible");
    };
    svg.addEventListener("mousemove", (ev) => show(ev.clientX));
    svg.addEventListener("touchmove", (ev) => { show(ev.touches[0].clientX); ev.preventDefault(); }, { passive: false });
    svg.addEventListener("mouseleave", () => { tip.hidden = true; cur.setAttribute("visibility", "hidden"); });
  }

  // ---------- 明細
  function openDetail(code) {
    const e = byCode[code]; if (!e) return;
    const y = yield12(e);
    const periods = QUICK;
    let rows = periods.map(([k, l]) => {
      const r = resolve(e, { kind: "quick", key: k });
      if (!r) return `<tr><td class="l">${l}</td><td colspan="4"><span class="na">資料不足</span></td></tr>`;
      const a = metrics(e, r, "price"), b = metrics(e, r, "tr"), c = metrics(e, r, "trx");
      return `<tr><td class="l">${l}<span class="na"> ${fromDay(a.start)}起</span></td><td>${pct(a.ret)}</td><td>${pct(b.ret)}</td><td>${pct(c.ret)}</td><td>${b.ann != null ? pct(b.ann) : '<span class="na">—</span>'}</td></tr>`;
    }).join("");
    const divs = e.divs.slice().reverse().slice(0, 24).map((d) =>
      `<tr><td class="l">${fromDay(d.day)}</td><td>${num(d.amount, 3)}</td><td>${(d.amount / d.close * 100).toFixed(2)}%</td></tr>`).join("");
    const yahoo = `https://tw.stock.yahoo.com/quote/${encodeURIComponent(e.code)}${e.market === "上櫃" ? ".TWO" : ".TW"}`;
    $("#detail").innerHTML = `
      <div class="dlg-head"><h3>${esc(e.code)} ${esc(e.name)} <span class="tag ${e.active ? "active" : "passive"}">${e.active ? "主動式" : "被動式"}</span></h3>
        <button class="btn" data-close>關閉</button></div>
      <div class="dlg-body">
        <div class="kv">
          <div><span>市場</span><b>${esc(e.market)}</b></div><div><span>分類</span><b>${esc(e.cat)}</b></div>
          <div><span>上市日</span><b>${esc(e.listed || "—")}</b></div><div><span>資料起點</span><b>${esc(e.d0)}</b></div>
          <div><span>最新收盤</span><b>${num(e.last)}</b> <span>(${esc(e.lastDate)})</span></div>
          <div><span>近 12 月配息率</span><b>${y.y ? (y.y * 100).toFixed(2) + "%" : "—"}</b> <span>${y.cnt} 次</span></div>
          <div><span>20 日均量</span><b>${e.vol20 ? Math.round(e.vol20 / 1000).toLocaleString() + " 張" : "—"}</b></div>
          <div><span>外部連結</span><a href="${yahoo}" target="_blank" rel="noopener">Yahoo 股市</a></div>
        </div>
        ${(e.adj || []).length ? `<div class="na" style="margin-top:8px">價格已依偵測到的分割／反分割回溯調整：${e.adj.map(([d, f]) => `${esc(d)} ×${f}`).join("、")}</div>` : ""}
        <h4>標準期間報酬</h4>
        <table class="cmp"><thead><tr><th class="l">期間</th><th>不含息</th><th>含息再投入</th><th>含息不再投入</th><th>含息年化</th></tr></thead><tbody>${rows}</tbody></table>
        <h4>配息紀錄（最近 24 次，除息日／每單位／以當日收盤計之單次殖利率）</h4>
        ${divs ? `<table class="cmp"><thead><tr><th class="l">除息日</th><th>配息</th><th>單次殖利率</th></tr></thead><tbody>${divs}</tbody></table>` : '<div class="na">沒有配息紀錄（或資料來源未收錄）。</div>'}
      </div>`;
    $("#detail").showModal();
  }

  // ---------- 其他
  function stampAndFooter() {
    $("#stamp").textContent = `資料至 ${DATA.asof}｜更新 ${DATA.generated}`;
    const errs = (DATA.errors || []);
    $("#footer").innerHTML = `
      <div>來源：${esc(DATA.sources.list)}；價格與除息資料：${esc(DATA.sources.prices)}。共 ${DATA.count} 檔上市櫃 ETF，每個交易日收盤後自動更新。</div>
      <div>說明：報酬以<b>市價（收盤價）</b>計算，非基金淨值；「含息再投入」假設除息日以收盤價買回，「含息不再投入」為價格差＋累計配息；
      天／週／月／年以日曆推算，起點取該日或之前最近一個交易日；年化波動以日報酬標準差 ×√252；主動／被動與分類依證交所代號末碼與名稱關鍵字判斷，可能有誤。
      未計手續費、交易稅、二代健保補充保費與配息所得稅。槓桿／反向 ETF 每日重設，長期績效不等於指數倍數。僅供參考，非投資建議。</div>
      ${errs.length ? `<details><summary>本次更新有 ${errs.length} 項資料未更新成功（沿用前次資料）</summary>${errs.map((x) => `<div>${esc(x)}</div>`).join("")}</details>` : ""}`;
  }
  function refresh() { writeHash(); renderTable(); renderCompare(); }

  function bind() {
    $("#quick").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-q]"); if (!b) return;
      state.period = { kind: "quick", key: b.dataset.q }; renderControls(); refresh();
    });
    $("#custom-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const n = parseInt($("#c-n").value, 10); if (!(n > 0)) return;
      state.period = { kind: "custom", n, unit: $("#c-unit").value }; renderControls(); refresh();
    });
    $("#range-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const from = $("#r-from").value, to = $("#r-to").value;
      if (!from || !to || from >= to) { alert("起日必須早於訖日"); return; }
      state.period = { kind: "range", from, to }; renderControls(); refresh();
    });
    $("#mode").addEventListener("click", (ev) => { const b = ev.target.closest("[data-mode]"); if (!b) return; state.mode = b.dataset.mode; renderControls(); refresh(); });
    $("#type").addEventListener("click", (ev) => { const b = ev.target.closest("[data-type]"); if (!b) return; state.type = b.dataset.type; renderControls(); refresh(); });
    $("#ann").addEventListener("change", (ev) => { state.ann = ev.target.checked; refresh(); });
    $("#hide-short").addEventListener("change", (ev) => { state.hideShort = ev.target.checked; refresh(); });
    $("#market").addEventListener("change", (ev) => { state.market = ev.target.value; refresh(); });
    $("#minvol").addEventListener("change", (ev) => { state.minVol = Math.max(0, +ev.target.value || 0); refresh(); });
    let qt; $("#q").addEventListener("input", (ev) => { clearTimeout(qt); qt = setTimeout(() => { state.q = ev.target.value; refresh(); }, 150); });
    $("#cats").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-cat]"); if (!b) return;
      const c = b.dataset.cat;
      if (c === "*") state.cats = state.cats.size === CATS.length ? new Set() : new Set(CATS);
      else if (state.cats.has(c)) state.cats.delete(c); else state.cats.add(c);
      renderControls(); refresh();
    });
    $("#bench").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-bench]"); if (!b) return;
      const c = b.dataset.bench; if (state.bench.has(c)) state.bench.delete(c); else state.bench.add(c);
      renderControls(); refresh();
    });
    $("#tbl").addEventListener("click", (ev) => {
      const th = ev.target.closest("th[data-sort]");
      if (th) { const k = th.dataset.sort; state.sort = state.sort.key === k ? { key: k, dir: -state.sort.dir } : { key: k, dir: k === "code" || k === "cat" || k === "listed" ? 1 : -1 }; refresh(); return; }
      const d = ev.target.closest("[data-detail]"); if (d) { openDetail(d.dataset.detail); return; }
    });
    $("#tbl").addEventListener("change", (ev) => {
      const cb = ev.target.closest("[data-sel]"); if (!cb) return;
      const c = cb.dataset.sel;
      if (cb.checked) { if (!state.sel.includes(c) && state.sel.length < MAX_SEL) state.sel.push(c); }
      else state.sel = state.sel.filter((x) => x !== c);
      refresh();
    });
    $("#chart").addEventListener("click", (ev) => { const x = ev.target.closest("[data-unsel]"); if (!x) return; state.sel = state.sel.filter((c) => c !== x.dataset.unsel); refresh(); });
    $("#clear-sel").addEventListener("click", () => { state.sel = []; refresh(); });
    $("#detail").addEventListener("click", (ev) => { if (ev.target.closest("[data-close]") || ev.target === ev.currentTarget) $("#detail").close(); });
    $("#csv").addEventListener("click", () => {
      const head = ["排名", "代號", "名稱", "類型", "分類", "市場", "收盤", `${periodLabel(state.period)}報酬%(${MODES[state.mode]})`, "年化報酬%", "起日", "訖日", "年化波動%", "最大回撤%", "期間配息", "近12月配息率%", "近12月配息次數", "20日均量(張)", "上市日"];
      const lines = rowsCache.map((r, i) => {
        const e = r.e, m = r.m;
        return [i + 1, e.code, e.name, e.active ? "主動" : "被動", e.cat, e.market, e.last,
          m ? pctPlain(m.ret) : "", m && m.ann != null ? pctPlain(m.ann) : "", m ? fromDay(m.start) : "", m ? fromDay(m.end) : "",
          m && m.vol != null ? pctPlain(m.vol, 1) : "", m ? pctPlain(m.mdd, 1) : "", m ? m.divSum.toFixed(3) : "",
          pctPlain(r.y12), r.cnt12, Math.round(e.vol20 / 1000), e.listed || ""].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",");
      });
      const blob = new Blob(["﻿" + [head.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = `tw-etf-${periodCode(state.period)}-${state.mode}-${DATA.asof}.csv`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
    window.addEventListener("hashchange", () => { readHash(); renderControls(); refresh(); });
  }

  readHash();
  stampAndFooter();
  renderControls();
  bind();
  refresh();
})();
