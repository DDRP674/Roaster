import logging
import requests
from bs4 import BeautifulSoup
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import func_name

# 这个库用于网络搜索的相关工具。我们可以只实现对一个网站的搜索

class Crawler:
    def __init__(self, website: str = "https://www.baidu.com/s?wd={query}"):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.website = website
    
    def search(self, query: str, max_results: int = 3) -> list[dict]:
        """搜索，返回搜索结果列表"""
        try:
            search_url = self.website.format(query=requests.utils.quote(query))
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                logging.warning(f"搜索请求失败，状态码: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            if 'baidu.com' in self.website: results = self._parse_baidu(soup, max_results)
            elif 'bing.com' in self.website: results = self._parse_bing(soup, max_results)
            else: results = self._parse_generic(soup, max_results)
            
            logging.info(f"搜索到 {len(results)} 条结果")
            return results
            
        except Exception as e:
            logging.error(f"搜索过程中发生错误: {e}")
            return []
    
    def _parse_baidu(self, soup, max_results):
        """百度"""
        results = []
        for result in soup.find_all('div', class_='result', limit=max_results):
            try:
                title_elem = result.find('h3') or result.find('a')
                snippet_elem = result.find('div', class_='c-abstract') or result.find('div', class_='content-right_2sSWR')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    # 处理百度相对链接
                    if url.startswith('/'):
                        url = 'https://www.baidu.com' + url
                    
                    results.append({
                        "title": title,
                        "snippet": snippet,
                        "url": url
                    })
            except Exception as e:
                logging.warning(f"解析百度结果失败: {e}")
                continue
        return results
    
    def _parse_bing(self, soup, max_results):
        """必应"""
        results = []
        for result in soup.find_all('li', class_='b_algo', limit=max_results):
            try:
                title_elem = result.find('h2')
                snippet_elem = result.find('p')
                url_elem = result.find('a')
                
                if title_elem and url_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    url = url_elem.get('href', '')
                    
                    results.append({
                        "title": title,
                        "snippet": snippet,
                        "url": url
                    })
            except Exception as e:
                logging.warning(f"解析必应结果失败: {e}")
                continue
        return results
    
    def _parse_generic(self, soup, max_results):
        """通用解析方法"""
        results = []
        selectors = [
            'div.result', 'li.result', 'div.search-result', 'li.search-result',
            'div.g', 'div.rc', 'div.res', 'li.res', 'div.web-result', 'article'
        ]
        
        for selector in selectors:
            elements = soup.find_all(selector, limit=max_results)
            if elements:
                for element in elements:
                    try:
                        title_elem = (element.find('h3') or element.find('h2') or 
                                    element.find('a') or element.find('span'))
                        snippet_elem = (element.find('p') or element.find('span') or 
                                      element.find('div', class_=True))
                        
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            url = title_elem.get('href', '') if title_elem.name == 'a' else ''
                            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                            
                            if title: 
                                results.append({
                                    "title": title,
                                    "snippet": snippet,
                                    "url": url
                                })
                    except Exception:
                        continue
                if results: 
                    break
        
        return results[:max_results]
        
    def get_content(self, url: str, max_length: int = 1000) -> str:
        """获取网页的主要文本内容"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return ""
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())
            
            return text[:max_length]
            
        except Exception as e:
            logging.warning(f"{func_name()}: 获取网页内容失败: {e}")
            return ""

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    c = Crawler("https://cn.bing.com/search?q={query}")
    print(c.search("董卓", max_results=2))