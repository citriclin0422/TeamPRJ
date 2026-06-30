# Stock KPI Index Dashboard

這個專案是一個可部署到 Streamlit Community Cloud 的股票 KPI 查詢儀表板。使用者輸入股票代號後，系統會整合 Yahoo Finance、Fintel、MarketBeat 與 StockCircle 資料，計算 KPI 1-15，並將查詢結果保存到 SQLite。

## Streamlit Cloud 部署設定

在 `https://share.streamlit.io/deploy` 建立 app 時，請使用下列設定：

| 欄位 | 設定值 |
|---|---|
| Repository | `citriclin0422/TeamPRJ` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |

本 repo 已包含部署需要的檔案：

| 檔案 | 用途 |
|---|---|
| `streamlit_app.py` | Streamlit Cloud 的主執行檔。 |
| `requirements.txt` | Python 套件清單。 |
| `packages.txt` | Streamlit Cloud Linux 系統套件，安裝 Chromium 給 Playwright 備援爬蟲使用。 |
| `.streamlit/config.toml` | Streamlit 雲端執行設定。 |

## 本機執行

```powershell
pip install -r requirements.txt
python -m playwright install chromium
python -m streamlit run streamlit_app.py
```

或在 Windows 直接執行：

```powershell
run_streamlit.bat
```

## 專案功能

- 查詢股票代號並計算 KPI 1-15。
- 使用 `yfinance` 取得股本、市值、成交量、機構持股與內部人持股資料。
- 使用 `curl_cffi` 抓取 Fintel、MarketBeat 與 StockCircle。
- 使用 BeautifulSoup、lxml 與 regex 解析網頁文字。
- StockCircle ESG 若靜態頁面無資料，會用 Playwright + Chromium 渲染頁面後再解析。
- 查詢結果寫入 `stock_kpi_history.sqlite3`。
- `rowdata.csv` 保存每個股票代號最新查詢日期的 KPI 匯出資料。

## KPI 說明與成功率分析

完整的繁體中文專案說明、KPI 來源對照與 `rowdata.csv` 成功率分析請見：

[READEME.md](./READEME.md)

## 注意事項

- Streamlit Community Cloud 的檔案系統屬於雲端執行環境，SQLite 歷史資料可能會隨 app 重啟或重新部署而重建。
- Fintel、MarketBeat、StockCircle 都是第三方網站，抓取成功率會受到網站防爬、資料缺漏、代號格式與網路狀態影響。
- 非美股代號或特殊代號，例如 `2330.TW`、`BRK-A`、`BRK-B`，可能需要另外調整資料來源或 URL 轉換規則。
