import requests
from bs4 import BeautifulSoup

def fetch_aapl_esg_score():
    # 目標 URL
    url = "https://stockcircle.com/stocks/aapl"
    
    # 設定 User-Agent 模擬真人瀏覽器行為，避免被視為惡意爬蟲
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    try:
        # 發送 GET 請求
        response = requests.get(url, headers=headers, timeout=10)
        
        # 檢查請求是否成功
        if response.status_code != 200:
            print(f"無法取得網頁，狀態碼: {response.status_code}")
            return
        
        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找包含 "ESG Score" 的標題（該網頁通常使用 <h2> 或 <h3>）
        # 根據 Stockcircle 的結構，我們尋找 text 包含 'ESG Score' 的標籤
        esg_heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 'ESG Score' in tag.text)
        
        if not esg_heading:
            print("找不到 ESG Score 區塊，網頁結構可能已改變，或遭遇 JavaScript 動態渲染限制。")
            return
        
        print(f"=== {esg_heading.text.strip()} ===")
        
        # 通常數據會放在標題下方的 table 或 div 之中
        # 我們尋找該標題後面的第一個 table 標籤
        esg_table = esg_heading.find_next('table')
        
        if esg_table:
            # 遍歷表格中的每一行
            rows = esg_table.find_all('tr')
            for row in rows:
                cols = row.find_all(['td', 'th'])
                if len(cols) >= 2:
                    metric = cols[0].text.strip()
                    score = cols[1].text.strip()
                    print(f"{metric}: {score}")
        else:
            # 如果不是表格，嘗試抓取下一個同級區塊的文字
            next_node = esg_heading.find_next_sibling()
            if next_node:
                print(next_node.text.strip())
                
    except Exception as e:
        print(f"爬取過程中發生錯誤: {e}")

if __name__ == "__main__":
    fetch_aapl_esg_score()