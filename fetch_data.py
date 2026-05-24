import requests
from config import config


class NewsFetcher:
    def __init__(self):
        # 从config中获取的参数作为成员属性
        self.domestic_url = config['domestic_url']
        self.foreign_url = config['foreign_url']
        self.domestic_api_key = config['domestic_api_key']
        self.domestic_num = config['domestic_num']
        self.foreign_api_key = config['foreign_api_key']
        self.host = config['host']
        self.content_type = config['content_type']
        
        # 代码中的变量参数作为成员属性
        self.params = {
            'key': self.domestic_api_key,
            'num': self.domestic_num
        }
        
        self.querystring = {
            "story": "CAAqNggKIjBDQklTSGpvSmMzUnZjbmt0TXpZd1NoRUtEd2pibk5UN0VCSDVpWndxM3pJc0hDZ0FQAQ",
            "sort": "RELEVANCE",
            "country": "US",
            "lang": "en"
        }
        
        self.headers = {
            "x-rapidapi-key": self.foreign_api_key,
            "x-rapidapi-host": self.host,
            "Content-Type": self.content_type
        }
    
    def fetch_domestic_news(self) -> list[dict]:
        """
        从天行API获取国内财经新闻
        :return: 国内财经新闻列表
        """
        response = requests.get(self.domestic_url, params=self.params)
        data = response.json()
        raw_newslist = data['result']['newslist']
        newslist = []
        for item in raw_newslist:
            news = {
                '标题+具体内容': item['title'] + '|' + item['description'],
                '时间': item['ctime'],
                '来源': item['source']
            }
            newslist.append(news)
        
        return newslist
    
    def fetch_foreign_news(self) -> list[dict]:
        """
        从 RapidAPI 获取国外财经新闻
        :return: 国外财经新闻数据
        """
        try:
            # 发送 GET 请求
            response = requests.get(self.foreign_url, headers=self.headers, params=self.querystring)
            
            # 检查响应状态并解析数据
            response.raise_for_status()
            data = response.json()
            data = data['data']['all_articles']
            newslist = []
            for item in data:
                if item['title'] and item['snippet']:
                    news = {
                        '标题+具体内容': item['title'] + '|' + item['snippet'],
                        '时间': item['published_datetime_utc'],
                        '来源': item['source_name']
                    }
                    newslist.append(news)
            
            return newslist
        
        except requests.exceptions.RequestException as e:
            print(f"请求出错了: {e}")
            return None


if __name__ == '__main__':
    fetcher = NewsFetcher()
    # newslist = fetcher.fetch_domestic_news()
    # print(newslist)
    newslist = fetcher.fetch_foreign_news()
    print(newslist)
