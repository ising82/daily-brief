"""推播晨報：Telegram（HTML 格式）與 LINE Messaging API（純文字）。

環境變數（在 GitHub → Settings → Secrets 設定，沒設定的管道會自動略過）：
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID（多個用逗號分隔）
  LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID（多個用逗號分隔）
"""
import html
import json
import os
import urllib.error
import urllib.request
from datetime import date

from .names import FLAGS

TG_LIMIT = 3900     # Telegram 上限 4096 字
LINE_LIMIT = 4900   # LINE 上限 5000 字


class _Fmt:
    def __init__(self, rich):
        self.rich = rich

    def esc(self, s):
        return html.escape(str(s), quote=False) if self.rich else str(s)

    def b(self, s):
        return f"<b>{self.esc(s)}</b>" if self.rich else f"【{s}】"

    def a(self, s, url):
        if self.rich and url:
            return f'<a href="{html.escape(url)}">{self.esc(s)}</a>'
        return str(s)


def _flag(e):
    if e.get("region") == "INTL":
        return FLAGS.get(e.get("country"), "🌐")
    return FLAGS.get(e.get("region"), "")


def _md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}（{'一二三四五六日'[d.weekday()]}）"


def _market_line(m):
    price = m["price"]
    if m.get("unit") == "%":
        text = f"{price:.2f}%"
        if "change" in m:
            ch = m["change"] * 100
            text += f" {'▲' if ch > 0 else '▼' if ch < 0 else '－'}{abs(ch):.1f}bp"
        return f"{m['name']} {text}"
    text = f"{price:,.2f}"
    if "pct" in m:
        p = m["pct"]
        text += f" {'▲' if p > 0 else '▼' if p < 0 else '－'}{abs(p):.2f}%"
    return f"{m['name']} {text}"


def _values(e):
    parts = []
    if e.get("forecast"):
        parts.append(f"預期 {e['forecast']}")
    if e.get("previous"):
        parts.append(f"前值 {e['previous']}")
    return "｜".join(parts)


def compose(data, rich=True, news_count=8, cal_days=3, max_cal_lines=18):
    f = _Fmt(rich)
    site = (data.get("site_url") or "").rstrip("/")
    L = [f.b(f"☀️ 財經晨報｜{_md(data['date'])}"), ""]

    if data.get("markets"):
        L.append(f.b("📈 市場行情"))
        L += [f.esc(_market_line(m)) for m in data["markets"]]
        L.append("")

    rel = [e for e in data.get("released") or [] if e["importance"] >= 2][:8]
    if rel:
        L.append(f.b("📊 昨夜公布數據"))
        for e in rel:
            extra = _values(e)
            L.append(f.esc(f"{_flag(e)} {e['title']}：{e['actual']}" + (f"（{extra}）" if extra else "")))
        L.append("")

    res = [r for r in data.get("earnings_results") or [] if r["importance"] >= 2][:6]
    if res:
        L.append(f.b("💼 昨夜財報"))
        for r in res:
            s = f"{r['symbol']} {r['name']}：EPS {r['eps']}"
            if r.get("forecast"):
                s += f"（預期 {r['forecast']}）"
            if r.get("surprise"):
                try:
                    s += f" 驚喜 {float(r['surprise']):+.1f}%"
                except ValueError:
                    pass
            L.append(f.esc(s))
        L.append("")

    days = [d["date"] for d in (data.get("days") or [])][:cal_days]
    cal, count = [], 0
    for iso in days:
        todays = [e for e in data.get("events") or []
                  if e["date"] == iso and (e["importance"] >= 3 or (iso == data["date"] and e["importance"] >= 2))]
        if not todays or count >= max_cal_lines:
            continue
        cal.append(f.esc(("今天 " if iso == data["date"] else "") + _md(iso)))
        for e in todays[: max_cal_lines - count]:
            t = f"{e['time']} " if e.get("time") else ""
            extra = f"（{e['session']}）" if e.get("session") else ""
            cal.append(f.esc(f"  {_flag(e)} {t}{e['title']}{extra}"))
            count += 1
    if cal:
        L.append(f.b(f"🗓 未來 {cal_days} 天重點"))
        L += cal
        L.append("")

    by_id = {n["id"]: n for n in data.get("news") or []}
    top = [by_id[i] for i in data.get("top_news") or [] if i in by_id][:news_count]
    if top:
        L.append(f.b("📰 24 小時重點新聞"))
        for i, n in enumerate(top, 1):
            L.append(f"{i}. {f.a(n['title'], n['url'])}（{f.esc(n['source'])}）")
        L.append("")

    if data.get("errors"):
        L.append(f.esc(f"⚠️ 有 {len(data['errors'])} 個資料來源暫時失敗，詳見網站"))
    if site:
        L.append(f.a("🔗 完整晨報（財經日曆）", site + "/") if rich else f"🔗 財經日曆：{site}/")
        L.append(f.a("🔗 24 小時快訊", site + "/news.html") if rich else f"🔗 24 小時快訊：{site}/news.html")
    return "\n".join(L).strip()


def _fit(data, rich, limit, news_count=8, cal_days=3):
    lines = 18
    msg = compose(data, rich, news_count, cal_days, lines)
    while len(msg) > limit and (news_count > 3 or lines > 6):
        news_count = max(3, news_count - 1)
        lines = max(6, lines - 2)
        msg = compose(data, rich, news_count, cal_days, lines)
    return msg[:limit]


def _post(url, payload, headers=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, f"連線失敗：{e.reason}"


def _ids(var):
    return [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]


def send(data, cfg=None, dry_run=False):
    """發送到所有已設定的管道；全部成功（或沒有設定任何管道）回傳 True。"""
    opts = (cfg or {}).get("notify") or {}
    fit = {"news_count": int(opts.get("news_count", 8)), "cal_days": int(opts.get("calendar_days", 3))}
    tg_token, line_token = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    tg_chats, line_users = _ids("TELEGRAM_CHAT_ID"), _ids("LINE_USER_ID")
    ok = True

    if dry_run or not ((tg_token and tg_chats) or (line_token and line_users)):
        print("（未設定推播管道或為 --dry-run，以下為訊息預覽）\n")
        print(_fit(data, False, LINE_LIMIT, **fit))
        return True

    if tg_token and tg_chats:
        msg = _fit(data, True, TG_LIMIT, **fit)
        for chat in tg_chats:
            code, body = _post(f"https://api.telegram.org/bot{tg_token}/sendMessage", {
                "chat_id": chat, "text": msg, "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            })
            if code == 200:
                print(f"Telegram ✓ 已送出（chat {chat}）")
            else:
                ok = False
                print(f"Telegram ✗ chat {chat}：HTTP {code} {body[:300]}")

    if line_token and line_users:
        msg = _fit(data, False, LINE_LIMIT, **fit)
        for uid in line_users:
            code, body = _post("https://api.line.me/v2/bot/message/push",
                               {"to": uid, "messages": [{"type": "text", "text": msg}]},
                               headers={"Authorization": f"Bearer {line_token}"})
            if code == 200:
                print(f"LINE ✓ 已送出（{uid[:6]}…）")
            else:
                ok = False
                print(f"LINE ✗ {uid[:6]}…：HTTP {code} {body[:300]}")
    return ok
