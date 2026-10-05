"""Yahoo Finance 日線（含配息、分割事件）。

用 period1/period2 指定起訖（用 range=max 時 Yahoo 會把長歷史自動降成週線／月線，period 參數才會給完整日線）。
回傳 {"rows": {日期: [收盤, 成交量]}, "div": {除息日: 每單位配息}, "splits": [日期]}。
"""
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from briefing.util import fetch_json

HOSTS = ("query1", "query2")
CHART = ("https://{}.finance.yahoo.com/v8/finance/chart/{}"
         "?period1={}&period2={}&interval=1d&events=div%7Csplit&includePrePost=false")
EPOCH_2000 = 946684800   # 台灣第一檔 ETF（0050）2003 年上市，從 2000 年起抓即可


def _result(symbol, rng):
    p1 = EPOCH_2000 if rng == "max" else int(time.time()) - 40 * 86400
    p2 = int(time.time()) + 86400
    last = None
    for host in HOSTS:
        try:
            data = fetch_json(CHART.format(host, urllib.parse.quote(symbol, safe=""), p1, p2), retries=0, timeout=20)
            res = (data.get("chart") or {}).get("result") or []
            if not res:
                raise ValueError((data.get("chart") or {}).get("error") or "沒有資料")
            return res[0]
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(last)


def fetch_history(symbol, rng="max"):
    res = _result(symbol, rng)
    offset = (res.get("meta") or {}).get("gmtoffset") or 28800
    tz = timezone(timedelta(seconds=offset))

    def day(ts):
        return datetime.fromtimestamp(int(ts), tz).date().isoformat()

    ts = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    rows = {}
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None or c <= 0:
            continue
        v = vols[i] if i < len(vols) else None
        rows[day(t)] = [float(c), int(v or 0)]

    today = datetime.now(tz)
    if today.hour < 14 and rows and max(rows) == today.date().isoformat():
        del rows[today.date().isoformat()]        # 盤中執行：當日尚未收盤，不採用

    events = res.get("events") or {}
    div = {}
    for d in (events.get("dividends") or {}).values():
        amt = d.get("amount")
        if amt and amt > 0 and d.get("date"):
            div[day(d["date"])] = float(amt)
    splits = sorted(day(s["date"]) for s in (events.get("splits") or {}).values() if s.get("date"))
    return {"rows": rows, "div": div, "splits": splits}
