"""
工具流派一：老牌瀏覽器自動化——【Top 4: Selenium】(Python)
與 Playwright 類似，Selenium 是最經典的自動化工具，能完全模擬真人打開瀏覽器，因此能成功將動態 JS 渲染出來。
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def fetch_with_selenium_fixed():
    url = "https://stockcircle.com/stocks/aapl"
    
    # 設定 Chrome 瀏覽器參數
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # 背景執行
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    print("【Selenium】正在啟動 Chrome 瀏覽器並加載網頁...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(url)
        print("等待 5 秒讓 JavaScript 完整渲染...")
        time.sleep(5)
        
        # 獲取渲染完畢後的完整網頁原始碼
        page_source = driver.page_source
        
    except Exception as e:
        print(f"瀏覽器請求發生錯誤: {e}")
        page_source = None
    finally:
        driver.quit()
        
    if page_source:
        print("瀏覽器任務完成，交給 BeautifulSoup 解析 HTML...")
        # 結合您剛剛測試成功的 BeautifulSoup 機制
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # 尋找包含 "ESG Score" 的標題
        esg_heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 'ESG Score' in tag.text)
        
        if not esg_heading:
            print("依舊找不到 ESG Score 區塊，可能網頁結構在 headless 模式下有變。")
            return
            
        print(f"=== {esg_heading.text.strip()} ===")
        
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
    fetch_with_selenium_fixed()