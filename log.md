# Project Log

## 2026-06-29 10:30 +08:00

### Index 2-7 source alignment from `0_Preparation/0622/S__1343499_0.jpg`

- Reviewed the reference image for Index 2-7 source locations.
- Kept KPI 2 and KPI 4 on Fintel Basic Stats because the image points those rows to Fintel.
- Kept KPI 3 using the existing Fintel/Yahoo owners-count path; Yahoo provides the current institutional owners count, while MRQ change still requires Fintel Basic Stats text.
- Reworked KPI 5, KPI 6, and KPI 7 to use MarketBeat Institutional Ownership instead of Fintel/yfinance as the primary source:
  - `https://www.marketbeat.com/stocks/{EXCHANGE}/{SYMBOL}/institutional-ownership/`
  - `Number of Institutional Buyers (last 12 months)`
  - `Number of Institutional Sellers (last 12 months)`
  - `Total Institutional Inflows (last 12 months)`
  - `Total Institutional Outflows (last 12 months)`
- Added `parse_marketbeat_institutional_ownership()` and a dedicated MarketBeat ownership fetch path.

### Live verification

- `python -m py_compile streamlit_app.py` passed.
- AAPL live MarketBeat Institutional Ownership parse passed:
  - Buyers: `4,297`
  - Sellers: `4,345`
  - Inflows: `$286.56B`
  - Outflows: `$131.27B`
  - KPI 5: `0.99`
  - KPI 6: `3.73%`
  - KPI 7: `3.68`
- AAPL Fintel live fetch returned HTTP 403 for all configured impersonations, so KPI 2 and KPI 3 remained unavailable in that run unless the user pastes Fintel Basic Stats text into the sidebar fallback.

## 2026-06-29 10:55 +08:00

### Fintel 403 mitigation

- Tested a `curl_cffi.Session` warmup flow before fetching the Fintel ownership page.
- The working sequence is:
  - open `https://fintel.io/`
  - open `https://fintel.io/login`
  - fetch `https://fintel.io/so/us/{symbol}`
- Added browser-like request headers and preserved cookies in the same session.
- AAPL live verification passed with `chrome120`:
  - Fintel status: `Fintel 自動抓取成功 (chrome120, session warmup)`
  - KPI 2: `13.07%`
  - KPI 3: `-2.96%`
  - KPI 4: `-7.25%`
- This avoids adding heavier browser automation dependencies for now.

### Fintel 403 crawler runbook

- Preferred lightweight method:
  - Use `curl_cffi.requests.Session(impersonate="chrome120")`.
  - Reuse the same session for warmup and target requests so cookies are preserved.
  - Send browser-like headers: `accept`, `accept-language`, `cache-control`, `pragma`, `referer`, and `upgrade-insecure-requests`.
  - Warmup URLs: `https://fintel.io/`, then `https://fintel.io/login`.
  - Target URL: `https://fintel.io/so/us/{symbol}`.
- Retry order used by the app:
  - `chrome120`
  - `chrome124`
  - `chrome136`
  - `safari17_0`
- If this method fails again:
  - Next option is Playwright/Selenium real-browser rendering.
  - `cloudscraper` can be tested, but it is less reliable for newer Cloudflare challenges.
- Do not replace this with plain `requests`; direct `requests.get()` still returned Cloudflare HTTP 403 in testing.

## 2026-06-29 11:25 +08:00

### StockCircle ESG KPI

- Reviewed `0_Preparation/0622/S__1343500_0.jpg` and `0_Preparation/0622/S__1343507_0.jpg`.
- The image maps ESG to KPI 11, while KPI 9 is already Short Interest Change in the 8-17 index sheet, so the app implements ESG as KPI 11 to avoid overwriting KPI 9.
- Added StockCircle source URL pattern:
  - `https://stockcircle.com/stocks/{symbol}`
  - Example: `https://stockcircle.com/stocks/aapl`
- Added `fetch_stockcircle_text()` with `curl_cffi` browser impersonation.
- Added `parse_stockcircle_esg()` for both page states:
  - ESG table: `Environment`, `Social`, `Governance`, `Total`
  - Missing data: `ESG Score No data`
- ESG value uses StockCircle `Total` when present; otherwise it computes `(E + S + G) / 3`.
- ESG judgement follows the StockCircle note `Lower score means less risk`:
  - `> 70`: higher ESG risk
  - `50-70`: medium ESG risk
  - `< 50`: lower ESG risk
- Parser sample verification passed:
  - Environment `74`
  - Social `76`
  - Governance `66`
  - Total `72`
- AAPL live verification:
  - StockCircle fetch succeeded with `chrome120`.
  - Current AAPL StockCircle page returned `ESG Score No data`.
  - KPI 11 is saved as `N/A` with status `StockCircle 無 ESG 資料`.

## 2026-06-29 13:15 +08:00

### KPI 11 StockCircle crawler retest

- Rechecked KPI 11 because the Streamlit page showed insufficient ESG data.
- Tried the crawler/tool options discussed earlier:
  - `curl_cffi` direct browser impersonation.
  - StockCircle session warmup similar to the Fintel workaround.
  - Multiple impersonations: `chrome120`, `chrome124`, `chrome136`, `safari17_0`.
  - yfinance `sustainability` fallback probe.
- Findings:
  - StockCircle warmup with `/login` is not useful; it can trigger Cloudflare/host `502 Bad gateway`.
  - Direct StockCircle fetch can succeed; in current tests AAPL page returned normal HTML.
  - The normal AAPL page itself contains `ESG Score No data`.
  - yfinance `sustainability` returned an empty dataframe / Yahoo 404 for AAPL.
  - Playwright/Selenium/cloudscraper are not installed in the current Python environment, and no local Chrome/Edge executable was found.
- Code update:
  - `fetch_stockcircle_text()` now detects Cloudflare/host error pages and continues retrying other impersonations.
  - KPI 11 detail now appends `StockCircle page shows ESG Score No data` when the source page explicitly says no data.
- Latest AAPL verification:
  - StockCircle fetch status: success.
  - Parsed ESG payload: `{'no_data': True}`.
  - KPI 11 remains `N/A`, but this is because StockCircle currently provides no ESG score for AAPL, not because the crawler failed.

## 2026-06-29 13:35 +08:00

### KPI 11 lxml parser integration

- Reviewed `test_lxml.py`; it demonstrates parsing a rendered ESG HTML table with `BeautifulSoup(..., "lxml")`.
- Added the same table-oriented parser path to `parse_stockcircle_esg()`:
  - find heading `ESG Score`
  - find the next `table`
  - read `Environment`, `Social`, `Governance`, and `Total`
  - preserve `No data` detection
- Installed `lxml` into the current Python environment and added it to `requirements.txt`.
- Parser fallback remains in place:
  - use `lxml` when available
  - fallback to `html.parser` if `lxml` is missing
- Verification:
  - `python test_lxml.py` passed.
  - Sample ESG table parsed as `66 / 45 / 59 / 57`.
  - `python -m py_compile streamlit_app.py` passed.
  - AAPL live query used parser `lxml`, but StockCircle still returned `ESG Score No data`, so KPI 11 remains `N/A` for AAPL.

## 2026-06-25 23:28 +08:00

### 主題

建立 17 項機構籌碼 index 的 Streamlit + SQLite 查詢工具，並處理目前遇到的資料抓取不穩定問題。

### 已完成進度

- 已建立 `streamlit_app.py`。
- 已建立 `stock_kpi_history.sqlite3` 查詢歷史資料庫。
- 已建立 `implementplan.md` 追蹤 17 項 index 實作狀態。
- 已完成 KPI：1、2、3、4、5、6、7、12、13、14、15。
- 待完成 KPI：8、9、10、11、16、17。

### 目前資料抓取問題

#### 1. Fintel live 抓取不穩定

現象：

- `https://fintel.io/so/us/{ticker}` 有時可抓取，有時回傳 `HTTP 403`。
- 有時請求會 timeout。
- 即使頁面可抓取，也可能缺少 KPI 4-7 需要的完整欄位，例如：
  - `Average Portfolio Allocation`
  - `Buyers`
  - `Sellers`
  - `Inflows`
  - `Outflows`
  - `Market Cap`

影響：

- KPI 2：MRQ Institutional Shares Change。
- KPI 3：Owners Count Change。
- KPI 4：Portfolio Allocation Growth。
- KPI 5：Buyer/Seller Ratio。
- KPI 6：Relative Net Inflow。
- KPI 7：Institutional Activity Score。

暫時對策：

- 保留 Streamlit sidebar 的「Fintel 備援文字貼上」欄位。
- 若使用者可從 Fintel 頁面複製 Basic Stats / Ownership / Fund Flow 區塊文字，系統會直接解析貼上的文字。
- KPI 4-7 已加入 yfinance fallback，當 Fintel 缺資料時改用 yfinance top institutional holders 估算。
- Treeview `status` 欄會標示：
  - `OK`：Fintel 或 yfinance 原始欄位足夠。
  - `yfinance 估算`：由 yfinance top holders 估算，不等於 Fintel 完整 ownership-flow 口徑。
  - `需 ... 資料`：Fintel 與 yfinance fallback 都不足。

#### 2. yfinance 可替代範圍有限

可穩定取得的欄位：

- `major_holders`
  - `insidersPercentHeld`
  - `institutionsPercentHeld`
  - `institutionsFloatPercentHeld`
  - `institutionsCount`
- `institutional_holders`
  - `Date Reported`
  - `Holder`
  - `pctHeld`
  - `Shares`
  - `Value`
  - `pctChange`
- `mutualfund_holders`
- `info` / `fast_info`
  - `sharesOutstanding`
  - `floatShares`
  - `marketCap`
  - `averageVolume10days`
  - `averageVolume`

適合直接使用的 KPI：

- KPI 1：Institutional Ownership。
- KPI 12：Institutional Float Control。
- KPI 13：Volume Activity。
- KPI 14：Volume Growth。
- KPI 15：Insider Ownership。

只能估算的 KPI：

- KPI 4：用 top holders 的持股市值加權 `pctChange` 估算 Portfolio Allocation Growth。
- KPI 5：用 top holders 中 `pctChange > 0` 當 Buyers，`pctChange < 0` 當 Sellers。
- KPI 6：用 top holders 的股數變化與持股價值估算 Inflows / Outflows，再除以 market cap。
- KPI 7：由 KPI 5 和 KPI 6 的估算值計算。

限制：

- yfinance 的 holder 明細通常只有 top holders，不是完整機構名單。
- yfinance fallback 不是 Fintel 的完整機構資金流口徑。
- 若 `pctChange = 1.0`，代表前期可能接近 0 或新進持股，流量估算會偏大；目前仍保留計算，但會在 status 標示估算。

#### 3. JSON 寫入 SQLite 時遇到 Timestamp 序列化問題

現象：

- yfinance holder dataframe 內含 `Timestamp`。
- 寫入 `query_runs.raw_payload` 時，`json.dumps()` 出現：
  - `TypeError: Object of type Timestamp is not JSON serializable`

對策：

- `save_run()` 已改用 `json.dumps(..., default=str)`。
- 可正常保存 yfinance holder 明細與 fallback 估算 payload。

### 目前驗證結果

MU live 查詢：

- Fintel 有時可取得 KPI 2、3。
- KPI 4-7 可由 yfinance fallback 補上。
- 最新測試中 KPI 4-7 顯示：
  - KPI 4：20.34%，`yfinance 估算`
  - KPI 5：1.50，`yfinance 估算`
  - KPI 6：2.47%，`yfinance 估算`
  - KPI 7：3.71，`yfinance 估算`

Streamlit：

- 啟動方式：`python -m streamlit run streamlit_app.py`
- 本機網址：`http://localhost:8501`
- `run_streamlit.bat` 已改用 `python -m streamlit`，避免 `streamlit` 指令不在 PATH 的問題。

### 待追蹤事項

- KPI 8、9、10 需要建立 MarketBeat short interest 抓取器。
- KPI 11 需要確認 StockCircle ESG 是否可穩定抓取，並決定使用平均公式或圖中權重版。
- KPI 16、17 需要建立 SEC EDGAR / 13F 資料流程。
- 若未來取得 Fintel API 或穩定匯出格式，應優先用官方/API/匯出資料取代 HTML scraping。

## 2026-06-26 18:54 +08:00

### Streamlit default ticker

- Changed the Streamlit sidebar default ticker from `MU` to `AAPL`.
- Changed the history ticker fallback from `MU` to `AAPL`.

### Fintel Basic Stats parsing for KPI 2 and KPI 3

Source pages checked:
- `https://fintel.io/so/us/nvda`
- `https://fintel.io/so/us/AAPL`

Confirmed that the Basic Stats values are available as HTML text and can be parsed, not only as an image/canvas.

NVDA live parse verified:
- `owners_count=5952`
- `owners_change_mrq_pct=-5.58`
- `institutional_shares_long=18,580,550,152`
- `institutional_ownership_fintel_pct=76.71`
- `institutional_shares_change=1,836,620,000`
- `institutional_shares_change_mrq_pct=10.97`
- `average_portfolio_allocation_pct=2.538`
- `portfolio_allocation_change_mrq_pct=-14.34`
- `institutional_value_long_usd_thousands=3,141,981,626`

AAPL issue and fix:
- Streamlit showed KPI 2 and KPI 3 as missing when Fintel timed out or when the AAPL `Institutional Shares` text used a different layout.
- AAPL page format was `Institutional Shares ... 12.31% (Long) MRQ`, while the previous parser expected `(Long)` immediately after the label.
- Updated the `Institutional Shares` regex so `(Long)` is optional after the label and optional before `MRQ`.
- Increased Fintel fetch timeout from 30 seconds to 60 seconds.
- Added retry across `curl_cffi` impersonations: `chrome120`, `chrome124`, `chrome136`, `safari17_0`.

AAPL live parse verified after fix:
- `owners_count=6199`
- `owners_change_mrq_pct=-4.69`
- `institutional_shares_long=10,893,345,655`
- `institutional_ownership_fintel_pct=74.17`
- `institutional_shares_change=1,193,770,000`
- `institutional_shares_change_mrq_pct=12.31`
- `average_portfolio_allocation_pct=2.8567`
- `portfolio_allocation_change_mrq_pct=-7.43`
- `institutional_value_long_usd_thousands=2,682,997,900`

Expected KPI values for AAPL:
- KPI 2 `MRQ Institutional Shares Change`: `12.31%`
- KPI 3 `Owners Count Change`: `-4.69%`

### MarketBeat Short Interest parsing for KPI 8, KPI 9, KPI 10

Source page checked:
- `https://www.marketbeat.com/stocks/NASDAQ/AAPL/short-interest/`

Confirmed that MarketBeat exposes the short-interest overview values in HTML text:
- `Current Short Interest`
- `Previous Short Interest`
- `Change Vs. Previous Month`
- `Short Percent of Float`
- `Short Interest Ratio`
- `Last Record Date`

Added MarketBeat fetch and parser:
- KPI 8 `Short Interest %` reads `Short Percent of Float`.
- KPI 9 `Short Interest Change` reads `Change Vs. Previous Month`.
- KPI 10 `Days To Cover` reads `Short Interest Ratio`.
- MarketBeat exchange path is inferred from yfinance exchange metadata, defaulting to `NASDAQ` when unknown.

AAPL MarketBeat live parse verified:
- `current_short_interest=144,248,476`
- `previous_short_interest=155,886,024`
- `short_interest_change_pct=-7.47`
- `short_percent_of_float=0.98`
- `days_to_cover=2.8`
- `last_record_date=June 15, 2026`

Expected KPI values for AAPL:
- KPI 8 `Short Interest %`: `0.98%`
- KPI 9 `Short Interest Change`: `-7.47%`
- KPI 10 `Days To Cover`: `2.80`

### Verification

- `python -m py_compile streamlit_app.py` passed.
- Fintel live fetch and parse passed for AAPL after retry/timeout changes.
- MarketBeat live fetch and parse passed for AAPL.
- Streamlit local server responded with HTTP 200 at `http://localhost:8501`.
- `git status` could not be checked because Windows safe.directory/dubious ownership blocks `C:/AI_class` for the sandbox user.

## 2026-06-29

### StockCircle AAPL ESG Playwright fallback

- Rechecked `0_Preparation/0622/AAPL_ESG_html.png`; the rendered StockCircle DOM places KPI 11 under `ESG Score` as a table with `Environment`, `Social`, `Governance`, and `Total`.
- Verified the user's venv at `C:\AI_class\aivm\Scripts\python.exe` has both `playwright` and `selenium`; the earlier failure came from using the shell default Python instead of this venv.
- Added a Playwright fallback to `fetch_stockcircle_text()`:
  - keep the existing `curl_cffi` static fetch first;
  - if static HTML says `ESG Score No data`, render the page with Playwright and parse `page.content()`;
  - if all static attempts fail with timeout/502, also try Playwright before returning failure.
- AAPL rendered ESG verification:
  - Environment `66`
  - Social `45`
  - Governance `59`
  - Total `57`
- Verified commands:
  - `C:\AI_class\aivm\Scripts\python.exe test_lxml.py`
  - `C:\AI_class\aivm\Scripts\python.exe test_playwright.py`
  - `C:\AI_class\aivm\Scripts\python.exe -m py_compile streamlit_app.py`
  - `fetch_stockcircle_text("AAPL")` returned `StockCircle Playwright 渲染抓取成功; static chrome120 showed ESG Score No data`
  - `parse_stockcircle_esg(...)` returned `{'environment': 66.0, 'social': 45.0, 'governance': 59.0, 'total': 57.0, 'parser': 'lxml'}`
