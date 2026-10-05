"""HTTP 與時區工具（只用 Python 標準函式庫）。"""
import gzip
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8), "Asia/Taipei")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def now_tw():
    return datetime.now(TW)


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
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url} 取得失敗：{last}")


def fetch_text(url, **kw):
    return fetch(url, **kw).decode("utf-8", errors="replace")


def fetch_json(url, **kw):
    return json.loads(fetch_text(url, **kw))
