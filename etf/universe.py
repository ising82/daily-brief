"""台灣 ETF 清單與分類。

清單來源：證交所 ISIN 名冊（上市 strMode=2、上櫃 strMode=4，含上市日），
備援：證交所／櫃買中心每日收盤 OpenAPI（只有代號與名稱）。
分類：依證交所代號末碼規則（A 主動式、B 債券、L 槓桿、R 反向、U 期貨）加上名稱關鍵字，
屬啟發式判斷，網頁上有說明。
"""
import re

from .util import fetch, fetch_json

ISIN = "https://isin.twse.com.tw/isin/C_public.jsp?strMode={}"
TWSE_CLOSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_CLOSE = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

CODE = re.compile(r"^00\d{2,4}[A-Z]?$")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")

MARKETS = (("2", "上市", ".TW"), ("4", "上櫃", ".TWO"))


def _cells(row):
    return [_TAG.sub("", c).replace("\xa0", " ").replace("&nbsp;", " ").strip() for c in _TD.findall(row)]


def _isin(mode, market):
    """ISIN 名冊欄位：有價證券代號及名稱、ISIN、上市日、市場別、產業別、CFICode、備註。"""
    html = fetch(ISIN.format(mode), timeout=60).decode("cp950", errors="replace")
    out = []
    for row in _TR.findall(html):
        cells = _cells(row)
        if len(cells) < 6:
            continue
        parts = re.split(r"[　\s]+", cells[0], maxsplit=1)
        if len(parts) != 2 or not CODE.match(parts[0]):
            continue
        cfi = cells[5]
        if cfi and not cfi.upper().startswith("CE"):  # CE = 集合投資／ETF
            continue
        listed = re.sub(r"[/.]", "-", cells[2])
        out.append({"code": parts[0], "name": parts[1], "market": market,
                    "listed": listed if re.match(r"^\d{4}-\d{2}-\d{2}$", listed) else ""})
    if not out:
        raise ValueError("名冊解析不到任何 ETF")
    return out


def _fallback(market):
    if market == "上市":
        rows = fetch_json(TWSE_CLOSE, timeout=60)
        pairs = [(r.get("Code"), r.get("Name")) for r in rows]
    else:
        rows = fetch_json(TPEX_CLOSE, timeout=60)
        pairs = [(r.get("SecuritiesCompanyCode"), r.get("CompanyName")) for r in rows]
    return [{"code": c, "name": (n or "").strip(), "market": market, "listed": ""}
            for c, n in pairs if c and CODE.match(c)]


def collect(errors):
    """回傳 [{code, name, market, listed, yahoo, active, cat, region}]，依代號排序。"""
    seen = {}
    for mode, market, suffix in MARKETS:
        try:
            rows = _isin(mode, market)
        except Exception as e:  # noqa: BLE001
            errors.append(f"ETF 名冊（{market}）：{e}，改用每日收盤清單")
            try:
                rows = _fallback(market)
            except Exception as e2:  # noqa: BLE001
                errors.append(f"ETF 清單備援（{market}）：{e2}")
                rows = []
        for r in rows:
            if r["code"] in seen:
                continue
            r["yahoo"] = r["code"] + suffix
            r.update(classify(r["code"], r["name"]))
            seen[r["code"]] = r
    return [seen[k] for k in sorted(seen)]


# ---------------------------------------------------------------- 分類

_OVERSEAS = ("美國", "美股", "標普", "S&P", "SP500", "那斯達克", "納斯達克", "NASDAQ", "道瓊", "費城", "費半",
             "日本", "日經", "東證", "中國", "中証", "中證", "上證", "滬深", "深証", "深證", "恒生", "恆生", "香港",
             "印度", "越南", "韓國", "歐洲", "歐元", "德國", "英國", "法國", "全球", "世界", "亞洲", "亞太",
             "新興", "東協", "拉美", "巴西", "泰國", "印尼", "馬來", "菲律賓", "澳洲", "加拿大", "FANG", "MSCI世界",
             "已開發", "國際", "海外", "美元", "黃金", "原油", "白銀", "比特")
_CAP = ("台灣50", "臺灣50", "台50", "臺50", "中型100", "MSCI台灣", "MSCI臺灣", "臺灣加權", "台灣加權", "大盤",
        "臺灣市值", "台灣市值", "臺灣領袖", "台灣領袖")
_DIV = ("高股息", "高息", "優息", "股利", "股息", "配息", "收益", "息收", "月配", "季配")
_COMMODITY = ("黃金", "原油", "白銀", "期貨", "商品", "天然氣", "布蘭特", "比特幣", "以太")


def classify(code, name):
    tail = code[-1]
    n = name.replace(" ", "")
    active = tail == "A" or "主動" in n
    lev = tail in "LR" or any(k in n for k in ("正2", "反1", "正二", "反一", "槓桿", "反向", "2X", "-1X"))
    bond = tail == "B" or ("債" in n and "可轉" not in n)
    commodity = tail == "U" or any(k in n for k in _COMMODITY)
    overseas = any(k in n for k in _OVERSEAS)
    taiwan = any(k in n for k in ("台灣", "臺灣", "台股", "臺股", "台", "臺"))

    if lev:
        cat = "槓桿/反向"
    elif bond:
        cat = "債券"
    elif commodity:
        cat = "商品/期貨"
    elif any(k in n for k in _DIV):
        cat = "高股息"
    elif any(k in n for k in _CAP):
        cat = "市值型"
    elif overseas and not (taiwan and not any(k in n for k in ("全球", "世界", "國際"))):
        cat = "海外股票"
    elif any(k in n for k in ("多重資產", "多元資產", "平衡", "資產配置")):
        cat = "多重資產/其他"
    else:
        cat = "主題/產業"
    region = "海外" if (cat in ("海外股票", "商品/期貨") or (overseas and not taiwan)) else "台灣"
    if cat == "債券":
        region = "台灣" if any(k in n for k in ("台灣", "臺灣", "台債", "臺債")) else "海外"
    return {"active": active, "cat": cat, "region": region}
