"""財經日曆：美國／國際經濟數據、台灣官方統計、休市日、月營收截止與手動事件。"""
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta

from . import names
from .util import (TW, clean_value, et_to_tw, fetch_json, fetch_text, strip_html,
                   us_market_holidays)

NASDAQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
STAT_URL = "https://www.stat.gov.tw/News_NoticeCalendar_Future.aspx?n=3907&date={}"
TWSE_HOLIDAYS = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _event(d, time, region, title, importance, kind="econ", **extra):
    ev = {"date": d.isoformat(), "time": time, "region": region, "kind": kind,
          "title": title, "importance": importance}
    ev.update({k: v for k, v in extra.items() if v not in (None, "")})
    return ev


# ---------------------------------------------------------------- 美國／國際（Nasdaq）

def _nasdaq_rows(query_day):
    url = f"https://api.nasdaq.com/api/calendar/economicevents?date={query_day.isoformat()}"
    data = fetch_json(url, headers=NASDAQ_HEADERS)
    return ((data or {}).get("data") or {}).get("rows") or []


def _detect_offset(fetched):
    """實測 Nasdaq 查詢日期 D 會回傳 D-1 的事件。用固定星期公布的數據投票校正，
    萬一哪天 Nasdaq 修正了也不會錯位。"""
    anchors = {"initial jobless claims": 3, "mba mortgage applications": 2}  # 週四、週三
    votes = Counter()
    for qday, rows in fetched.items():
        for r in rows:
            wd = anchors.get((r.get("eventName") or "").strip().lower())
            if wd is not None and r.get("country") == "United States":
                votes[(qday.weekday() - wd) % 7] += 1
    for off, _ in votes.most_common():
        if off in (0, 1):
            return off
    return 1


def us_intl_events(start_et, end_et):
    fetched, fails = {}, []
    q = start_et
    while q <= end_et + timedelta(days=1):
        try:
            fetched[q] = _nasdaq_rows(q)
        except Exception as e:  # noqa: BLE001
            fails.append(str(e))
        q += timedelta(days=1)
    if not fetched:
        raise RuntimeError(fails[0] if fails else "沒有資料")
    offset = _detect_offset(fetched)

    groups = {}
    for qday, rows in fetched.items():
        et_day = qday - timedelta(days=offset)
        if not start_et <= et_day <= end_et:
            continue
        for r in rows:
            country = (r.get("country") or "").strip()
            name = (r.get("eventName") or "").strip()
            if country == "United States":
                zh, imp = names.us_event(name)
                region = "US"
            else:
                hit = names.intl_event(country, name)
                if not hit:
                    continue
                zh, imp = hit
                region = "INTL"
            t = (r.get("gmt") or "").strip()
            ts = None
            if re.fullmatch(r"\d{1,2}:\d{2}", t):
                tw_dt = et_to_tw(et_day, t)
                ev_date, ev_time = tw_dt.date(), tw_dt.strftime("%H:%M")
                ts = tw_dt.isoformat(timespec="minutes")
            else:
                ev_date, ev_time = et_day, ""
            key = (ev_date, ev_time, region, zh)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "ev": _event(ev_date, ev_time, region, zh, imp, title_en=name,
                                 country=country if region == "INTL" else None, ts=ts),
                    "rows": [],
                }
            g["rows"].append(tuple(clean_value(r.get(k))
                                   for k in ("actual", "consensus", "previous")))

    out = []
    for g in groups.values():
        ev = g["ev"]
        # 同名多列（例如 CPI 月增與年增）合併為 "0.4% / 3.4%"
        for i, fld in enumerate(("actual", "forecast", "previous")):
            vals = [row[i] for row in g["rows"]]
            if any(vals):
                ev[fld] = " / ".join(v or "–" for v in vals)
        out.append(ev)
    return out


def _ff_events():
    """備援：ForexFactory 本週美國數據（只有本週、沒有公布值）。"""
    out = []
    for r in fetch_json(FF_URL):
        if r.get("country") != "USD" or r.get("impact") not in ("High", "Medium"):
            continue
        tw_dt = datetime.fromisoformat(r["date"]).astimezone(TW)
        base = re.sub(r"\s+[mqy]/[mqy]$", "", r.get("title") or "")
        zh, _ = names.us_event(base)
        out.append(_event(tw_dt.date(), tw_dt.strftime("%H:%M"), "US", zh,
                          3 if r["impact"] == "High" else 2, title_en=r.get("title"),
                          ts=tw_dt.isoformat(timespec="minutes"),
                          forecast=r.get("forecast"), previous=r.get("previous")))
    return out


# ---------------------------------------------------------------- 台灣官方統計

def _period(notice):
    """'(11508)' -> '8月'；'(114年)' -> '114年'"""
    s = (notice or "").strip().strip("()（）")
    m = re.fullmatch(r"(\d{3})(\d{2})", s)
    return f"{int(m.group(2))}月" if m else s


def _tw_releases(days):
    out, seen = [], set()
    for d in days:
        page = fetch_text(STAT_URL.format(d.isoformat()))
        m = re.search(r"VueData\s*=\s*(\{.*?\})\s*;?\s*</script>", page, re.S)
        if not m:
            continue
        for it in json.loads(m.group(1)).get("list") or []:
            td = it.get("timedatas") or {}
            dm = re.match(r"(\d{1,2})/(\d{1,2})", td.get("date") or "")
            if dm and (int(dm.group(1)), int(dm.group(2))) != (d.month, d.day):
                continue
            full = (it.get("name") or "").strip()
            short, imp = names.tw_release(full)
            period = _period(td.get("notice"))
            title = f"{short}（{period}）" if period else short
            if (d, title) in seen:
                continue
            seen.add((d, title))
            t = (td.get("time") or "").strip()
            out.append(_event(d, t if re.fullmatch(r"\d{1,2}:\d{2}", t) else "", "TW", title,
                              imp, detail=f"{it.get('DeptName', '')}｜{full}",
                              url=it.get("ContentUrl")))
    return out


def _roc_compact(s):
    """'1150925' -> date(2026, 9, 25)"""
    s = (s or "").strip()
    if not re.fullmatch(r"\d{6,7}", s):
        return None
    return date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:]))


def _tw_holidays(start, end):
    out, seen = [], set()
    for r in fetch_json(TWSE_HOLIDAYS):
        d = _roc_compact(r.get("Date"))
        if not d or not start <= d <= end or d.weekday() >= 5 or d in seen:
            continue
        name = strip_html(r.get("Name") or "")
        if "開始交易" in name or "最後交易" in name:
            continue
        seen.add(d)
        title = "台股無交易（僅辦理結算交割）" if "無交易" in name else f"台股休市：{name}"
        out.append(_event(d, "", "TW", title, 2, kind="holiday"))
    return out


def _us_holidays(start, end):
    out = []
    for y in sorted({start.year, end.year}):
        for d, name in us_market_holidays(y).items():
            if start <= d <= end:
                out.append(_event(d, "", "US", f"美股休市：{name}", 2, kind="holiday"))
    return out


def _revenue_deadlines(start, end):
    out, d = [], start
    while d <= end:
        if d.day == 10:
            prev_month = (d.month - 2) % 12 + 1
            out.append(_event(d, "", "TW", f"上市櫃公司 {prev_month} 月營收公布截止", 2,
                              kind="deadline"))
        d += timedelta(days=1)
    return out


def _manual(cfg, start, end):
    out = []
    for m in cfg.get("manual_events") or []:
        try:
            d = date.fromisoformat(m["date"])
        except (KeyError, ValueError):
            continue
        if start <= d <= end:
            out.append(_event(d, m.get("time", ""), m.get("region", "TW"), m.get("title", ""),
                              int(m.get("importance", 2)), kind="manual"))
    return out


# ---------------------------------------------------------------- 對外介面

def collect(cfg, today, errors):
    """回傳 today-2 ~ today+N-1 的事件（含已公布，供「昨夜數據」使用）。"""
    n = int(cfg.get("calendar_days", 7))
    end = today + timedelta(days=n - 1)
    events = []
    try:
        events += us_intl_events(today - timedelta(days=2), end)
    except Exception as e:  # noqa: BLE001
        errors.append(f"美國／國際經濟數據（Nasdaq）：{e}")
        try:
            events += _ff_events()
        except Exception as e2:  # noqa: BLE001
            errors.append(f"美國經濟數據備援（ForexFactory）：{e2}")

    jobs = (
        ("台灣官方統計（stat.gov.tw）", lambda: _tw_releases([today + timedelta(days=i) for i in range(n)])),
        ("台股休市日（證交所）", lambda: _tw_holidays(today, end)),
    )
    for label, job in jobs:
        try:
            events += job()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label}：{e}")

    events += _us_holidays(today, end)
    events += _revenue_deadlines(today, end)
    events += _manual(cfg, today, end)
    return events
