import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup


# ===== 選用套件：curl_cffi =====
# curl_cffi 可模擬不同瀏覽器指紋，對 Fintel / MarketBeat / StockCircle
# 這類有反爬或 Cloudflare 保護的網站，比一般 requests 穩定。
try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - optional dependency
    curl_requests = None


# ===== 專案路徑與資料庫設定 =====
# APP_DIR 固定指向此檔案所在資料夾，SQLite 歷史資料也放在同一層，
# 方便 Streamlit app 直接讀寫，不依賴目前啟動指令的位置。
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "stock_kpi_history.sqlite3"


# ===== KPI 定義表 =====
# 每一列代表 Treeview / SQLite 會顯示的一個指標：
# code 是排序與辨識用編號，name/formula/source 則是報表欄位說明。
KPI_DEFINITIONS = [
    {"code": "01", "name": "Institutional Ownership", "formula": "Institutional shares / shares outstanding * 100", "source": "Yahoo Finance/yfinance; Fintel"},
    {"code": "02", "name": "MRQ Institutional Shares Change", "formula": "(current institutional shares - prior institutional shares) / prior institutional shares * 100", "source": "Fintel"},
    {"code": "03", "name": "Owners Count Change", "formula": "(current owners - prior owners) / prior owners * 100", "source": "Fintel"},
    {"code": "04", "name": "Portfolio Allocation Growth", "formula": "(new allocation - old allocation) / old allocation * 100", "source": "Fintel"},
    {"code": "05", "name": "Buyer/Seller Ratio", "formula": "buyers / sellers", "source": "MarketBeat Institutional Ownership"},
    {"code": "06", "name": "Relative Net Inflow", "formula": "(inflows - outflows) / market cap * 100", "source": "MarketBeat Institutional Ownership + yfinance market cap fallback"},
    {"code": "07", "name": "Institutional Activity Score", "formula": "buyer/seller ratio * relative net inflow %", "source": "MarketBeat Institutional Ownership"},
    {"code": "08", "name": "Short Interest %", "formula": "short shares / float * 100", "source": "MarketBeat Short Interest"},
    {"code": "09", "name": "Short Interest Change", "formula": "(current short interest - previous short interest) / previous short interest * 100", "source": "MarketBeat Short Interest"},
    {"code": "10", "name": "Days To Cover", "formula": "short shares / average daily volume", "source": "MarketBeat Short Interest"},
    {"code": "11", "name": "ESG Score", "formula": "(environment + social + governance) / 3", "source": "StockCircle ESG Score"},
    {"code": "12", "name": "Institutional Float Control", "formula": "shares outstanding * institutional ownership / float * 100", "source": "Yahoo Finance/yfinance"},
    {"code": "13", "name": "Volume Activity", "formula": "10-day average volume / shares outstanding * 100", "source": "Yahoo Finance/yfinance"},
    {"code": "14", "name": "Volume Growth", "formula": "(10-day average volume - 3-month average volume) / 3-month average volume * 100", "source": "Yahoo Finance/yfinance"},
    {"code": "15", "name": "Insider Ownership", "formula": "insider ownership * 100", "source": "Yahoo Finance/yfinance"},
]


# ===== SQLite 初始化 =====
# 建立兩張表：
# 1. query_runs：每次查詢的主檔與原始 payload
# 2. kpi_results：每次查詢產生的各 KPI 明細
def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queried_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company_name TEXT,
                raw_payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kpi_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                kpi_code TEXT NOT NULL,
                kpi_name TEXT NOT NULL,
                value REAL,
                display_value TEXT NOT NULL,
                judgement TEXT NOT NULL,
                formula TEXT NOT NULL,
                source TEXT NOT NULL,
                detail TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES query_runs(id)
            )
            """
        )


# ===== 數值清理與顯示格式工具 =====
# 這些函式統一處理 None、逗號、美元符號、百分比與金額縮寫，
# 避免各 KPI 重複寫格式化邏輯。
def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(str(value).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def pct(value: Optional[float], digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}%"


def number(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:,.0f}"


def ratio(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def money(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1_000_000_000:
        return f"{sign}${abs_value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{sign}${abs_value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{sign}${abs_value / 1_000:.2f}K"
    return f"{sign}${abs_value:.0f}"


def parse_scaled_number(value: str, suffix: str = "") -> Optional[float]:
    base = safe_float(value)
    if base is None:
        return None
    suffix = (suffix or "").upper()
    scale = {"K": 1_000, "M": 1_000_000, "MM": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return base * scale


# ===== KPI 判讀規則 =====
# 以下 classify_* 函式把數值轉成中文判讀文字。
# 門檻值依 implementplan.md 與參考圖片規則整理，供 Treeview 顯示。
def classify_institutional_ownership(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 70:
        return "高機構持股"
    if value >= 40:
        return "中等機構持股"
    return "低機構持股"


def classify_growth(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value < 0:
        return "減少/流失"
    if value > 20:
        return "強增長/高度關注"
    if value >= 5:
        return "中增長/穩定增加"
    return "弱增長/觀望"


def classify_portfolio_allocation(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 25:
        return "配置強增長"
    if value >= 15:
        return "配置中強增長"
    if value >= 5:
        return "配置穩定增長"
    if value < 0:
        return "配置下降"
    return "配置低增長"


def classify_buyer_seller(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 2:
        return "買方明顯強"
    if value >= 1:
        return "買方略強或正常"
    return "賣方較強"


def classify_relative_inflow(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value < 0:
        return "資金流出"
    if value > 20:
        return "強資金流入"
    if value >= 5:
        return "中等資金流入"
    if value >= 1:
        return "低資金流入"
    return "弱資金流入"


def classify_activity(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value >= 50:
        return "極高活躍"
    if value >= 30:
        return "高活躍"
    if value >= 10:
        return "中活躍"
    return "低活躍"


def classify_institutional_float(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value >= 80:
        return "大型股：極高影響"
    if value >= 60:
        return "大型股：高影響"
    if value >= 40:
        return "大型股：中影響"
    return "大型股：低影響"


def classify_volume_activity(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value >= 30:
        return "大型股：異常活躍"
    if value >= 15:
        return "大型股：高活躍"
    if value >= 5:
        return "大型股：中活躍"
    return "大型股：低活躍"


def classify_volume_growth(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value >= 100:
        return "大型股：異常增長"
    if value >= 50:
        return "大型股：高增長"
    if value >= 20:
        return "大型股：中增長"
    return "大型股：低增長"


def classify_insider(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 10:
        return "高信心"
    if value >= 5:
        return "正常"
    return "偏低"


def classify_short_interest(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value >= 25:
        return "極高放空壓力"
    if value >= 15:
        return "高放空壓力"
    if value >= 5:
        return "中度放空壓力"
    return "低放空壓力"


def classify_short_change(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value < -5:
        return "空頭部位下降"
    if value <= 5:
        return "空頭部位穩定"
    return "空頭部位增加"


def classify_days_to_cover(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 7:
        return "回補天數偏高"
    if value >= 3:
        return "回補天數中等"
    return "回補天數偏低"


def classify_esg(value: Optional[float]) -> str:
    if value is None:
        return "資料不足"
    if value > 70:
        return "ESG 風險偏高"
    if value >= 50:
        return "ESG 風險中等"
    return "ESG 風險偏低"


# ===== Yahoo Finance / yfinance 資料抓取 =====
# 取得公司基本資訊、股本、市值、float、持股比例與成交量。
# 這些資料用於 KPI 1、12、13、14、15，也作為部分指標的估算備援。
def fetch_yfinance(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    info = ticker.info
    major_holders = None
    institutional_holders = None
    mutualfund_holders = None
    try:
        major_holders = ticker.major_holders
    except Exception:
        pass
    try:
        institutional_holders = ticker.institutional_holders
    except Exception:
        pass
    try:
        mutualfund_holders = ticker.mutualfund_holders
    except Exception:
        pass
    fast = {}
    try:
        fast = dict(ticker.fast_info)
    except Exception:
        pass

    def major_value(name: str) -> Optional[float]:
        if major_holders is None or major_holders.empty:
            return None
        if name in major_holders.index and "Value" in major_holders.columns:
            return safe_float(major_holders.loc[name, "Value"])
        if {"Breakdown", "Value"}.issubset(set(major_holders.columns)):
            rows = major_holders[major_holders["Breakdown"] == name]
            if not rows.empty:
                return safe_float(rows.iloc[0]["Value"])
        return None

    return {
        "company_name": info.get("longName") or info.get("shortName") or symbol.upper(),
        "exchange": info.get("exchange") or info.get("fullExchangeName"),
        "market_cap": safe_float(info.get("marketCap") or fast.get("marketCap")),
        "shares_outstanding": safe_float(info.get("sharesOutstanding") or fast.get("shares")),
        "float_shares": safe_float(info.get("floatShares")),
        "held_percent_institutions": safe_float(info.get("heldPercentInstitutions") if info.get("heldPercentInstitutions") is not None else major_value("institutionsPercentHeld")),
        "held_percent_insiders": safe_float(info.get("heldPercentInsiders") if info.get("heldPercentInsiders") is not None else major_value("insidersPercentHeld")),
        "institutions_float_percent": safe_float(major_value("institutionsFloatPercentHeld")),
        "institutions_count": safe_float(major_value("institutionsCount")),
        "average_volume_10d": safe_float(info.get("averageVolume10days") or info.get("averageDailyVolume10Day") or fast.get("tenDayAverageVolume")),
        "average_volume_3m": safe_float(info.get("averageVolume") or fast.get("threeMonthAverageVolume")),
        "institutional_holders": institutional_holders.to_dict("records") if institutional_holders is not None and not institutional_holders.empty else [],
        "mutualfund_holders": mutualfund_holders.to_dict("records") if mutualfund_holders is not None and not mutualfund_holders.empty else [],
    }


# ===== Fintel 抓取：KPI 2、3、4 的主要來源 =====
# 使用 curl_cffi Session warmup 技巧：先訪問首頁與 login 頁保留 cookie，
# 再抓 ownership 頁，以降低 Fintel 403 的機率。
def fetch_fintel_text(symbol: str) -> tuple[Optional[str], str]:
    url = f"https://fintel.io/so/us/{symbol.lower()}"
    if curl_requests is None:
        return None, "curl_cffi 未安裝，略過 Fintel 自動抓取"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://fintel.io/",
        "upgrade-insecure-requests": "1",
    }
    errors: list[str] = []
    for impersonate in ("chrome120", "chrome124", "chrome136", "safari17_0"):
        try:
            session = curl_requests.Session(impersonate=impersonate)
            for warmup_url in ("https://fintel.io/", "https://fintel.io/login"):
                session.get(warmup_url, headers=headers, timeout=30)
            response = session.get(url, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.text, f"Fintel 自動抓取成功 ({impersonate}, session warmup)"
            errors.append(f"{impersonate}: HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{impersonate}: {exc}")
    return None, f"Fintel 自動抓取失敗：{'; '.join(errors)}"


# ===== HTML 文字正規化 =====
# 將 HTML 轉為純文字，並壓縮空白，讓後續 regex 解析更穩定。
def normalize_fintel_text(text: str) -> str:
    if "<html" in text[:1000].lower() or "<!doctype" in text[:1000].lower():
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text)


# ===== 通用欄位數字搜尋 =====
# 給定多個可能 label，尋找後方的數值，並支援 K/M/MM/B 單位轉換。
def find_metric_number(text: str, labels: list[str]) -> Optional[float]:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:\-]?\s*\$?(-?[\d,]+(?:\.\d+)?)\s*(MM|M|K|B)?"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_scaled_number(match.group(1), match.group(2) or "")
    return None


# ===== Fintel 文字解析 =====
# 從 Fintel Basic Stats / Ownership 文字中解析機構家數、機構持股變化、
# Portfolio Allocation 等欄位，提供 KPI 2、3、4 使用。
def parse_fintel(text: str) -> dict[str, Any]:
    compact = normalize_fintel_text(text)
    data: dict[str, Any] = {}

    owners = re.search(
        r"Institutional Owners\s+([\d,]+).*?change of\s+(-?[\d.]+)\s*%\s+MRQ",
        compact,
        flags=re.IGNORECASE,
    )
    if owners:
        data["owners_count"] = float(owners.group(1).replace(",", ""))
        data["owners_change_mrq_pct"] = float(owners.group(2))

    shares = re.search(
        r"Institutional Shares(?:\s*\(Long\))?\s+([\d,]+)\s*-\s*([\d.]+)\s*%.*?"
        r"change of\s+(-?[\d,]+(?:\.\d+)?)\s*(MM|M|K|B)?\s*shares\s+(-?[\d.]+)\s*%"
        r"(?:\s*\(Long\))?\s+MRQ",
        compact,
        flags=re.IGNORECASE,
    )
    if shares:
        data["institutional_shares_long"] = float(shares.group(1).replace(",", ""))
        data["institutional_ownership_fintel_pct"] = float(shares.group(2))
        data["institutional_shares_change"] = parse_scaled_number(shares.group(3), shares.group(4) or "")
        data["institutional_shares_change_mrq_pct"] = float(shares.group(5))

    allocation = re.search(
        r"Average Portfolio Allocation\s+(-?[\d.]+)\s*%.*?change of\s+(-?[\d.]+)\s*%\s+MRQ",
        compact,
        flags=re.IGNORECASE,
    )
    if allocation:
        data["average_portfolio_allocation_pct"] = float(allocation.group(1))
        data["portfolio_allocation_change_mrq_pct"] = float(allocation.group(2))

    institutional_value = re.search(
        r"Institutional Value\s*\(Long\)\s*\$\s*([\d,]+(?:\.\d+)?)\s+USD\s*\(\$1000\)",
        compact,
        flags=re.IGNORECASE,
    )
    if institutional_value:
        data["institutional_value_long_usd_thousands"] = safe_float(institutional_value.group(1))

    data["buyers"] = find_metric_number(compact, ["Buyers", "Buyer Count", "Funds Buying"])
    data["sellers"] = find_metric_number(compact, ["Sellers", "Seller Count", "Funds Selling"])
    data["inflows"] = find_metric_number(compact, ["Inflows", "Inflow"])
    data["outflows"] = find_metric_number(compact, ["Outflows", "Outflow"])
    data["market_cap_fintel"] = find_metric_number(compact, ["Market Cap", "Market Capitalization"])

    return {key: value for key, value in data.items() if value is not None}


# ===== MarketBeat 交易所路徑轉換 =====
# MarketBeat URL 需要 NASDAQ / NYSE / NYSEARCA 等路徑名稱，
# 這裡把 yfinance 回傳的 exchange 代碼轉成 MarketBeat 可用格式。
def marketbeat_exchange(exchange: Optional[str]) -> str:
    value = (exchange or "").upper()
    if "NASDAQ" in value or value in {"NMS", "NGM", "NCM", "NAS"}:
        return "NASDAQ"
    if "NYSE ARCA" in value or value in {"PCX", "ARCX"}:
        return "NYSEARCA"
    if "NYSE" in value or value in {"NYQ", "NYE"}:
        return "NYSE"
    if "AMEX" in value or value in {"ASE", "ASEMKT"}:
        return "NYSEAMERICAN"
    return "NASDAQ"


# ===== MarketBeat 通用頁面抓取 =====
# Short Interest 與 Institutional Ownership 都使用同一套 URL 組合與抓取邏輯。
def fetch_marketbeat_page_text(symbol: str, exchange: Optional[str], page_slug: str, page_name: str) -> tuple[Optional[str], str]:
    if curl_requests is None:
        return None, "curl_cffi 未安裝，略過 MarketBeat 自動抓取"
    marketbeat_ex = marketbeat_exchange(exchange)
    url = f"https://www.marketbeat.com/stocks/{marketbeat_ex}/{symbol.upper()}/{page_slug}/"
    try:
        response = curl_requests.get(url, impersonate="chrome120", timeout=30)
        if response.status_code != 200:
            return None, f"MarketBeat {page_name} 自動抓取失敗 HTTP {response.status_code}"
        return response.text, f"MarketBeat {page_name} 自動抓取成功 ({marketbeat_ex})"
    except Exception as exc:
        return None, f"MarketBeat {page_name} 自動抓取失敗：{exc}"


# ===== MarketBeat Short Interest 抓取：KPI 8、9、10 =====
def fetch_marketbeat_text(symbol: str, exchange: Optional[str] = None) -> tuple[Optional[str], str]:
    return fetch_marketbeat_page_text(symbol, exchange, "short-interest", "Short Interest")


# ===== MarketBeat Institutional Ownership 抓取：KPI 5、6、7 =====
def fetch_marketbeat_ownership_text(symbol: str, exchange: Optional[str] = None) -> tuple[Optional[str], str]:
    return fetch_marketbeat_page_text(symbol, exchange, "institutional-ownership", "Institutional Ownership")


# ===== MarketBeat Short Interest 解析 =====
# 解析 Current/Previous Short Interest、Change Vs. Previous Month、
# Short Percent of Float、Days to Cover 等欄位。
def parse_marketbeat_short_interest(text: str) -> dict[str, Any]:
    compact = normalize_fintel_text(text)
    data: dict[str, Any] = {}

    current = re.search(r"Current Short Interest\s+([\d,]+)\s+shares", compact, flags=re.IGNORECASE)
    if current:
        data["current_short_interest"] = safe_float(current.group(1))

    previous = re.search(r"Previous Short Interest\s+([\d,]+)\s+shares", compact, flags=re.IGNORECASE)
    if previous:
        data["previous_short_interest"] = safe_float(previous.group(1))

    change = re.search(r"Change Vs\. Previous Month\s+([+-]?[\d.]+)\s*%", compact, flags=re.IGNORECASE)
    if change:
        data["short_interest_change_pct"] = safe_float(change.group(1))

    short_float = re.search(r"Short Percent of Float\s+([+-]?[\d.]+)\s*%", compact, flags=re.IGNORECASE)
    if short_float:
        data["short_percent_of_float"] = safe_float(short_float.group(1))

    days = re.search(r"Short Interest Ratio\s+([\d.]+)\s+Days to Cover", compact, flags=re.IGNORECASE)
    if days:
        data["days_to_cover"] = safe_float(days.group(1))

    date = re.search(r"Last Record Date\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", compact, flags=re.IGNORECASE)
    if date:
        data["last_record_date"] = date.group(1)

    return {key: value for key, value in data.items() if value is not None}


# ===== MarketBeat summary 卡片數字解析 =====
# MarketBeat ownership 頁的買家、賣家、流入、流出都在 summary 卡片內。
def find_marketbeat_summary_number(text: str, label: str) -> Optional[float]:
    pattern = rf"{re.escape(label)}(?:\s*\([^)]+\))*\s*\$?(-?[\d,]+(?:\.\d+)?)\s*(MM|M|K|B|%)?"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return parse_scaled_number(match.group(1), match.group(2) or "")


# ===== MarketBeat Institutional Ownership 解析 =====
# 解析 Buyers、Sellers、Inflows、Outflows，用於 KPI 5、6、7。
def parse_marketbeat_institutional_ownership(text: str) -> dict[str, Any]:
    compact = normalize_fintel_text(text)
    data: dict[str, Any] = {}

    data["marketbeat_institutional_ownership_pct"] = find_marketbeat_summary_number(
        compact,
        "Current Institutional Ownership Percentage",
    )
    data["buyers"] = find_marketbeat_summary_number(
        compact,
        "Number of Institutional Buyers",
    )
    data["sellers"] = find_marketbeat_summary_number(
        compact,
        "Number of Institutional Sellers",
    )
    data["inflows"] = find_marketbeat_summary_number(
        compact,
        "Total Institutional Inflows",
    )
    data["outflows"] = find_marketbeat_summary_number(
        compact,
        "Total Institutional Outflows",
    )

    return {key: value for key, value in data.items() if value is not None}


# ===== StockCircle ESG 抓取：KPI 11 =====
# 先直接抓取 StockCircle 股票頁。若靜態 HTML 顯示 ESG Score No data，
# 再改用 Playwright 等待 React 渲染後取 page content。
def chromium_launch_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }
    for command in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        executable = shutil.which(command)
        if executable:
            options["executable_path"] = executable
            break
    return options


def fetch_stockcircle_rendered_text(symbol: str) -> tuple[Optional[str], str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return None, f"Playwright 未可用：{exc}"

    url = f"https://stockcircle.com/stocks/{symbol.lower()}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, **chromium_launch_options())
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("load", timeout=15000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector("text=ESG Score", timeout=15000)
                    page.wait_for_function(
                        """
                        () => {
                            const text = document.body?.innerText || "";
                            const start = text.toLowerCase().indexOf("esg score");
                            if (start < 0) return false;
                            const block = text.slice(start, start + 1000);
                            return /Total\\s+\\d+(?:\\.\\d+)?\\s*\\/\\s*100/i.test(block);
                        }
                        """,
                        timeout=25000,
                    )
                except Exception:
                    page.wait_for_timeout(3000)
                html = page.content()
            finally:
                browser.close()
        return html, "StockCircle Playwright 渲染抓取成功"
    except Exception as exc:
        return None, f"StockCircle Playwright 渲染抓取失敗：{exc}"


# 避免把錯誤頁誤判成「沒有 ESG 資料」。
def fetch_stockcircle_text(symbol: str) -> tuple[Optional[str], str]:
    if curl_requests is None:
        rendered_text, rendered_status = fetch_stockcircle_rendered_text(symbol)
        return rendered_text, rendered_status
    url = f"https://stockcircle.com/stocks/{symbol.lower()}"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://stockcircle.com/",
        "upgrade-insecure-requests": "1",
    }
    errors: list[str] = []
    for impersonate in ("chrome120", "chrome124", "chrome136", "safari17_0"):
        try:
            response = curl_requests.get(url, impersonate=impersonate, headers=headers, timeout=30)
            if response.status_code == 200:
                page_text = BeautifulSoup(response.text, "html.parser").get_text(" ")
                if "Bad gateway" in page_text or "cloudflare.com" in page_text.lower():
                    errors.append(f"{impersonate}: Cloudflare/host error page")
                    continue
                if re.search(r"ESG Score\s+No data", re.sub(r"\s+", " ", page_text), flags=re.IGNORECASE):
                    rendered_text, rendered_status = fetch_stockcircle_rendered_text(symbol)
                    if rendered_text:
                        return rendered_text, f"{rendered_status}; static {impersonate} showed ESG Score No data"
                    return response.text, (
                        f"StockCircle 靜態抓取成功但顯示 No data ({impersonate}); "
                        f"{rendered_status}"
                    )
                return response.text, f"StockCircle 自動抓取成功 ({impersonate})"
            errors.append(f"{impersonate}: HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{impersonate}: {exc}")
    rendered_text, rendered_status = fetch_stockcircle_rendered_text(symbol)
    if rendered_text:
        return rendered_text, f"{rendered_status}; static fetch failed: {'; '.join(errors)}"
    return None, f"StockCircle 自動抓取失敗：{'; '.join(errors)}; {rendered_status}"


# ===== StockCircle ESG 解析 =====
# 優先使用 BeautifulSoup + lxml 解析 ESG table；若 lxml 不可用則回退 html.parser。
# 支援兩種頁面狀態：有 E/S/G/Total 表格，或頁面明確顯示 ESG Score No data。
def parse_stockcircle_esg(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        soup = BeautifulSoup(text, "lxml")
        parser_name = "lxml"
    except Exception:
        soup = BeautifulSoup(text, "html.parser")
        parser_name = "html.parser"

    esg_heading = soup.find(
        lambda tag: tag.name in {"h1", "h2", "h3", "h4"}
        and "ESG Score" in tag.get_text(" ", strip=True)
    )
    if esg_heading:
        esg_table = esg_heading.find_next("table")
        if esg_table:
            for row in esg_table.find_all("tr"):
                cols = row.find_all(["td", "th"])
                if len(cols) < 2:
                    continue
                metric = cols[0].get_text(" ", strip=True).lower()
                score_match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*100", cols[1].get_text(" ", strip=True))
                if not score_match:
                    continue
                if "environment" in metric:
                    data["environment"] = safe_float(score_match.group(1))
                elif "social" in metric:
                    data["social"] = safe_float(score_match.group(1))
                elif "governance" in metric:
                    data["governance"] = safe_float(score_match.group(1))
                elif "total" in metric:
                    data["total"] = safe_float(score_match.group(1))
            if data:
                data["parser"] = parser_name
                return {key: value for key, value in data.items() if value is not None}

        next_node = esg_heading.find_next_sibling()
        if next_node and re.search(r"\bNo data\b", next_node.get_text(" ", strip=True), flags=re.IGNORECASE):
            data["no_data"] = True
            data["parser"] = parser_name
            return data

    compact = normalize_fintel_text(text)

    esg_index = compact.lower().find("esg score")
    if esg_index >= 0:
        esg_block = compact[esg_index : esg_index + 800]
        if re.search(r"ESG Score\s+No data", esg_block, flags=re.IGNORECASE):
            data["no_data"] = True
            data["parser"] = parser_name
            return data
    else:
        esg_block = compact

    pattern = (
        r"ESG Score\s+"
        r"(?:A company's environmental,\s*social,\s*and governance risks\.\s*Lower score means less risk\.\s*)?"
        r"Environment\s+(\d+(?:\.\d+)?)\s*/\s*100\s+"
        r"Social\s+(\d+(?:\.\d+)?)\s*/\s*100\s+"
        r"Governance\s+(\d+(?:\.\d+)?)\s*/\s*100\s+"
        r"Total\s+(\d+(?:\.\d+)?)\s*/\s*100"
    )
    match = re.search(pattern, esg_block, flags=re.IGNORECASE)
    if match:
        environment = safe_float(match.group(1))
        social = safe_float(match.group(2))
        governance = safe_float(match.group(3))
        total = safe_float(match.group(4))
        data.update(
            {
                "environment": environment,
                "social": social,
                "governance": governance,
                "total": total,
            }
        )
        if total is None and None not in (environment, social, governance):
            data["total"] = (environment + social + governance) / 3
        data["parser"] = parser_name

    return {key: value for key, value in data.items() if value is not None}


# ===== yfinance 估算備援 =====
# 當 Fintel 或 MarketBeat 缺少部分 ownership-flow 欄位時，
# 用 yfinance top institutional holders 的持股變化估算買家、賣家、流入、流出。
def estimate_yfinance_advanced_metrics(yahoo: dict[str, Any]) -> dict[str, Any]:
    holders = yahoo.get("institutional_holders") or []
    market_cap = yahoo.get("market_cap")
    estimates: dict[str, Any] = {
        "source_note": "yfinance top holders estimate, not Fintel full ownership-flow data",
    }
    if not holders:
        return estimates

    buyers = 0
    sellers = 0
    inflows = 0.0
    outflows = 0.0
    weighted_change_sum = 0.0
    weight_sum = 0.0

    for holder in holders:
        shares = safe_float(holder.get("Shares"))
        value = safe_float(holder.get("Value"))
        pct_change = safe_float(holder.get("pctChange"))
        if shares is None or value is None or pct_change is None:
            continue
        if pct_change > 0:
            buyers += 1
        elif pct_change < 0:
            sellers += 1

        if pct_change != -1:
            previous_shares = shares / (1 + pct_change)
            share_change = shares - previous_shares
            price = value / shares if shares else 0
            flow_value = share_change * price
            if flow_value >= 0:
                inflows += flow_value
            else:
                outflows += abs(flow_value)

        weighted_change_sum += pct_change * value
        weight_sum += value

    if buyers or sellers:
        estimates["buyers"] = float(buyers)
        estimates["sellers"] = float(sellers)
    if inflows or outflows:
        estimates["inflows"] = inflows
        estimates["outflows"] = outflows
    if weight_sum:
        estimates["portfolio_allocation_change_mrq_pct"] = weighted_change_sum / weight_sum * 100
    if market_cap:
        estimates["market_cap_fintel"] = market_cap
    return estimates


# ===== 指標來源選擇工具 =====
# 優先使用主要來源；若主要來源缺資料，再改用 fallback 並標示來源。
def metric_with_source(fintel: dict[str, Any], fallback: dict[str, Any], key: str) -> tuple[Optional[float], str]:
    if fintel.get(key) is not None:
        return safe_float(fintel.get(key)), "Fintel"
    if fallback.get(key) is not None:
        return safe_float(fallback.get(key)), "yfinance 估算"
    return None, "缺資料"


# ===== KPI row 組裝工具 =====
# 將單一 KPI 的數值、顯示文字、判讀、來源與計算細節整理成報表列。
def make_row(code: str, value: Optional[float], display: str, judgement: str, detail: str, status: str) -> dict[str, Any]:
    definition = next(item for item in KPI_DEFINITIONS if item["code"] == code)
    return {
        "kpi_code": code,
        "kpi_name": definition["name"],
        "value": value,
        "display_value": display,
        "judgement": judgement,
        "formula": definition["formula"],
        "source": definition["source"],
        "detail": detail,
        "status": status,
    }


# ===== KPI 計算主體 =====
# 將 Yahoo/Fintel/MarketBeat/StockCircle 的原始資料整合後，
# 依 KPI_DEFINITIONS 產生 Treeview 與 SQLite 需要的完整 KPI rows。
def make_kpi_rows(
    symbol: str,
    yahoo: dict[str, Any],
    fintel: dict[str, Any],
    fintel_status: str,
    marketbeat: dict[str, Any],
    marketbeat_status: str,
    marketbeat_ownership: Optional[dict[str, Any]] = None,
    marketbeat_ownership_status: str = "",
    stockcircle_esg: Optional[dict[str, Any]] = None,
    stockcircle_status: str = "",
) -> list[dict[str, Any]]:
    marketbeat_ownership = marketbeat_ownership or {}
    stockcircle_esg = stockcircle_esg or {}
    yfinance_estimates = estimate_yfinance_advanced_metrics(yahoo)
    shares = yahoo["shares_outstanding"]
    float_shares = yahoo["float_shares"]
    market_cap = fintel.get("market_cap_fintel") or yfinance_estimates.get("market_cap_fintel") or yahoo.get("market_cap")
    inst_pct = yahoo["held_percent_institutions"] * 100 if yahoo["held_percent_institutions"] is not None else None
    insider_pct = yahoo["held_percent_insiders"] * 100 if yahoo["held_percent_insiders"] is not None else None
    avg10 = yahoo["average_volume_10d"]
    avg3m = yahoo["average_volume_3m"]

    inst_shares = shares * yahoo["held_percent_institutions"] if shares and yahoo["held_percent_institutions"] is not None else None
    inst_float = inst_shares / float_shares * 100 if inst_shares and float_shares else None
    vol_activity = avg10 / shares * 100 if avg10 and shares else None
    vol_activity_float = avg10 / float_shares * 100 if avg10 and float_shares else None
    vol_growth = (avg10 - avg3m) / avg3m * 100 if avg10 and avg3m else None

    buyers, buyers_source = metric_with_source(marketbeat_ownership, yfinance_estimates, "buyers")
    if buyers_source == "Fintel":
        buyers_source = "MarketBeat"
    sellers, sellers_source = metric_with_source(marketbeat_ownership, yfinance_estimates, "sellers")
    if sellers_source == "Fintel":
        sellers_source = "MarketBeat"
    buyer_seller = buyers / sellers if buyers is not None and sellers not in (None, 0) else None
    flow_source = "MarketBeat" if marketbeat_ownership.get("inflows") is not None and marketbeat_ownership.get("outflows") is not None else "yfinance 估算" if yfinance_estimates.get("inflows") is not None and yfinance_estimates.get("outflows") is not None else "缺資料"
    inflows, _ = metric_with_source(marketbeat_ownership, yfinance_estimates, "inflows")
    outflows, _ = metric_with_source(marketbeat_ownership, yfinance_estimates, "outflows")
    net_inflow = inflows - outflows if inflows is not None and outflows is not None else None
    relative_inflow = net_inflow / market_cap * 100 if net_inflow is not None and market_cap else None
    activity_score = buyer_seller * relative_inflow if buyer_seller is not None and relative_inflow is not None else None
    allocation_change, allocation_source = metric_with_source(fintel, yfinance_estimates, "portfolio_allocation_change_mrq_pct")
    short_pct = safe_float(marketbeat.get("short_percent_of_float"))
    short_change = safe_float(marketbeat.get("short_interest_change_pct"))
    days_to_cover = safe_float(marketbeat.get("days_to_cover"))
    esg_environment = safe_float(stockcircle_esg.get("environment"))
    esg_social = safe_float(stockcircle_esg.get("social"))
    esg_governance = safe_float(stockcircle_esg.get("governance"))
    esg_total = safe_float(stockcircle_esg.get("total"))
    if esg_total is None and None not in (esg_environment, esg_social, esg_governance):
        esg_total = (esg_environment + esg_social + esg_governance) / 3
    esg_status = "OK" if esg_total is not None else "StockCircle 無 ESG 資料" if stockcircle_esg.get("no_data") else "需 StockCircle ESG 資料"
    esg_detail = (
        f"Environment={number(esg_environment)}/100; "
        f"Social={number(esg_social)}/100; "
        f"Governance={number(esg_governance)}/100; "
        f"Total={number(esg_total)}/100; {stockcircle_status}"
    )
    if stockcircle_esg.get("no_data"):
        esg_detail += "; StockCircle page shows ESG Score No data"
    short_detail = (
        f"Current short={number(marketbeat.get('current_short_interest'))}; "
        f"Previous short={number(marketbeat.get('previous_short_interest'))}; "
        f"Record date={marketbeat.get('last_record_date', 'N/A')}; {marketbeat_status}"
    )

    rows = [
        make_row("01", inst_pct, pct(inst_pct), classify_institutional_ownership(inst_pct), f"Shares Outstanding={number(shares)}; yfinance heldPercentInstitutions={pct(inst_pct)}", "OK" if inst_pct is not None else "缺資料"),
        make_row("02", safe_float(fintel.get("institutional_shares_change_mrq_pct")), pct(safe_float(fintel.get("institutional_shares_change_mrq_pct"))), classify_growth(safe_float(fintel.get("institutional_shares_change_mrq_pct"))), f"Fintel change shares={number(fintel.get('institutional_shares_change'))}; {fintel_status}", "OK" if fintel.get("institutional_shares_change_mrq_pct") is not None else "需 Fintel 資料"),
        make_row("03", safe_float(fintel.get("owners_change_mrq_pct")), pct(safe_float(fintel.get("owners_change_mrq_pct"))), classify_growth(safe_float(fintel.get("owners_change_mrq_pct"))), f"Owners={number(fintel.get('owners_count') or yahoo.get('institutions_count'))}; {fintel_status}", "OK" if fintel.get("owners_change_mrq_pct") is not None else "需 Fintel 資料"),
        make_row("04", allocation_change, pct(allocation_change), classify_portfolio_allocation(allocation_change), f"Source={allocation_source}; Average Portfolio Allocation={pct(fintel.get('average_portfolio_allocation_pct'))}; {fintel_status}", "OK" if allocation_source == "Fintel" else "yfinance 估算" if allocation_change is not None else "需 Allocation 資料"),
        make_row("05", buyer_seller, ratio(buyer_seller), classify_buyer_seller(buyer_seller), f"Source={buyers_source}/{sellers_source}; Buyers={number(buyers)}; Sellers={number(sellers)}; {marketbeat_ownership_status}", "OK" if buyers_source == "MarketBeat" and sellers_source == "MarketBeat" else "yfinance 估算" if buyer_seller is not None else "需 Buyers/Sellers 資料"),
        make_row("06", relative_inflow, pct(relative_inflow), classify_relative_inflow(relative_inflow), f"Source={flow_source}; Inflows={money(inflows)}; Outflows={money(outflows)}; Net={money(net_inflow)}; Market Cap={money(market_cap)}", "OK" if flow_source == "MarketBeat" else "yfinance 估算" if relative_inflow is not None else "需 Inflows/Outflows 資料"),
        make_row("07", activity_score, ratio(activity_score), classify_activity(activity_score), f"Source=KPI 5/6; Buyer/Seller Ratio={ratio(buyer_seller)}; Relative Net Inflow={pct(relative_inflow)}", "OK" if flow_source == "MarketBeat" and buyers_source == "MarketBeat" else "yfinance 估算" if activity_score is not None else "需 KPI 5 與 KPI 6 資料"),
        make_row("08", short_pct, pct(short_pct), classify_short_interest(short_pct), short_detail, "OK" if short_pct is not None else "需 MarketBeat 資料"),
        make_row("09", short_change, pct(short_change), classify_short_change(short_change), short_detail, "OK" if short_change is not None else "需 MarketBeat 資料"),
        make_row("10", days_to_cover, ratio(days_to_cover), classify_days_to_cover(days_to_cover), short_detail, "OK" if days_to_cover is not None else "需 MarketBeat 資料"),
        make_row("12", inst_float, pct(inst_float), classify_institutional_float(inst_float), f"Institutional shares estimate={number(inst_shares)}; Float={number(float_shares)}", "OK" if inst_float is not None else "缺資料"),
        make_row("13", vol_activity, pct(vol_activity), classify_volume_activity(vol_activity), f"10-day avg volume={number(avg10)}; Float version={pct(vol_activity_float)}", "OK" if vol_activity is not None else "缺資料"),
        make_row("14", vol_growth, pct(vol_growth), classify_volume_growth(vol_growth), f"10-day avg volume={number(avg10)}; 3-month avg volume={number(avg3m)}", "OK" if vol_growth is not None else "缺資料"),
        make_row("15", insider_pct, pct(insider_pct, 3), classify_insider(insider_pct), f"yfinance heldPercentInsiders={pct(insider_pct, 3)}", "OK" if insider_pct is not None else "缺資料"),
    ]
    rows.insert(10, make_row("11", esg_total, number(esg_total), classify_esg(esg_total), esg_detail, esg_status))
    for row in rows:
        row["symbol"] = symbol.upper()
    return rows


# ===== 查詢結果保存 =====
# 將一次股票查詢的原始 payload 與每個 KPI row 寫入 SQLite，
# 方便之後在 Streamlit 頁面回查歷史紀錄。
def save_run(symbol: str, company_name: str, payload: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO query_runs (queried_at, symbol, company_name, raw_payload) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), symbol.upper(), company_name, json.dumps(payload, ensure_ascii=False, default=str)),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO kpi_results
            (run_id, kpi_code, kpi_name, value, display_value, judgement, formula, source, detail, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    row["kpi_code"],
                    row["kpi_name"],
                    row["value"],
                    row["display_value"],
                    row["judgement"],
                    row["formula"],
                    row["source"],
                    row["detail"],
                    row["status"],
                )
                for row in rows
            ],
        )
    return run_id


# ===== 歷史紀錄讀取 =====
# 依股票代號與筆數限制讀取最近查詢結果，供頁面下方歷史表格使用。
def load_history(symbol: str | None = None, limit: int = 100) -> pd.DataFrame:
    where = ""
    params: list[Any] = []
    if symbol:
        where = "WHERE r.symbol = ?"
        params.append(symbol.upper())
    params.append(limit)
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                r.id AS run_id,
                r.queried_at,
                r.symbol,
                r.company_name,
                k.kpi_code,
                k.kpi_name,
                k.display_value,
                k.judgement,
                k.status,
                k.detail
            FROM query_runs r
            JOIN kpi_results k ON k.run_id = r.id
            {where}
            ORDER BY r.id DESC, CAST(k.kpi_code AS INTEGER)
            LIMIT ?
            """,
            conn,
            params=params,
        )


# ===== 單次查詢總流程 =====
# 依序抓取 Yahoo、Fintel、MarketBeat、StockCircle，
# 解析各來源資料、計算 KPI、寫入 SQLite，最後回傳 DataFrame 給 UI 顯示。
def run_query(symbol: str, pasted_fintel_text: str = "") -> tuple[int, str, pd.DataFrame, dict[str, Any]]:
    yahoo = fetch_yfinance(symbol)
    fintel_text = pasted_fintel_text.strip()
    if fintel_text:
        fintel_status = "使用手動貼上的 Fintel 文字"
    else:
        fintel_text, fintel_status = fetch_fintel_text(symbol)
    fintel = parse_fintel(fintel_text) if fintel_text else {}
    marketbeat_text, marketbeat_status = fetch_marketbeat_text(symbol, yahoo.get("exchange"))
    marketbeat = parse_marketbeat_short_interest(marketbeat_text) if marketbeat_text else {}
    marketbeat_ownership_text, marketbeat_ownership_status = fetch_marketbeat_ownership_text(symbol, yahoo.get("exchange"))
    marketbeat_ownership = parse_marketbeat_institutional_ownership(marketbeat_ownership_text) if marketbeat_ownership_text else {}
    stockcircle_text, stockcircle_status = fetch_stockcircle_text(symbol)
    stockcircle_esg = parse_stockcircle_esg(stockcircle_text) if stockcircle_text else {}
    yfinance_estimates = estimate_yfinance_advanced_metrics(yahoo)
    rows = make_kpi_rows(
        symbol,
        yahoo,
        fintel,
        fintel_status,
        marketbeat,
        marketbeat_status,
        marketbeat_ownership,
        marketbeat_ownership_status,
        stockcircle_esg,
        stockcircle_status,
    )
    payload = {
        "yfinance": yahoo,
        "fintel": fintel,
        "fintel_status": fintel_status,
        "marketbeat_short_interest": marketbeat,
        "marketbeat_status": marketbeat_status,
        "marketbeat_institutional_ownership": marketbeat_ownership,
        "marketbeat_ownership_status": marketbeat_ownership_status,
        "stockcircle_esg": stockcircle_esg,
        "stockcircle_status": stockcircle_status,
        "yfinance_estimates_for_kpi_4_7": yfinance_estimates,
    }
    run_id = save_run(symbol, yahoo["company_name"], payload, rows)
    return run_id, yahoo["company_name"], pd.DataFrame(rows), payload


# ===== Treeview 報表顯示 =====
# 將 KPI rows 轉成 Streamlit dataframe，模擬 Treeview 的層級與欄位呈現。
def render_treeview(df: pd.DataFrame) -> None:
    view = df[
        ["kpi_code", "kpi_name", "display_value", "judgement", "status", "source", "formula", "detail"]
    ].copy()
    view.insert(0, "tree", view["kpi_code"].map(lambda code: f"KPI {code}"))
    view = view.drop(columns=["kpi_code"])
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "tree": st.column_config.TextColumn("Tree"),
            "kpi_name": st.column_config.TextColumn("Index 指標"),
            "display_value": st.column_config.TextColumn("數值"),
            "judgement": st.column_config.TextColumn("判斷"),
            "status": st.column_config.TextColumn("狀態"),
            "source": st.column_config.TextColumn("來源"),
            "formula": st.column_config.TextColumn("公式"),
            "detail": st.column_config.TextColumn("計算細節"),
        },
    )


# ===== Streamlit 主畫面 =====
# 建立側邊欄查詢表單、KPI 報表區、原始 payload 展開區與歷史紀錄表。
def main() -> None:
    st.set_page_config(page_title="Stock KPI Index Dashboard", layout="wide")
    init_db()

    st.title("Stock KPI Index Dashboard")
    st.caption("輸入股票代號後，計算 KPI 1-10、12-15，並將每次查詢保存到 SQLite。KPI 4-7 優先使用 Fintel，KPI 8-10 使用 MarketBeat Short Interest。")

    with st.sidebar:
        st.header("查詢設定")
        symbol = st.text_input("股票代號", value="AAPL", placeholder="例如 AAPL, NVDA, MU").strip().upper()
        with st.expander("Fintel 備援文字貼上", expanded=False):
            pasted_fintel_text = st.text_area(
                "若 Fintel 自動抓取被阻擋，可貼上 Fintel 頁面 Basic Stats / Ownership / Fund Flow 區塊文字。",
                height=180,
            )
        submitted = st.button("取得 Index 指標", type="primary", use_container_width=True)

    if submitted:
        if not symbol:
            st.error("請輸入股票代號。")
        else:
            with st.spinner(f"正在查詢 {symbol}..."):
                try:
                    run_id, company_name, result_df, payload = run_query(symbol, pasted_fintel_text)
                except Exception as exc:
                    st.error(f"查詢失敗：{exc}")
                else:
                    st.success(f"已完成 {symbol} - {company_name}，並寫入 SQLite run_id={run_id}")
                    st.subheader("Treeview Index 報表")
                    render_treeview(result_df)
                    with st.expander("原始抓取摘要"):
                        st.json(payload)

    st.divider()
    st.subheader("歷史紀錄查詢")
    col1, col2 = st.columns([1, 1])
    with col1:
        history_symbol = st.text_input("歷史紀錄股票代號", value=symbol or "AAPL").strip().upper()
    with col2:
        history_limit = st.number_input("最多顯示筆數", min_value=7, max_value=500, value=77, step=7)

    history_df = load_history(history_symbol, int(history_limit))
    if history_df.empty:
        st.info("目前沒有符合條件的歷史紀錄。")
    else:
        st.dataframe(history_df, use_container_width=True, hide_index=True)

    st.caption(f"SQLite DB: {DB_PATH}")


if __name__ == "__main__":
    main()
