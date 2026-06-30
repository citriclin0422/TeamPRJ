# 17 項機構籌碼 Index 實作進度

建立日期：2026-06-25  
最後更新：2026-06-25  
專案目標：建立可透過網頁輸入股票代號、抓取資料、計算 index、顯示 Treeview 報表，並以 SQLite 儲存查詢歷史的機構籌碼分析工具。

## 目前狀態摘要

- 已完成：11 項
- 待完成：6 項
- 已完成項目：1、2、3、4、5、6、7、12、13、14、15
- 待完成項目：8、9、10、11、16、17

> 備註：KPI 4-7 已完成公式、Fintel 文字解析、Treeview 顯示與 SQLite 入庫流程。Fintel live 抓取偶爾會被網站回 403 或 timeout；介面已保留「Fintel 備援文字貼上」欄位，也已加入 yfinance top institutional holders 估算 fallback。若欄位來自估算，Treeview 狀態會顯示「yfinance 估算」。

## Index 實作清單

| 編號 | Index 指標 | 主要資料來源 | 公式 / 判讀資料 | 狀態 | 備註 |
|---:|---|---|---|---|---|
| 1 | 機構持股比例 | Fintel、Yahoo Finance Statistics / yfinance | 機構持股股數 ÷ 總股本 × 100 | 已完成 | 目前由 yfinance `heldPercentInstitutions` 取得；Fintel 可作對照 |
| 2 | MRQ 機構持股變化 | Fintel | (本季機構持股 - 上季機構持股) ÷ 上季機構持股 × 100 | 已完成 | 已解析 Fintel `Institutional Shares ... change ... MRQ` |
| 3 | Owners 家數變化 | Fintel | (本季 Owners 家數 - 上季 Owners 家數) ÷ 上季 Owners 家數 × 100 | 已完成 | 已解析 Fintel `Institutional Owners ... change ... MRQ` |
| 4 | Portfolio Allocation | Fintel；yfinance 估算 fallback | (新配置比例 - 舊配置比例) ÷ 舊配置比例 × 100 | 已完成 | Fintel 解析 `Average Portfolio Allocation ... change ... MRQ`；缺值時用 yfinance top holders 市值加權 `pctChange` 估算 |
| 5 | 買賣家比 | Fintel；yfinance 估算 fallback | 買家數 ÷ 賣家數 | 已完成 | Fintel 解析 Buyers / Sellers；缺值時用 yfinance top holders `pctChange > 0 / < 0` 估算 |
| 6 | 相對淨流入 | Fintel、yfinance | 淨流入 = Inflows - Outflows；相對淨流入 = 淨流入 ÷ 市值 × 100 | 已完成 | Fintel 解析 Inflows / Outflows；缺值時由 yfinance top holders 股數變化與持股市值估算，市值用 yfinance `marketCap` |
| 7 | 活躍度 Institutional Activity Score | Fintel；yfinance 估算 fallback | 買賣比 × 相對淨流入 % | 已完成 | 依賴第 5、6 項；若第 5、6 項為估算，此項同步標示為 yfinance 估算 |
| 8 | Short Interest % | MarketBeat | Short Shares ÷ Float × 100 | 待完成 | 需建立 MarketBeat short interest 抓取器 |
| 9 | Short Interest 變化 | MarketBeat | (本期空頭股數 - 上期空頭股數) ÷ 上期空頭股數 × 100 | 待完成 | 需抓取 Previous / Current Short Interest |
| 10 | Days To Cover | MarketBeat | Short Shares ÷ Average Daily Volume | 待完成 | 可由 MarketBeat 或 short shares + yfinance average volume 補算 |
| 11 | ESG | StockCircle | (E + S + G) ÷ 3 | 待完成 | 圖中另註權重版：E 40%、S 25%、G 35%；實作時需確認採用平均或權重 |
| 12 | 機構佔流通股比例 | Yahoo Finance Statistics / yfinance | 機構持股總量 = 總股本 × 機構持股比例；機構佔流通股 = 機構持股總量 ÷ Float × 100 | 已完成 | 目前已由 shares outstanding、float shares、institutional ownership 計算 |
| 13 | 成交量活躍度 Volume Activity | Yahoo Finance Statistics / yfinance | 10 日平均成交量 ÷ 總股本 × 100；另可計算 10 日平均成交量 ÷ Float × 100 | 已完成 | 目前報表以總股本版為主，detail 顯示 Float 版 |
| 14 | 成交量增長率 Volume Growth | Yahoo Finance Statistics / yfinance | (10 日均量 - 3 個月均量) ÷ 3 個月均量 × 100 | 已完成 | 目前由 yfinance average volume 欄位計算 |
| 15 | Insider Ownership 內部人持股 | Yahoo Finance Holders / yfinance、MarketBeat Insider Trades | Insider Ownership % | 已完成 | 目前由 yfinance `heldPercentInsiders` 取得 |
| 16 | Form 4 內部人交易申報 | SEC EDGAR Search Filings | 追蹤 Transaction Date、Shares、Price、Transaction Code / Type、Transaction Value | 待完成 | 需建立 SEC Form 4 抓取與交易類型分類 |
| 17 | Form 13F 機構持股申報 | SEC Form 13F Data Sets | 追蹤 Shares Held、Market Value、New / Increased / Reduced / Closed Position、Filing Date | 待完成 | 需建立 SEC 13F 資料集或 filings 抓取流程 |

## 判斷規則摘要

| 編號 | 指標 | 判斷規則 |
|---:|---|---|
| 1 | 機構持股比例 | >70% 高機構持股；40%~70% 中等機構持股；<40% 低機構持股 |
| 2 | MRQ 機構持股變化 | >20% 強增長；5%~20% 中增長；<5% 弱增長；負值為機構減持 |
| 3 | Owners 家數變化 | >20% 高度關注；5%~20% 穩定增加；<5% 觀望；負值為機構流失 |
| 4 | Portfolio Allocation | >25% 強增長；15%~25% 中強增長；5%~15% 穩定增長；<5% 低增長；負值為配置下降 |
| 5 | 買賣家比 | >2 買方明顯強；1~2 買方略強或正常；<1 賣方較強 |
| 6 | 相對淨流入 | >20% 強資金流入；5%~20% 中等資金流入；1%~5% 低資金流入；<1% 弱資金流入；負值為資金流出 |
| 7 | 活躍度 | 0~10 低活躍；10~30 中活躍；30~50 高活躍；50+ 極高活躍 |
| 8 | Short Interest % | 0~5% 低空頭；5%~15% 中空頭；15%~25% 中高空頭；25%以上 高空頭 |
| 9 | Short Interest 變化 | <-5% 空頭減少；-5%~5% 持平；>5% 空頭增加 |
| 10 | Days To Cover | 0~3 天低；3~7 天中；7 天以上高 |
| 11 | ESG | 70 以上高分；50~70 中等；50 以下低分 |
| 12 | 機構佔流通股比例 | 大型股：<40% 低影響、40%~60% 中影響、60%~80% 高影響、80%以上極高影響 |
| 13 | 成交量活躍度 | 大型股：0~5% 低活躍、5%~15% 中活躍、15%~30% 高活躍、30%以上異常活躍 |
| 14 | 成交量增長率 | 大型股：0~20% 低增長、20%~50% 中增長、50%~100% 高增長、100%以上異常增長 |
| 15 | Insider Ownership | >10% 高信心；5%~10% 正常；<5% 偏低 |
| 16 | Form 4 | 大量買入為利多；持續買入為正向；大量賣出需觀察；零星賣出偏中性 |
| 17 | Form 13F | New Position 新增持股；Increased Position 持續加碼；Reduced Position 減碼；Closed Position 全部賣出 |

## 下一階段實作順序建議

1. 完成 MarketBeat 空頭指標：8、9、10。
2. 完成 StockCircle ESG：11。
3. 完成 SEC 申報資料：16、17。
4. 將所有新增指標持續寫入現有 Streamlit Treeview 報表與 SQLite 歷史紀錄。
