"""組裝：ETF 清單 + Yahoo 日線 → docs/data/etf.js（網頁直接以 <script> 載入，本機開檔也能用）。

資料格式（每檔）：
  d0   第一筆日期（ISO）
  dd   與前一筆相隔天數（第一筆為 0），累加即可還原日期
  c    收盤價（Yahoo 已就分割回溯調整）
  div  [[列索引, 每單位配息], ...]（除息日對應的列；含息報酬在網頁端計算）
  vol20 近 20 日平均成交量（股）
  adj  [[日期, 倍數], ...] 偵測到的分割／反分割（Yahoo 常漏掉台灣槓反 ETF 的反分割），舊價已乘上倍數
含息／年化／波動／回撤等全部在網頁端計算，Python 只負責抓資料與合併快取。
"""
import json
import os
import time
from datetime import date, datetime, timedelta

from briefing.util import now_tw
from . import universe, yahoo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data", "etf.js")
PREFIX = "window.ETF_DATA="
BENCH = [{"code": "^TWII", "name": "加權指數", "yahoo": "^TWII", "cat": "指數", "note": "價格指數，不含股息"}]
STALE_DAYS = 25      # 快取最後日期太舊就全抓
PAUSE = 0.35         # 每檔之間停一下，避免被 Yahoo 限流
MAX_STREAK = 12      # 連續失敗這麼多檔就判定被限流，其餘沿用快取，讓部署不被拖住


# ---------------------------------------------------------------- 快取

def load_cache():
    try:
        with open(OUT, encoding="utf-8") as f:
            text = f.read()
        text = text[text.index("{"):].rstrip().rstrip(";")
        data = json.loads(text)
        out = {}
        for e in data.get("etfs", []) + data.get("bench", []):
            out[e["code"]] = decode(e)
        return out
    except Exception:  # noqa: BLE001 — 沒有快取或格式不對就全抓
        return {}


def decode(e):
    """壓縮格式 → {"rows": {日期: [收盤, 量]}, "div": {日期: 金額}}。"""
    rows, div = {}, {}
    if e.get("d0") and e.get("dd"):
        d = date.fromisoformat(e["d0"])
        dates = []
        for i, gap in enumerate(e["dd"]):
            d = d + timedelta(days=gap)
            dates.append(d.isoformat())
            rows[d.isoformat()] = [e["c"][i], 0]
        for idx, amt in e.get("div") or []:
            if 0 <= idx < len(dates):
                div[dates[idx]] = amt
    return {"rows": rows, "div": div, "splits": []}


def encode(hist):
    dates = sorted(hist["rows"])
    if not dates:
        return None
    dd, prev = [], None
    for d in dates:
        cur = date.fromisoformat(d)
        dd.append(0 if prev is None else (cur - prev).days)
        prev = cur
    closes = [round(hist["rows"][d][0], 2) for d in dates]
    pos = {d: i for i, d in enumerate(dates)}
    div = []
    for d in sorted(hist["div"]):
        i = pos.get(d)
        if i is None:  # 除息日不是交易日（罕見），對到之後第一個交易日
            later = [x for x in dates if x > d]
            i = pos[later[0]] if later else None
        if i is not None and i > 0:
            div.append([i, round(hist["div"][d], 4)])
    vols = [hist["rows"][d][1] for d in dates[-20:] if hist["rows"][d][1]]
    return {"d0": dates[0], "dd": dd, "c": closes, "div": div, "adj": hist.get("adj") or [],
            "vol20": int(sum(vols) / len(vols)) if vols else 0,
            "last": closes[-1], "lastDate": dates[-1]}


SPLIT_N = (2, 3, 4, 5, 8, 10)


def adjust_splits(hist):
    """偵測未被 Yahoo 調整的分割／反分割：相鄰兩日收盤比接近整數倍（±12%）就把之前的價格與配息乘上倍數。

    ETF 單日漲跌不可能接近 2 倍或腰斬（台股有漲跌幅限制，海外槓桿 ETF 也遠不到），所以誤判機率極低；
    偵測結果會存進 adj 欄位，網頁明細會標示。"""
    rows, div = hist["rows"], hist["div"]
    dates = sorted(rows)
    found = []
    for i in range(1, len(dates)):
        p0, p1 = rows[dates[i - 1]][0], rows[dates[i]][0]
        if not p0 or not p1:
            continue
        r = p1 / p0
        factor = None
        for n in SPLIT_N:
            if abs(r - n) / n < 0.12:
                factor = float(n)          # 反分割 n 合 1：舊價 ×n
            elif abs(r - 1 / n) * n < 0.12:
                factor = 1 / n             # 分割 1 拆 n：舊價 ÷n
        if factor:
            for d in dates[:i]:
                rows[d][0] *= factor
                rows[d][1] = int(rows[d][1] / factor)
            for d in list(div):
                if d < dates[i]:
                    div[d] *= factor
            found.append([dates[i], round(factor, 4)])
    hist["adj"] = found
    return found


def merge(old, new):
    rows = dict(old["rows"]) if old else {}
    rows.update(new["rows"])                       # 同日期以新資料為準
    div = dict(old["div"]) if old else {}
    div.update(new["div"])
    return {"rows": rows, "div": div, "splits": new.get("splits", [])}


# ---------------------------------------------------------------- 主流程

def _update(symbol, cached, full, errors, label):
    last = max(cached["rows"]) if cached and cached["rows"] else None
    stale = (not last) or (date.today() - date.fromisoformat(last)).days > STALE_DAYS
    need_full = full or stale
    try:
        new = yahoo.fetch_history(symbol, "max" if need_full else "1mo")
        if not need_full and new["splits"] and max(new["splits"]) > last:
            new = yahoo.fetch_history(symbol, "max")   # 期間有分割：Yahoo 會回溯調整舊價，要整段重抓
            need_full = True
    except Exception as e:  # noqa: BLE001
        errors.append(f"{label}：{e}")
        return cached
    if not new["rows"]:
        errors.append(f"{label}：Yahoo 沒有價格資料")
        return cached
    return new if need_full else merge(cached, new)


def run(full=False, limit=None):
    t0 = time.time()
    errors = []
    if not full and now_tw().weekday() == 5:
        full = True          # 每週六整段重抓，吸收 Yahoo 的事後修正
    etfs = universe.collect(errors)
    if limit:
        etfs = etfs[:limit]
    if not etfs:
        print("抓不到 ETF 清單，保留原檔不動")
        for e in errors:
            print(" -", e)
        return 1
    cache = load_cache()
    print(f"ETF {len(etfs)} 檔，快取 {len(cache)} 檔，{'全抓' if full else '增量'}")

    out_etfs = []
    streak, halted = 0, False
    for i, e in enumerate(etfs, 1):
        cached = cache.get(e["code"])
        if halted:
            hist = cached
        else:
            before = len(errors)
            hist = _update(e["yahoo"], cached, full, errors, f"{e['code']} {e['name']}")
            streak = streak + 1 if len(errors) > before else 0
            if streak >= MAX_STREAK:
                halted = True
                errors.append(f"連續 {MAX_STREAK} 檔抓取失敗（可能被 Yahoo 限流），其餘 {len(etfs) - i} 檔沿用前次資料")
                print(" !", errors[-1])
        if hist:
            for day, factor in adjust_splits(hist):
                print(f"  {e['code']} {e['name']}：{day} 偵測到{'反' if factor > 1 else ''}分割 ×{factor:g}，已回溯調整")
        enc = encode(hist) if hist else None
        if enc:
            item = {k: e[k] for k in ("code", "name", "market", "listed", "active", "cat", "region")}
            item.update(enc)
            out_etfs.append(item)
        if i % 25 == 0:
            print(f"  {i}/{len(etfs)}")
        if not halted:
            time.sleep(PAUSE)

    bench = []
    for b in BENCH:
        hist = cache.get(b["code"]) if halted else _update(b["yahoo"], cache.get(b["code"]), full, errors, b["name"])
        enc = encode(hist) if hist else None
        if enc:
            item = dict(b)
            item.update(enc)
            bench.append(item)

    asof = max((e["lastDate"] for e in out_etfs), default="")
    data = {"generated": now_tw().strftime("%Y-%m-%d %H:%M"), "asof": asof,
            "count": len(out_etfs), "errors": errors,
            "sources": {"list": "證交所／櫃買中心 ISIN 名冊", "prices": "Yahoo Finance（市價、除息）"},
            "etfs": out_etfs, "bench": bench}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    size = os.path.getsize(OUT) / 1e6
    print(f"完成：{len(out_etfs)} 檔，最新交易日 {asof}，{size:.1f} MB，{time.time() - t0:.0f} 秒，錯誤 {len(errors)} 筆")
    for e in errors[:30]:
        print(" -", e)
    return 0
