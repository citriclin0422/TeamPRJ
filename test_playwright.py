import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def fetch_aapl_esg_with_playwright():
    url = "https://stockcircle.com/stocks/aapl"
    
    # 啟動 Playwright 環境
    with sync_playwright() as p:
        # 啟動 Chromium 瀏覽器（headless=True 代表在背景執行，不跳出視窗）
        browser = p.chromium.launch(headless=True)
        
        # 建立新分頁，並設定 User-Agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("正在開啟網頁並等待動態資料渲染...")
        # 前往目標網頁，並等待網路完全閒置（代表 JS 動態資料載入完畢）
        page.goto(url, wait_until="networkidle")
        
        # 保險起見，多給它額外 3 秒確保 ESG 區塊渲染出來
        time.sleep(3)
        
        # 取得渲染完成後的完整網頁 HTML 原始碼
        html_content = page.content()
        
        # 關閉瀏覽器釋放資源
        browser.close()
        
    # 接下來交給 BeautifulSoup 進行解析
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 尋找包含 ESG Score 的標題
    esg_heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 'ESG Score' in tag.text)
    
    if not esg_heading:
        print("依舊找不到 ESG Score 區塊。請檢查該網站是否需要登入，或區塊名稱是否已變更。")
        return

    print(f"=== {esg_heading.text.strip()} ===")
    
    # 尋找標題下方的表格數據
    esg_table = esg_heading.find_next('table')
    
    if esg_table:
        rows = esg_table.find_all('tr')
        data_found = False
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 2:
                metric = cols[0].text.strip()
                score = cols[1].text.strip()
                print(f"{metric}: {score}")
                data_found = True
        
        if not data_found:
            print("表格內沒有任何數據。")
    else:
        # 如果不是以 table 呈現，嘗試抓取下一個兄弟節點的文字
        next_node = esg_heading.find_next_sibling()
        if next_node:
            print(next_node.text.strip())
        else:
            print("No data (找不到表格或對應文字區塊)")

if __name__ == "__main__":
    fetch_aapl_esg_with_playwright()