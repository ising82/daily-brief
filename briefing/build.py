"""組合所有資料，輸出 docs/data/latest.json、latest.js 與每日封存。"""
import json
from datetime import timedelta
from pathlib import Path

from . import earnings, econ, markets, news
from .util import now_tw, weekday_zh

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
ARCHIVE = DATA / "archive"
KEEP_DAYS = 60


def load_config():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def load_latest():
    with open(DATA / "latest.json", encoding="utf-8") as f:
        return json.load(f)


def _write(path, obj, var=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if var:  # 用 <script> 載入的版本，連 file:// 直接開網頁也能看
        text = f"window.{var}={text};\n"
    path.write_text(text, encoding="utf-8")


def _update_index():
    files = sorted(ARCHIVE.glob("????-??-??.js"), reverse=True)
    for old in files[KEEP_DAYS:]:
        old.unlink()
    _write(DATA / "archive-index.js", [p.stem for p in files[:KEEP_DAYS]], var="BRIEF_INDEX")


def _sort_key(e):
    # 同一天：沒有時間的（休市、截止日）在前，其餘依時間、重要度
    return (e["date"], 1 if e.get("time") else 0, e.get("time", ""), -e["importance"], e["region"])


def build(site_url=""):
    cfg = load_config()
    now = now_tw()
    today = now.date()
    errors = []

    events = econ.collect(cfg, today, errors)
    us_events, us_results = earnings.us_earnings(cfg, today, errors)
    tw_events = earnings.tw_conferences(cfg, today, errors)
    mkts = markets.collect(cfg, errors)
    items, top_ids = news.collect(cfg, now, errors)

    n = int(cfg.get("calendar_days", 7))
    start_s, end_s = today.isoformat(), (today + timedelta(days=n - 1)).isoformat()
    upcoming = sorted((e for e in events + us_events + tw_events if start_s <= e["date"] <= end_s),
                      key=_sort_key)

    # 昨夜已公布（過去 30 小時、有公布值、重要度 ≥ 2）
    since = (now - timedelta(hours=30)).isoformat(timespec="minutes")
    now_s = now.isoformat(timespec="minutes")
    released = sorted((e for e in events
                       if e.get("actual") and e.get("ts") and e["importance"] >= 2
                       and since <= e["ts"] <= now_s), key=lambda e: e["ts"])

    days = [{"date": (today + timedelta(days=i)).isoformat(),
             "weekday": weekday_zh(today + timedelta(days=i))} for i in range(n)]
    data = {
        "version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "weekday": weekday_zh(today),
        "site_url": site_url,
        "days": days,
        "markets": mkts,
        "events": upcoming,
        "released": released,
        "earnings_results": us_results[:20],
        "news": items,
        "top_news": top_ids,
        "errors": errors,
    }
    _write(DATA / "latest.json", data)
    _write(DATA / "latest.js", data, var="BRIEF")
    _write(ARCHIVE / f"{today.isoformat()}.js", data, var="BRIEF")
    _update_index()
    return data
