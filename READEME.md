# Stock KPI Index Dashboard 專案說明

## 專案建立目的

本目錄是一個以 Streamlit 建立的股票 KPI 指標查詢與紀錄系統。使用者輸入股票代號後，程式會即時抓取 Yahoo Finance、Fintel、MarketBeat 與 StockCircle 等來源，計算 KPI 1-15，並將每次查詢結果寫入 SQLite 資料庫 `stock_kpi_history.sqlite3`。

專案的核心目標是把分散在不同網站的機構持股、買賣流向、放空壓力、ESG、成交量與內部人持股資料，整理成同一份可追蹤的 KPI 表，方便後續比較不同股票、檢查資料來源穩定度，以及保留查詢歷史。

## 主要檔案

| 檔案 | 說明 |
|---|---|
| `streamlit_app.py` | Streamlit 主程式，負責資料抓取、KPI 計算、SQLite 寫入與 UI 顯示。 |
| `stock_kpi_history.sqlite3` | SQLite 歷史資料庫，包含每次查詢主檔與 KPI 明細。 |
| `rowdata.csv` | 從資料庫匯出的最新 KPI 原始資料；目前為每個股票代號各取最新查詢日期的 KPI 1-15。 |
| `requirements.txt` | Python 套件需求，包含 `streamlit`、`pandas`、`yfinance`、`curl_cffi`、`beautifulsoup4`、`lxml`、`playwright`。 |
| `run_streamlit.bat` | Windows 啟動 Streamlit 的批次檔。 |
| `log.md` | 專案維護紀錄，保存已修正的爬蟲、解析與驗證結果。 |
| `test_*.py` | 針對 BeautifulSoup、lxml、Playwright、Selenium、API 等抓取方式的測試腳本。 |

## 執行方式

安裝套件：

```powershell
pip install -r requirements.txt
```

若第一次使用 Playwright，需要安裝瀏覽器：

```powershell
python -m playwright install chromium
```

啟動 Streamlit：

```powershell
python -m streamlit run streamlit_app.py
```

或直接執行：

```powershell
run_streamlit.bat
```

啟動後可在瀏覽器開啟 Streamlit 提供的 localhost 網址，輸入股票代號後執行查詢。查詢結果會顯示在頁面上，同時寫入 `stock_kpi_history.sqlite3`。

## 資料處理流程

1. 使用 `yfinance` 取得公司名稱、交易所、市值、股本、流通股數、機構持股、內部人持股與成交量等基礎資料。
2. 使用 `curl_cffi` 模擬瀏覽器請求 Fintel、MarketBeat 與 StockCircle 頁面，以降低一般 requests 被阻擋的機率。
3. 使用 BeautifulSoup、lxml 與正規表示式解析 HTML 或頁面文字。
4. StockCircle 若靜態 HTML 顯示 ESG 無資料或抓取失敗，會使用 Playwright 渲染頁面後再解析。
5. 將各來源資料整合成 KPI 1-15。
6. 將查詢主檔寫入 `query_runs`，將各 KPI 明細寫入 `kpi_results`。
7. 從 SQLite 匯出每個股票代號最近日期的 KPI 1-15 到 `rowdata.csv`，供後續分析使用。

## SQLite 資料表

| 資料表 | 說明 |
|---|---|
| `query_runs` | 每一次股票查詢的主檔，包含 `id`、`queried_at`、`symbol`、`company_name`、`raw_payload`。 |
| `kpi_results` | 每一次查詢產生的 KPI 明細，包含 `run_id`、`kpi_code`、`kpi_name`、`value`、`display_value`、`judgement`、`formula`、`source`、`detail`、`status`。 |

## KPI 與爬蟲工具對照

| KPI | 指標名稱 | 主要資料來源 | 使用工具與解析方式 |
|---:|---|---|---|
| 1 | Institutional Ownership | Yahoo Finance / yfinance，輔以 Fintel 定義 | `yfinance.Ticker().info` 與 major holders 欄位。 |
| 2 | MRQ Institutional Shares Change | Fintel | `curl_cffi` 抓取 `https://fintel.io/so/us/{symbol}`，BeautifulSoup 轉文字後用 regex 解析 Institutional Shares MRQ 變化。 |
| 3 | Owners Count Change | Fintel | `curl_cffi` + BeautifulSoup + regex 解析 Institutional Owners 與 MRQ change。 |
| 4 | Portfolio Allocation Growth | Fintel，缺資料時可用 yfinance 估算 | Fintel regex 解析 Average Portfolio Allocation；不足時由 yfinance institutional holders 的變化估算。 |
| 5 | Buyer/Seller Ratio | MarketBeat Institutional Ownership，缺資料時可用 yfinance 估算 | `curl_cffi` 抓取 MarketBeat institutional-ownership 頁，解析 Buyers / Sellers summary card。 |
| 6 | Relative Net Inflow | MarketBeat Institutional Ownership + yfinance market cap | `curl_cffi` + regex 解析 Inflows / Outflows，市值可由 yfinance 補足。 |
| 7 | Institutional Activity Score | KPI 5 與 KPI 6 衍生 | 由 Buyer/Seller Ratio 乘上 Relative Net Inflow 計算。 |
| 8 | Short Interest % | MarketBeat Short Interest | `curl_cffi` 抓取 MarketBeat short-interest 頁，解析 Short Percent of Float。 |
| 9 | Short Interest Change | MarketBeat Short Interest | 同上，解析 Change Vs. Previous Month。 |
| 10 | Days To Cover | MarketBeat Short Interest | 同上，解析 Short Interest Ratio / Days to Cover。 |
| 11 | ESG Score | StockCircle ESG Score | 先用 `curl_cffi` 抓取 StockCircle；若靜態頁無 ESG 或失敗，改用 Playwright 渲染後以 BeautifulSoup/lxml 解析 ESG table。 |
| 12 | Institutional Float Control | Yahoo Finance / yfinance | 由 shares outstanding、institutional ownership 與 float shares 計算。 |
| 13 | Volume Activity | Yahoo Finance / yfinance | 由 10 日平均成交量與 shares outstanding 計算。 |
| 14 | Volume Growth | Yahoo Finance / yfinance | 由 10 日平均成交量與 3 個月平均成交量計算。 |
| 15 | Insider Ownership | Yahoo Finance / yfinance | 讀取 `heldPercentInsiders` 或 major holders 中的 insiders percent。 |

## 目前處理狀況

目前 Streamlit 主流程已可完成：

- 查詢單一股票代號。
- 自動抓取 Yahoo Finance / Fintel / MarketBeat / StockCircle。
- 在 Fintel 被阻擋時支援手動貼上 Fintel 文字備援。
- 對 StockCircle ESG 使用 Playwright 渲染備援。
- 將每次查詢保存到 SQLite。
- 從 SQLite 匯出每個股票代號最新日期的 KPI 1-15 到 `rowdata.csv`。

目前 `rowdata.csv` 的匯出範圍為每個股票代號各取最新一次查詢。資料庫內共有 32 個股票代號，理論完整 KPI 格數為 32 x 15 = 480 格；實際匯出 471 筆，代表部分舊查詢紀錄本身沒有完整產生 KPI row。

## `rowdata.csv` 抓取結果成功率分析

本次分析依據 `C:\AI_class\TeamPRJ\rowdata.csv`。判定方式如下：

- `status = OK` 視為成功抓取或成功計算。
- `status = yfinance 估算` 視為可用估算，但不列入嚴格 OK 成功率。
- `需 ... 資料`、`缺資料` 視為未成功。

整體結果：

| 項目 | 數值 |
|---|---:|
| 股票代號數 | 32 |
| 理論完整 KPI 格數 | 480 |
| 實際匯出 KPI row | 471 |
| row 覆蓋率 | 98.12% |
| `OK` 筆數 | 405 |
| 以實際匯出 row 計算的 OK 成功率 | 85.99% |
| 以理論完整格數計算的 OK 成功率 | 84.38% |

狀態分布：

| 狀態 | 筆數 | 佔實際匯出 row 比例 |
|---|---:|---:|
| OK | 405 | 85.99% |
| 需 Fintel 資料 | 15 | 3.18% |
| 需 MarketBeat 資料 | 15 | 3.18% |
| 缺資料 | 11 | 2.34% |
| yfinance 估算 | 8 | 1.70% |
| 需 StockCircle ESG 資料 | 5 | 1.06% |
| 需 Allocation 資料 | 3 | 0.64% |
| 需 Buyers/Sellers 資料 | 3 | 0.64% |
| 需 Inflows/Outflows 資料 | 3 | 0.64% |
| 需 KPI 5 與 KPI 6 資料 | 3 | 0.64% |

各 KPI 成功率：

| KPI | 指標名稱 | 實際 row | OK 筆數 | OK 成功率 |
|---:|---|---:|---:|---:|
| 1 | 機構持股比例 | 32 | 30 | 93.75% |
| 2 | MRQ 機構持股變化 | 32 | 22 | 68.75% |
| 3 | Owners 家數變化 | 32 | 27 | 84.38% |
| 4 | Portfolio Allocation Growth | 31 | 26 | 83.87% |
| 5 | Buyer/Seller Ratio | 31 | 26 | 83.87% |
| 6 | Relative Net Inflow | 31 | 26 | 83.87% |
| 7 | Institutional Activity Score | 31 | 26 | 83.87% |
| 8 | Short Interest % | 31 | 26 | 83.87% |
| 9 | Short Interest Change | 31 | 26 | 83.87% |
| 10 | Days To Cover | 31 | 26 | 83.87% |
| 11 | ESG Score | 30 | 25 | 83.33% |
| 12 | 機構佔流通股比例 | 32 | 29 | 90.62% |
| 13 | 成交量活躍度 | 32 | 30 | 93.75% |
| 14 | 成交量增長率 | 32 | 30 | 93.75% |
| 15 | Insider Ownership | 32 | 30 | 93.75% |

## 成功率解讀

整體 OK 成功率為 85.99%，代表目前最新匯出的資料中，大多數 KPI 已能成功抓取或計算。若以完整 480 格作為分母，成功率為 84.38%，差異主要來自 `2330.TW` 與 `APPL` 的最新查詢紀錄沒有完整 KPI row。

最穩定的指標集中在 yfinance 來源的 KPI 1、13、14、15，成功率皆為 93.75%。KPI 12 也達 90.62%，但因部分股票缺少 float shares 或 institutional ownership，略低於其他 yfinance 指標。

Fintel 相關 KPI 中，KPI 2 成功率最低，只有 68.75%。這表示 Institutional Shares MRQ 變化最容易受 Fintel 頁面阻擋、欄位格式變動或個股資料缺漏影響。KPI 3 與 KPI 4 表現較好，但仍有部分股票需要 Fintel 或 Allocation 資料。

MarketBeat 相關 KPI 5-10 的成功率集中在 83.87%。這表示 MarketBeat institutional ownership 與 short interest 頁面在大多數美股可用，但對非典型代號、ETF、錯字代號或特殊股權類別較容易失敗。

StockCircle KPI 11 的成功率為 83.33%。目前已有 Playwright 渲染備援，但仍有部分股票沒有 ESG 資料，或 StockCircle 頁面本身沒有對應資料。

## 需要注意的資料品質問題

- `APPL` 很可能是 `AAPL` 的誤輸入代號；其最新紀錄 14 筆 KPI 全部不是 OK，會明顯拉低成功率。
- `BRK`、`BRK-A`、`BRK-B` 屬於特殊代號或股權類別，對 Fintel、MarketBeat、StockCircle 的 URL 與資料頁面較敏感。
- `2330.TW` 是台股代號，Fintel、MarketBeat、StockCircle 這些偏美股資料來源不一定支援，因此只有 7 筆 KPI row。
- `SPCX` 類似 ETF 或特殊標的，MarketBeat / Fintel / ESG 資料缺口較多。(自判:馬斯克公司新上市股票資料少)

## 後續改善建議

1. 對輸入股票代號加入檢查與提示，例如偵測 `APPL` 並提醒可能應為 `AAPL`。
2. 對 `BRK.A` / `BRK-A` / `BRK/B` 這類特殊代號建立來源網站專用轉換規則。
3. 將非美股如 `2330.TW` 分流到更適合的資料來源，避免用 Fintel / MarketBeat 當主要來源。
4. 在 `rowdata.csv` 匯出時可選擇補齊缺少的 KPI row，將狀態標記為 `未產生 row`，讓每個股票固定 15 筆，方便後續統計。
5. 對 Fintel KPI 2 加強解析容錯，因目前它是最低成功率的單一 KPI。
