"""財報：美股（Nasdaq 財報行事曆）與台股法說會（公開資訊觀測站）。"""
import re
import unicodedata
from datetime import timedelta

from .econ import NASDAQ_HEADERS
from .util import (clean_value, fetch_json, fetch_text, parse_money, roc_to_date,
                   strip_html, us_market_holidays)

MOPS_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1"
TWSE_BASIC = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_CLOSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_CLOSE = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

SESSION = {"time-pre-market": "盤前", "time-after-hours": "盤後"}
_SUFFIX = re.compile(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|Ltd\.?|"
                     r"Limited|plc|N\.V\.|S\.A\.|Holdings?|Group|Class [A-C]|\(The\))$", re.I)


def _short_name(name):
    name = (name or "").strip()
    for _ in range(3):
        name = _SUFFIX.sub("", name).strip(" ,")
    return name


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _prev_us_session(today):
    d = today - timedelta(days=1)
    while d.weekday() >= 5 or d in us_market_holidays(d.year):
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------- 美股

def us_earnings(cfg, today, errors):
    """回傳 (未來財報事件, 上一個交易日已公布的財報結果)。"""
    c = cfg.get("us_earnings") or {}
    min_cap = float(c.get("min_market_cap_usd", 1e10))
    major = float(c.get("major_market_cap_usd", 1e11))
    watch = {s.upper() for s in c.get("watchlist") or []}
    n = int(cfg.get("calendar_days", 7))

    last_session = _prev_us_session(today)
    us_days = {today - timedelta(days=1) + timedelta(days=i) for i in range(n)} | {last_session}
    events, results = [], []
    for d in sorted(us_days):
        if d.weekday() >= 5:
            continue
        try:
            data = fetch_json(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}",
                              headers=NASDAQ_HEADERS)
        except Exception as e:  # noqa: BLE001
            errors.append(f"美股財報 {d}：{e}")
            continue
        for r in ((data or {}).get("data") or {}).get("rows") or []:
            sym = (r.get("symbol") or "").upper()
            cap = parse_money(r.get("marketCap"))
            if cap < min_cap and sym not in watch:
                continue
            imp = 3 if (sym in watch or cap >= major) else (2 if cap >= min_cap * 3 else 1)
            session = SESSION.get(r.get("time"), "時間未定")
            name = _short_name(r.get("name"))
            item = {
                "symbol": sym, "name": name, "session": session, "us_date": d.isoformat(),
                "mcap": cap, "importance": imp, "watch": sym in watch,
                "forecast": clean_value(r.get("epsForecast")),
                "eps": clean_value(r.get("eps")),
                "surprise": clean_value(r.get("surprise")),
            }
            if d == last_session and item["eps"]:
                results.append(item)
            # 盤後公布 = 台灣隔天清晨，放在台灣日期
            tw_day = d + timedelta(days=1) if session == "盤後" else d
            if tw_day >= today:
                ev = {"date": tw_day.isoformat(), "time": "", "region": "US",
                      "kind": "earnings", "title": f"{name} 財報"}
                ev.update({k: v for k, v in item.items() if v not in ("", None)})
                events.append(ev)
    results.sort(key=lambda x: -x["mcap"])
    return events, results


# ---------------------------------------------------------------- 台股法說會

def _tw_market_caps(errors):
    caps = {}
    try:
        shares = {r.get("公司代號"): _num(r.get("已發行普通股數或TDR原股發行股數"))
                  for r in fetch_json(TWSE_BASIC, timeout=60)}
        for r in fetch_json(TWSE_CLOSE, timeout=60):
            px = _num(r.get("ClosingPrice"))
            if px and shares.get(r.get("Code")):
                caps[r["Code"]] = shares[r["Code"]] * px
    except Exception as e:  # noqa: BLE001
        errors.append(f"上市公司市值（證交所）：{e}")
    try:
        for r in fetch_json(TPEX_CLOSE, timeout=60):
            px, sh = _num(r.get("Close")), _num(r.get("Capitals"))
            if px and sh:
                caps[r.get("SecuritiesCompanyCode")] = px * sh
    except Exception as e:  # noqa: BLE001
        errors.append(f"上櫃公司市值（櫃買中心）：{e}")
    return caps


def _mops_rows(typek, year, month):
    body = (f"encodeURIComponent=1&step=1&firstin=true&off=1&TYPEK={typek}"
            f"&year={year - 1911}&month={month:02d}&co_id=")
    page = fetch_text(MOPS_URL, data=body, timeout=60,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    rows = []
    for tr in re.findall(r"<tr class='(?:even|odd)'[^>]*>(.*?)</tr>", page, re.S):
        cells = [unicodedata.normalize("NFKC", strip_html(c))
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 6:
            rows.append(cells)
    return rows


def tw_conferences(cfg, today, errors):
    c = cfg.get("tw_earnings") or {}
    min_cap = float(c.get("min_market_cap_twd", 3e10))
    major = float(c.get("major_market_cap_twd", 3e11))
    watch = set(c.get("watchlist") or [])
    n = int(cfg.get("calendar_days", 7))
    end = today + timedelta(days=n - 1)
    months = sorted({(d.year, d.month) for d in (today + timedelta(days=i) for i in range(n))})

    caps = _tw_market_caps(errors)
    events, seen = [], set()
    for typek, market in (("sii", "上市"), ("otc", "上櫃")):
        for y, m in months:
            try:
                rows = _mops_rows(typek, y, m)
            except Exception as e:  # noqa: BLE001
                errors.append(f"法說會（公開資訊觀測站 {market} {m}月）：{e}")
                continue
            for code, name, when, t, place, summary, *_ in rows:
                start = roc_to_date(when)
                if not start or not today <= start <= end or (code, start) in seen:
                    continue
                seen.add((code, start))
                cap = caps.get(code, 0.0)
                imp = 3 if (code in watch or cap >= major) else (2 if cap >= min_cap else 1)
                multi = "至" in when
                if multi:
                    imp = min(imp, 2)
                detail = " ｜ ".join(x for x in (summary, place) if x and x != "無")
                ev = {"date": start.isoformat(),
                      "time": t if re.fullmatch(r"\d{1,2}:\d{2}", t) else "",
                      "region": "TW", "kind": "earnings",
                      "title": f"{name} 法說會" + ("（多日）" if multi else ""),
                      "symbol": code, "name": name, "market": market,
                      "mcap": cap, "importance": imp, "watch": code in watch,
                      "detail": detail[:120]}
                if multi:
                    ev["range"] = when
                events.append(ev)
    return events
