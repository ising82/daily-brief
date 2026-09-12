"""經濟事件的中文名稱與重要度（3=重大、2=重要、1=次要，網頁預設隱藏 1）。"""
import re

# 美國：Nasdaq 行事曆的英文名稱（小寫）→ (中文, 重要度)
US_EVENTS = {
    "fed interest rate decision": ("聯準會利率決議", 3),
    "fomc statement": ("FOMC 政策聲明", 3),
    "fomc press conference": ("FOMC 記者會", 3),
    "fomc economic projections": ("FOMC 經濟預測（點陣圖）", 3),
    "fomc meeting minutes": ("FOMC 會議紀要", 3),
    "nonfarm payrolls": ("非農就業人數", 3),
    "unemployment rate": ("失業率", 3),
    "cpi": ("消費者物價指數 CPI", 3),
    "core cpi": ("核心 CPI", 3),
    "pce price index": ("PCE 物價指數", 3),
    "core pce price index": ("核心 PCE 物價指數", 3),
    "gdp": ("GDP", 3),
    "retail sales": ("零售銷售", 3),
    "ism manufacturing pmi": ("ISM 製造業 PMI", 3),
    "ism non-manufacturing pmi": ("ISM 服務業 PMI", 3),
    "ism services pmi": ("ISM 服務業 PMI", 3),
    "ppi": ("生產者物價指數 PPI", 2),
    "core ppi": ("核心 PPI", 2),
    "core retail sales": ("核心零售銷售", 2),
    "average hourly earnings": ("平均時薪", 2),
    "jolts job openings": ("JOLTS 職缺", 2),
    "adp nonfarm employment change": ("ADP 就業人數", 2),
    "initial jobless claims": ("初領失業救濟金", 2),
    "michigan consumer sentiment": ("密大消費者信心", 2),
    "michigan 1-year inflation expectations": ("密大 1 年通膨預期", 2),
    "cb consumer confidence": ("諮商會消費者信心", 2),
    "durable goods orders": ("耐久財訂單", 2),
    "housing starts": ("新屋開工", 2),
    "existing home sales": ("成屋銷售", 2),
    "new home sales": ("新屋銷售", 2),
    "industrial production": ("工業生產", 2),
    "philadelphia fed manufacturing index": ("費城聯準會製造業指數", 2),
    "ny empire state manufacturing index": ("紐約州製造業指數", 2),
    "s&p global manufacturing pmi": ("S&P 製造業 PMI", 2),
    "s&p global services pmi": ("S&P 服務業 PMI", 2),
    "personal income": ("個人所得", 2),
    "personal spending": ("個人支出", 2),
    "crude oil inventories": ("EIA 原油庫存", 2),
    "beige book": ("聯準會褐皮書", 2),
    "gdp price index": ("GDP 物價指數", 2),
    "continuing jobless claims": ("續領失業救濟金", 1),
    "core durable goods orders": ("核心耐久財訂單", 1),
    "building permits": ("營建許可", 1),
    "pending home sales": ("成屋待完成銷售", 1),
    "import price index": ("進口物價", 1),
    "export price index": ("出口物價", 1),
    "trade balance": ("貿易收支", 1),
    "business inventories": ("企業庫存", 1),
    "nahb housing market index": ("NAHB 房市指數", 1),
    "chicago pmi": ("芝加哥 PMI", 1),
    "nonfarm productivity": ("非農生產力", 1),
    "unit labor costs": ("單位勞動成本", 1),
    "private nonfarm payrolls": ("民間非農就業", 1),
    "participation rate": ("勞動參與率", 1),
    "u6 unemployment rate": ("U6 失業率", 1),
    "retail control": ("零售銷售控制組", 1),
    "atlanta fed gdpnow": ("亞特蘭大聯準會 GDPNow", 1),
    "10-year note auction": ("10 年期公債標售", 1),
    "30-year bond auction": ("30 年期公債標售", 1),
}

# 名稱不固定的事件用正規表示式
US_PATTERNS = [
    (r"fed chair .*speaks|powell speaks", ("聯準會主席談話", 3)),
    (r"^fomc member .* speaks|^fed .* speaks", ("聯準會官員談話", 1)),
    (r"interest rate projection", ("FOMC 利率預測", 1)),
]

# 其他國家：只收錄對台股／美股影響大的項目，其餘略過
INTL_EVENTS = {
    ("china", "gdp"): ("中國 GDP", 3),
    ("china", "cpi"): ("中國 CPI", 2),
    ("china", "ppi"): ("中國 PPI", 2),
    ("china", "industrial production"): ("中國 工業生產", 2),
    ("china", "retail sales"): ("中國 零售銷售", 2),
    ("china", "exports"): ("中國 出口", 2),
    ("china", "trade balance"): ("中國 貿易收支", 2),
    ("china", "manufacturing pmi"): ("中國 官方製造業 PMI", 2),
    ("china", "caixin manufacturing pmi"): ("中國 財新製造業 PMI", 2),
    ("china", "loan prime rate 1y"): ("中國 1 年期 LPR", 2),
    ("japan", "boj interest rate decision"): ("日本央行利率決議", 3),
    ("japan", "interest rate decision"): ("日本央行利率決議", 3),
    ("euro zone", "ecb interest rate decision"): ("歐洲央行利率決議", 3),
    ("euro zone", "deposit facility rate"): ("歐洲央行存款利率", 3),
    ("euro zone", "ecb press conference"): ("歐洲央行記者會", 2),
    ("euro zone", "cpi"): ("歐元區 CPI", 2),
    ("united kingdom", "boe interest rate decision"): ("英國央行利率決議", 3),
    ("united kingdom", "interest rate decision"): ("英國央行利率決議", 3),
    ("south korea", "exports"): ("韓國 出口", 1),
}

FLAGS = {
    "TW": "🇹🇼", "US": "🇺🇸", "China": "🇨🇳", "Japan": "🇯🇵",
    "Euro Zone": "🇪🇺", "United Kingdom": "🇬🇧", "South Korea": "🇰🇷",
}


def us_event(name):
    key = (name or "").strip().lower()
    if key in US_EVENTS:
        return US_EVENTS[key]
    for pat, val in US_PATTERNS:
        if re.search(pat, key):
            return val
    return (name.strip(), 1)


def intl_event(country, name):
    """回傳 (中文, 重要度)；不在清單內回傳 None（略過）。"""
    return INTL_EVENTS.get(((country or "").lower(), (name or "").strip().lower()))


# 台灣官方統計（stat.gov.tw 預告發布時間表）：依關鍵字判斷，順序有意義
TW_RULES = [
    (("失業率",), "失業率", 3),
    (("外銷訂單",), "外銷訂單", 3),
    (("消費者物價",), "CPI 消費者物價", 3),
    (("經濟成長", "國民所得", "國內生產毛額"), "GDP／經濟成長率", 3),
    (("進出口貿易", "海關進出口"), "進出口貿易（出口）", 3),
    (("景氣",), "景氣對策信號", 3),
    (("工業生產",), "工業生產指數", 2),
    (("薪資",), "薪資統計", 2),
    (("批發", "零售"), "批發零售餐飲營業額", 2),
    (("貨幣總計數", "金融統計", "貨幣供給"), "貨幣總計數 M1B／M2", 2),
    (("外匯存底", "外匯準備"), "外匯存底", 2),
    (("躉售物價", "生產者物價", "進口物價", "出口物價"), "物價指數（PPI／進出口）", 2),
    (("製造業",), None, 1),
]


def tw_release(name):
    """回傳 (短名稱, 重要度)。"""
    for keys, short, imp in TW_RULES:
        if any(k in name for k in keys):
            return (short or name, imp)
    return (name, 1)
