import time
import requests
from datetime import datetime
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

    def _convert_timestamp(self, ts_str: str) -> str:
        """内部辅助函数：将13位毫秒时间戳字符串转换为 xxxx-xx-xx 格式"""
        try:
            if not ts_str:
                return "未知"
            # 环球网使用的是13位毫秒时间戳，需要转换为10位秒级时间戳
            ts_float = float(ts_str.strip()) / 1000.0
            # 格式化为 年-月-日
            return datetime.fromtimestamp(ts_float).strftime("%Y-%m-%d")
        except Exception:
            # 如果转换失败（比如数据格式异常），返回默认兜底值
            return "未知"

    def get_news_list(self) -> list[dict]:
        """解析列表页，获取所有新闻的标题、代号、拼接后的 URL 以及发布时间"""
        self.news_list = []
        try:
            # 发送网络请求获取列表页 HTML
            response = requests.get(self.URL, headers=self.headers, timeout=10)
            response.encoding = "utf-8"  # 确保中文不乱码
            # 使用 BeautifulSoup 解析 HTML 内容
            soup = BeautifulSoup(response.text, "html.parser")

            # 找到所有包含新闻信息的 item 节点
            items = soup.find_all("div", class_="item")

            for item in items:
                # 提取新闻代号 (aid)、标题 (title) 和发布时间戳 (time)
                aid_tag = item.find("textarea", class_="item-aid")
                title_tag = item.find("textarea", class_="item-title")
                time_tag = item.find("textarea", class_="item-time")  # 对应HTML源码中的 item-time

                if aid_tag and title_tag:
                    aid = aid_tag.text.strip()
                    title = title_tag.text.strip()

                    # 提取并转换时间戳
                    raw_time = time_tag.text.strip() if time_tag else ""
                    formatted_time = self._convert_timestamp(raw_time)

                    # 动态拼接具体新闻的真实 URL
                    detail_url = f"https://mil.huanqiu.com/article/{aid}"

                    # 在字典中加入转换后的发布时间，格式为 xxxx-xx-xx
                    self.news_list.append(
                        {
                            "title": title,
                            "aid": aid,
                            "url": detail_url,
                            "publish_time": formatted_time,  # 新增的时间字段
                        }
                    )

            return self.news_list

        except Exception as e:
            print(f"提取列表页失败: {e}")
            return self.news_list


    def crawl_detail_page(self, detail_url) -> str:
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
                    [
                        p.text.strip()
                        for p in paragraphs
                        if p.text.strip()
                    ]
                )
                return text
            else:
                # 兜底逻辑：如果特殊提取失败，尝试常规的全局 p 标签提取
                paragraphs = soup.find_all("p")
                text = "\n".join(
                    [
                        p.text.strip()
                        for p in paragraphs
                        if p.text.strip()
                    ]
                )
                return text

        except Exception as e:
            print(f"抓取详情页失败 {detail_url}: {e}")
            return ""


if __name__ == "__main__":
    spider = NewsSpider()
    news_list = spider.get_news_list()
    print(f"成功提取到 {len(spider.news_list)} 条新闻！\n")
    for news in spider.news_list[3:6]:
        publish_time = news['publish_time']
        print(f"【发布时间】: {publish_time}")
        text = spider.crawl_detail_page(news['url'])
        text_to_send = f"时间：{publish_time}\n{text}"
        print(f"【抓取正文片段】:\n{text_to_send[:200]}")
        print(f"【抓取正文长度】: {len(text_to_send)}")
        time.sleep(2)
        print("-" * 50)
