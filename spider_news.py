import time
import requests
# BeautifulSoup 是一个用于解析 HTML 和 XML 文档的 Python 库，能够方便地从网页中提取数据
from bs4 import BeautifulSoup


class NewsSpider:
    def __init__(self):
        """初始化爬虫类"""
        self.news_list = []
        self.URL = "https://mil.huanqiu.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_news_list(self)->list[dict]:
        """解析列表页，获取所有新闻的标题、代号和拼接后的 URL"""
        self.news_list = []
        try:
            # 发送网络请求获取列表页 HTML
            response = requests.get(self.URL, headers=self.headers, timeout=10)
            response.encoding = "utf-8"  # 确保中文不乱码
            # 使用 BeautifulSoup 解析 HTML 内容，"html.parser" 是 Python 内置的 HTML 解析器
            soup = BeautifulSoup(response.text, "html.parser")

            # 找到所有包含新闻信息的 item 节点，返回一个可迭代对象
            items = soup.find_all("div", class_="item")

            for item in items:
                # 提取新闻代号 (aid) 和标题 (title)
                aid_tag = item.find("textarea", class_="item-aid")
                title_tag = item.find("textarea", class_="item-title")

                if aid_tag and title_tag:
                    aid = aid_tag.text.strip()
                    title = title_tag.text.strip()

                    # 动态拼接具体新闻的真实 URL
                    detail_url = f"https://mil.huanqiu.com/article/{aid}"

                    self.news_list.append({"title": title, "aid": aid, "url": detail_url})

            return self.news_list

        except Exception as e:
            print(f"提取列表页失败: {e}")
            return self.news_list

    def crawl_detail_page(self, detail_url)->str:
        """自动切换，访问具体新闻详情页，提取精准正文"""

        try:
            print(f"正在自动切换并抓取: {detail_url}")
            response = requests.get(detail_url, headers=self.headers, timeout=10)
            response.encoding = "utf-8"

            soup = BeautifulSoup(response.text, "html.parser")

            # 精准定位：根据HTML 结构，正文在 class_="article-content" 的 textarea 标签中
            content_textarea = soup.find("textarea", class_="article-content")

            if content_textarea:
                # 关键点：textarea 内部包裹的是 HTML 字符串，需要再次用 BeautifulSoup 解析它
                inner_html = content_textarea.text
                inner_soup = BeautifulSoup(inner_html, "html.parser")

                # 提取内部所有的 p 标签
                paragraphs = inner_soup.find_all("p")
                text = "\n".join(
                    [p.text.strip() for p in paragraphs if p.text.strip()]
                )
                return text
            else:
                # 兜底逻辑：如果特殊提取失败，尝试常规的全局 p 标签提取
                paragraphs = soup.find_all("p")
                text = "\n".join(
                    [p.text.strip() for p in paragraphs if p.text.strip()]
                )
                return text

        except Exception as e:
            print(f"抓取详情页失败 {detail_url}: {e}")
            return ""


if __name__ == "__main__":
    spider = NewsSpider()
    news_list = spider.get_news_list()
    print(f"成功提取到 {len(spider.news_list)} 条新闻！\n")
    for news in spider.news_list[:6]:
        text = spider.crawl_detail_page(news['url'])
        print(f"【抓取正文片段】:\n{text[:200]}")
        print(f"【抓取正文长度】: {len(text)}")
        time.sleep(2)
        print("-" * 50)
