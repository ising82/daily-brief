"""過去 24 小時財經新聞：鉅亨網 API ＋ 中央社、經濟日報、Yahoo、CNBC、WSJ 等 RSS。

同標題跨來源合併，依來源權重、關鍵字、被多家報導、時效性計分，挑出重點新聞。
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .util import TW, fetch, fetch_json, strip_html, truncate

CNYES_API = "https://api.cnyes.com/media/api/v1/newslist/category/{}?page=1&limit={}"
CNYES = [  # (分類, 權重, 預設標籤, 筆數)
    ("headline", 3.0, (), 40),
    ("tw_stock", 1.5, ("台股",), 30),
    ("wd_stock", 1.5, ("美股",), 30),
    ("wd_macro", 1.5, ("總經",), 30),
    ("tw_macro", 1.5, ("總經",), 30),
    ("forex", 1.0, ("外匯原物料",), 20),
]
RSS = [  # (來源, 網址, 語言, 權重, 預設標籤)
    ("中央社", "https://feeds.feedburner.com/rsscna/finance", "zh", 2.0, ()),
    ("經濟日報", "https://money.udn.com/rssfeed/news/1001/5591?ch=money", "zh", 2.0, ()),
    ("經濟日報", "https://money.udn.com/rssfeed/news/1001/5588?ch=money", "zh", 2.0, ()),
    ("Yahoo股市", "https://tw.stock.yahoo.com/rss?category=news", "zh", 1.0, ("台股",)),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "en", 1.5, ()),
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "en", 1.5, ("總經",)),
    ("WSJ", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "en", 1.5, ("美股",)),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "en", 1.0, ()),
]

# 標籤（順序即網頁篩選按鈕順序）
TAGS = {
    "台股": ["台股", "加權", "櫃買", "外資", "投信", "三大法人", "台指", "上市櫃", "台積電", "鴻海", "聯發科"],
    "美股": ["美股", "道瓊", "那斯達克", "標普", "費半", "華爾街", "S&P", "Nasdaq", "Dow",
             "Wall Street", "stocks", "stock market"],
    "總經": ["聯準會", "Fed", "FOMC", "通膨", "CPI", "PCE", "非農", "就業", "GDP", "利率", "降息",
             "升息", "央行", "殖利率", "美債", "關稅", "景氣", "inflation", "tariff", "Treasury",
             "jobs", "economy", "recession"],
    "科技": ["AI", "輝達", "半導體", "晶片", "台積電", "伺服器", "記憶體", "美光", "蘋果", "微軟",
             "博通", "甲骨文", "NVIDIA", "Nvidia", "TSMC", "chip", "chips", "semiconductor",
             "Apple", "Microsoft", "Broadcom", "Oracle", "OpenAI", "Micron"],
    "外匯原物料": ["美元", "匯率", "新台幣", "台幣", "日圓", "黃金", "金價", "油價", "原油", "比特幣",
               "dollar", "gold", "oil", "crude", "bitcoin", "crypto"],
}
BOOST = [  # (關鍵字, 加分)
    (["聯準會", "FOMC", "鮑爾", "Fed", "Powell"], 3),
    (["升息", "降息", "利率決議", "利率決策", "rate cut", "rate hike"], 3),
    (["CPI", "通膨", "PCE", "非農", "inflation", "payrolls"], 2),
    (["台積電", "輝達", "TSMC", "Nvidia", "NVIDIA"], 2),
    (["關稅", "貿易戰", "tariff", "tariffs"], 2),
    (["央行", "殖利率", "美債", "Treasury", "yields"], 1.5),
    (["財報", "法說", "營收", "財測", "earnings", "guidance"], 1),
    (["台股", "美股", "外資", "華爾街", "stocks", "Wall Street"], 1),
    (["重挫", "暴跌", "大漲", "創新高", "崩跌", "record", "plunge", "surge", "soar", "tumble"], 1),
]


def _kw(k):
    if k.isascii():  # 英文用字邊界，避免 AI 命中 SAID
        flags = 0 if k.isupper() else re.I
        return re.compile(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", flags)
    return re.compile(re.escape(k))


_TAGS = [(tag, [_kw(k) for k in kws]) for tag, kws in TAGS.items()]
_BOOST = [([_kw(k) for k in kws], w) for kws, w in BOOST]


def _cnyes(errors):
    out = []
    for cat, weight, tags, limit in CNYES:
        try:
            data = fetch_json(CNYES_API.format(cat, limit))
        except Exception as e:  # noqa: BLE001
            errors.append(f"鉅亨網 {cat}：{e}")
            continue
        for it in ((data or {}).get("items") or {}).get("data") or []:
            nid, ts = it.get("newsId"), it.get("publishAt")
            title = strip_html(it.get("title") or "")
            if not nid or not ts or not title:
                continue
            kws = [k for k in (it.get("keyword") or []) if isinstance(k, str)]
            out.append({
                "title": title, "url": f"https://news.cnyes.com/news/id/{nid}",
                "source": "鉅亨網", "lang": "zh", "dt": datetime.fromtimestamp(int(ts), TW),
                "summary": strip_html(it.get("summary") or "") or strip_html(it.get("content") or "")[:300],
                "weight": weight, "tags": set(tags), "extra": " ".join(kws),
            })
    return out


def _rss(errors, include_en):
    out = []
    for name, url, lang, weight, tags in RSS:
        if lang == "en" and not include_en:
            continue
        try:
            root = ET.fromstring(fetch(url))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} RSS：{e}")
            continue
        for item in root.iter("item"):
            title = strip_html(item.findtext("title") or "")
            link = (item.findtext("link") or "").strip()
            try:
                dt = parsedate_to_datetime(item.findtext("pubDate") or "")
            except (TypeError, ValueError, IndexError):
                continue
            if not title or not link or dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out.append({
                "title": title, "url": link, "source": name, "lang": lang,
                "dt": dt.astimezone(TW), "summary": strip_html(item.findtext("description") or ""),
                "weight": weight, "tags": set(tags), "extra": "",
            })
    return out


def _norm(title):
    return re.sub(r"[\W_]+", "", title.lower())[:18]


def collect(cfg, now, errors):
    """回傳 (新聞列表[新→舊], 重點新聞 id 列表)。"""
    c = cfg.get("news") or {}
    since = now - timedelta(hours=float(c.get("hours", 24)))
    top_n = int(c.get("top_n", 12))
    raw = _cnyes(errors) + _rss(errors, c.get("include_english", True))

    merged = {}
    for it in raw:
        if not since <= it["dt"] <= now + timedelta(minutes=10):
            continue
        key = _norm(it["title"])
        if not key:
            continue
        cur = merged.get(key)
        if cur is None:
            it["sources"] = {it["source"]}
            merged[key] = it
            continue
        cur["sources"].add(it["source"])
        cur["tags"] |= it["tags"]
        cur["dt"] = min(cur["dt"], it["dt"])
        if it["weight"] > cur["weight"]:
            cur.update(title=it["title"], url=it["url"], source=it["source"],
                       weight=it["weight"], summary=it["summary"] or cur["summary"])

    items = []
    for it in merged.values():
        text = f"{it['title']} {it['summary'][:200]} {it['extra']}"
        for tag, pats in _TAGS:
            if any(p.search(text) for p in pats):
                it["tags"].add(tag)
        score = it["weight"]
        score += sum(w for pats, w in _BOOST if any(p.search(text) for p in pats))
        score += 0.8 * (len(it["sources"]) - 1)
        age_h = (now - it["dt"]).total_seconds() / 3600
        score += 1.0 if age_h < 6 else (0.5 if age_h < 12 else 0)
        items.append({
            "id": hashlib.sha1(it["url"].encode("utf-8")).hexdigest()[:10],
            "title": it["title"], "url": it["url"], "source": it["source"], "lang": it["lang"],
            "ts": it["dt"].isoformat(timespec="minutes"),
            "tags": [t for t in TAGS if t in it["tags"]],
            "score": round(score, 1), "summary": truncate(it["summary"], 120),
            "also": sorted(it["sources"] - {it["source"]}),
        })
    items.sort(key=lambda x: x["ts"], reverse=True)

    # 重點新聞：分數高者優先，每個來源最多 4 則、英文最多 3 則
    top, per_src, en = [], Counter(), 0
    for it in sorted(items, key=lambda x: (x["score"], x["ts"]), reverse=True):
        if per_src[it["source"]] >= 4 or (it["lang"] == "en" and en >= 3):
            continue
        top.append(it["id"])
        per_src[it["source"]] += 1
        en += it["lang"] == "en"
        if len(top) >= top_n:
            break
    return items, top
