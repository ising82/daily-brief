# ☀️ 每日財經晨報

每天早上自動抓資料、更新網站，並推播晨報到 **Telegram**／**LINE**。

- **第一頁｜財經日曆**：未來 7 天台灣、美國（與主要國際）經濟數據、央行會議、休市日、月營收截止日、美股重要財報、台股法說會；附「昨夜回顧」（已公布數據與財報 EPS）與隔夜行情。
- **第二頁｜24 小時快訊**：過去 24 小時財經新聞（鉅亨網、中央社、經濟日報、Yahoo 股市、CNBC、WSJ、MarketWatch），自動去重、分類（台股／美股／總經／科技／外匯原物料）並挑出重點新聞。
- **推播**：行情、昨夜數據、昨夜財報、未來 3 天重點、8 則重點新聞，附網站連結。
- **封存**：保留最近 60 天，網站右上角可切換日期。

全部跑在 GitHub 上：**GitHub Actions** 每天排程執行 → Python（只用標準函式庫，免安裝套件）產生資料 → **GitHub Pages** 發佈網站 → 網站上線後才推播。免費、不需要自己的伺服器或電腦開著。

---

## 設定步驟（約 15 分鐘）

### 1. 建立 GitHub repository
1. 登入 GitHub → 右上角 **＋ → New repository**，名稱例如 `daily-brief`，選 **Public**（免費帳號的 GitHub Pages 需要公開 repo）。
2. 把這個資料夾的所有檔案上傳（網頁上 **Add file → Upload files** 拖曳即可，`.github` 資料夾也要上傳）。

### 2. 開啟 GitHub Pages
repo 的 **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。

### 3. Telegram 推播
1. 在 Telegram 搜尋 **@BotFather** → 傳 `/newbot` → 依指示命名，取得 **Bot Token**（像 `123456:ABC-...`）。
2. 搜尋你剛建立的 bot，按 **Start** 並隨便傳一句話給它。
3. 用瀏覽器打開 `https://api.telegram.org/bot<你的Token>/getUpdates`，找到 `"chat":{"id":123456789` 這串數字，就是 **Chat ID**。（想推到群組：把 bot 加進群組後在群組發言，群組的 ID 會是負數。）
4. repo 的 **Settings → Secrets and variables → Actions → New repository secret**，新增：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`（多個用逗號分隔）

### 4. LINE 推播（選用）
LINE Notify 已於 2025/3/31 停止服務，改用 **LINE Messaging API**：
1. 到 [LINE Developers](https://developers.line.biz/console/) 建立 Provider → 建立 **Messaging API channel**（會同時建立一個 LINE 官方帳號）。
2. 在 channel 的 **Messaging API** 分頁最下方發行 **Channel access token (long-lived)**。
3. 在 **Basic settings** 分頁最下方找到 **Your user ID**（`U` 開頭）。
4. 用手機掃 Messaging API 分頁的 QR code，把官方帳號加為好友。
5. 新增 secrets：`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_USER_ID`。

> 免費方案每月推播則數有上限，一天一則通常足夠；超過上限當月會停止推送。

### 5. 第一次執行
repo 的 **Actions** 分頁 →（第一次可能要按 *I understand my workflows, go ahead and enable them*）→ 左側 **每日財經晨報** → **Run workflow**。
約 2–4 分鐘後：
- 網站：`https://<你的帳號>.github.io/<repo 名稱>/`
- Telegram／LINE 會收到第一份晨報

之後每天 **台灣時間 06:15** 自動執行（GitHub 排程通常會延遲 5–30 分鐘，約 06:30–07:00 收到）。

---

## 自訂（編輯 `config.json`）

| 設定 | 說明 |
|---|---|
| `calendar_days` | 日曆顯示天數（預設 7） |
| `us_earnings.watchlist` | 美股關注清單，一定會列出並標為重大 |
| `us_earnings.min_market_cap_usd` | 市值低於此值（預設 100 億美元）且不在清單的財報不列出 |
| `tw_earnings.watchlist` | 台股關注代號，法說會標為重大 |
| `tw_earnings.min_market_cap_twd` | 市值門檻（預設 300 億元），低於者列為次要（網頁預設隱藏） |
| `news.include_english` | 是否納入英文新聞 |
| `notify.news_count` / `notify.calendar_days` | 推播的新聞則數／日曆天數 |
| `markets` | 行情清單（Yahoo Finance 代號） |
| `manual_events` | 手動事件，例如央行理監事會、重要會議 |

**改推播時間**：編輯 `.github/workflows/daily.yml` 的 `cron`（UTC 時間，台灣時間減 8 小時）。

**央行理監事會**：日期每年公布一次，請在 `manual_events` 補上（已預填 2026/9/17）。

---

## 資料來源

| 項目 | 來源 |
|---|---|
| 美國與國際經濟數據（含預期、前值、公布值） | Nasdaq 經濟行事曆（備援：ForexFactory） |
| 台灣經濟數據（CPI、外銷訂單、失業率、出口、景氣燈號…） | 中華民國統計資訊網「預告發布時間表」 |
| 美股財報 | Nasdaq 財報行事曆 |
| 台股法說會 | 公開資訊觀測站；市值來自證交所、櫃買中心 OpenAPI |
| 台股休市日 | 證交所 OpenAPI；美股休市日依 NYSE 規則計算 |
| 行情 | Yahoo Finance |
| 新聞 | 鉅亨網、中央社、經濟日報、Yahoo 股市、CNBC、WSJ、MarketWatch |

任何一個來源失敗都不影響其他部分，網站頁尾與推播會提示哪些來源暫時失敗。

---

## 常見問題

- **網站顯示「尚無資料」**：還沒成功跑過 workflow，到 Actions 手動執行一次。
- **Actions 顯示紅色 ✗**：點進去看是哪個步驟。推播失敗時會印出 Telegram／LINE 的錯誤訊息（例如 `chat not found` 表示 Chat ID 錯或還沒對 bot 按 Start）。
- **configure-pages 步驟失敗**：第 2 步的 Pages Source 還沒設成 GitHub Actions。
- **網址不對**：可在 **Settings → Secrets and variables → Actions → Variables** 新增 `SITE_URL` 覆寫推播中的網站連結。
- **法說會或台灣統計抓不到**：部分台灣政府網站偶爾會擋海外 IP（GitHub 主機在美國），頁尾會顯示失敗項目；通常隔天恢復。

## 本機執行（需要 Python 3.8 以上）

```bash
python -m briefing build
```

```bash
python -m briefing notify --dry-run
```

`build` 會更新 `docs/data/`，直接用瀏覽器開 `docs/index.html` 就能看；`--dry-run` 只印出推播內容，不會真的發送。

---

僅供參考，非投資建議。
