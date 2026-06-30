"""
工具流派三：高速 HTML 解析引擎——【Top 9: BeautifulSoup + lxml】(Python)
當您使用流派二（Requests 拿到 API 產出的純 HTML 文本）或是流派一（瀏覽器吐出的 Page Content）時，如果您需要對極其龐大的 HTML 進行高速解析，預設的 html.parser 會很慢。此時將底層換成 C 語言編寫的 lxml，效能會大幅提升。
"""
from bs4 import BeautifulSoup

# 模擬我們已經從 Playwright 或某處拿到了「完整的、渲染好的 HTML 文字」
mock_rendered_html = """
<html>
    <body>
        <h2>ESG Score</h2>
        <table>
            <tr><td>Environment</td><td>66 / 100</td></tr>
            <tr><td>Social</td><td>45 / 100</td></tr>
            <tr><td>Governance</td><td>59 / 100</td></tr>
            <tr><td>Total</td><td>57 / 100</td></tr>
        </table>
    </body>
</html>
"""

def parse_with_lxml():
    print("【BeautifulSoup + lxml】正在以 C 語言級別的速度解析 HTML...")
    # 關鍵點：在這裡指定解析器為 'lxml' 而非 'html.parser'
    soup = BeautifulSoup(mock_rendered_html, "lxml")
    
    title = soup.find("h2").text
    print(f"=== {title} ===")
    
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) == 2:
            print(f"{cols[0].text}: {cols[1].text}")

if __name__ == "__main__":
    parse_with_lxml()