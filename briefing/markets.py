"""市場行情：Yahoo Finance 日線（台股、美股指數、匯率、殖利率、原物料）。"""
import urllib.parse
from datetime import datetime, timedelta, timezone

from .util import fetch_json

HOSTS = ("query1", "query2")
CHART = "https://{}.finance.yahoo.com/v8/finance/chart/{}?range=5d&interval=1d"


def _chart(symbol):
    last = None
    for host in HOSTS:
        try:
            data = fetch_json(CHART.format(host, urllib.parse.quote(symbol, safe="")), retries=1)
            return data["chart"]["result"][0]
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(last)


def _quote(symbol):
    res = _chart(symbol)
    ts = res.get("timestamp") or []
    closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if not pts:
        raise ValueError("沒有報價")
    last_t, price = pts[-1]
    prev = pts[-2][1] if len(pts) > 1 else None
    offset = (res.get("meta") or {}).get("gmtoffset") or 0
    day = (datetime.fromtimestamp(last_t, timezone.utc) + timedelta(seconds=offset)).date()
    return price, prev, day


def collect(cfg, errors):
    out = []
    for m in cfg.get("markets") or []:
        try:
            price, prev, day = _quote(m["symbol"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"行情 {m.get('name', m.get('symbol'))}：{e}")
            continue
        item = {"symbol": m["symbol"], "name": m.get("name", m["symbol"]),
                "group": m.get("group", ""), "unit": m.get("unit", ""),
                "price": round(price, 4), "date": day.isoformat()}
        if prev:
            item["change"] = round(price - prev, 4)
            item["pct"] = round((price - prev) / prev * 100, 2)
        out.append(item)
    return out
