"""共用工具：時區、HTTP、字串與假日計算（只用 Python 標準函式庫）。"""
import gzip
import html
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

TW = timezone(timedelta(hours=8), "Asia/Taipei")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
WEEKDAYS = "一二三四五六日"


def now_tw():
    return datetime.now(TW)


# ---------------------------------------------------------------- HTTP

def fetch(url, data=None, headers=None, timeout=25, retries=2):
    """GET（data 不為 None 時改 POST），回傳 bytes；失敗自動重試。"""
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    body = data.encode("utf-8") if isinstance(data, str) else data
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as e:  # noqa: BLE001 — 網路錯誤種類很多，一律重試
            last = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url} 取得失敗：{last}")


def fetch_text(url, **kw):
    return fetch(url, **kw).decode("utf-8", errors="replace")


def fetch_json(url, **kw):
    return json.loads(fetch_text(url, **kw))


# ---------------------------------------------------------------- 字串

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(s):
    """去除 HTML 標籤；鉅亨的內容會雙重跳脫，所以 unescape 兩次。"""
    if not s:
        return ""
    s = html.unescape(html.unescape(s))
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", s).strip()


def truncate(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def clean_value(v):
    """Nasdaq 的數值欄位可能是 '&nbsp;'、'N/A' 或空白。"""
    v = strip_html(v or "")
    return "" if v in ("N/A", "-", "--") else v


def parse_money(s):
    """'$440,539,251,000' -> 440539251000.0；無法解析回傳 0。"""
    try:
        return float(re.sub(r"[^\d.]", "", s or "") or 0)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- 日期

def md(d):
    return f"{d.month}/{d.day}"


def weekday_zh(d):
    return WEEKDAYS[d.weekday()]


def roc_to_date(s):
    """'115/09/14' -> date(2026, 9, 14)"""
    m = re.match(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})", s or "")
    if not m:
        return None
    return date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))


def _nth_weekday(year, month, weekday, n):
    """某月第 n 個星期幾（週一=0）；n=-1 代表最後一個。"""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def et_offset(d):
    """美東時區在日期 d 的 UTC 偏移（夏令：3 月第 2 個週日 ~ 11 月第 1 個週日）。"""
    start = _nth_weekday(d.year, 3, 6, 2)
    end = _nth_weekday(d.year, 11, 6, 1)
    return timedelta(hours=-4 if start <= d < end else -5)


def et_to_tw(d, hhmm):
    """美東日期 + 'HH:MM' -> 台北時間 datetime。"""
    h, m = (int(x) for x in hhmm.split(":"))
    et = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone(et_offset(d)))
    return et.astimezone(TW)


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return date(y, n // 31, n % 31 + 1)


def _observed(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def us_market_holidays(y):
    """紐約證交所全日休市日（依規則計算，不需每年維護）。"""
    days = {
        _nth_weekday(y, 1, 0, 3): "馬丁路德金恩紀念日",
        _nth_weekday(y, 2, 0, 3): "總統日",
        _easter(y) - timedelta(days=2): "耶穌受難日",
        _nth_weekday(y, 5, 0, -1): "陣亡將士紀念日",
        _observed(date(y, 6, 19)): "六月節",
        _observed(date(y, 7, 4)): "獨立紀念日",
        _nth_weekday(y, 9, 0, 1): "勞動節",
        _nth_weekday(y, 11, 3, 4): "感恩節",
        _observed(date(y, 12, 25)): "聖誕節",
    }
    ny = date(y, 1, 1)
    if ny.weekday() != 5:  # 元旦逢週六時 NYSE 不補假
        days[_observed(ny)] = "元旦"
    return days
