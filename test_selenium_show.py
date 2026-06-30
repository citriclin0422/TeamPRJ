"""
工具流派一：老牌瀏覽器自動化——【Top 4: Selenium】(Python)
與 Playwright 類似，Selenium 是最經典的自動化工具，能完全模擬真人打開瀏覽器，因此能成功將動態 JS 渲染出來。
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def fetch_with_selenium_visible():
    url = "https://stockcircle.com/stocks/aapl"
    
    # 設定 Chrome 瀏覽器參數
    options = webdriver.ChromeOptions()
    
    # 【關鍵修正】註銷掉原本的 --headless 模式，讓瀏覽器跳出視窗（模擬完全正常的真人操作）
    # options.add_argument("--headless") 
    
    # 移除反爬蟲特徵與設定視窗大小
    options.add_argument("--window-size=1280,800")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    # 排除自動化控制的特徵標籤
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    print("【Selenium】正在啟動 Chrome 實體瀏覽器並加載網頁...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # 執行腳本隱藏 webdriver 特徵
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    page_source = None
    try:
        driver.get(url)
        
        print("正在等待網頁加載（最多等 15 秒）...")
        # 動態等待：直到網頁中出現包含 "ESG Score" 文字的元素為止才繼續
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'ESG Score')]"))
        )
        
        # 額外多停 2 秒確保資料完全填入
        time.sleep(2)
        
        # 獲取渲染完畢後的完整網頁原始碼
        page_source = driver.page_source
        print("【成功】動態資料已完成加載，正在關閉瀏覽器並解析...")
        
    except Exception as e:
        print(f"瀏覽器請求或等待逾時錯誤: {e}")
    finally:
        driver.quit()
        
    if page_source:
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # 尋找包含 "ESG Score" 的標題
        esg_heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 'ESG Score' in tag.text)
        
        if not esg_heading:
            print("依舊找不到 ESG Score 區塊，請確認瀏覽器開啟時頁面是否顯示正常。")
            return
            
        print(f"\n=== {esg_heading.text.strip()} ===")
        
        # 尋找標題下方的表格數據
        esg_table = esg_heading.find_next('table')
        
        if esg_table:
            rows = esg_table.find_all('tr')
            for row in rows:
                cols = row.find_all(['td', 'th'])
                if len(cols) >= 2:
                    metric = cols[0].text.strip()
                    score = cols[1].text.strip()
                    print(f"{metric}: {score}")
        else:
            print("未能定位到資料表格。")

if __name__ == "__main__":
    fetch_with_selenium_visible()