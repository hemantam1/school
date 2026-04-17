import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json

class SmartCrawler:
    def __init__(self, base_url, max_depth=2, delay=1):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.delay = delay
        self.visited = set()
        self.queue = [(self.base_url, 0)]

        self.skip_keywords = {"login", "signup", "cart", "checkout", "wp-admin", ".pdf", ".jpg", ".zip"}
        self.allowed_keywords = {"about", "course", "program", "admission", "faculty", "contact", "enrichment"}

    def normalize_url(self, url):
        return url.split("#")[0].rstrip("/")

    def is_internal(self, url):
        return self.domain in urlparse(url).netloc

    def fetch(self, url):
        try:
            res = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if res.status_code == 200 and "text/html" in res.headers.get("Content-Type", ""):
                return res.text
            return None
        except Exception as e:
            print(f"❌ Error fetching {url}: {e}")
            return None

    # -------------------------------------------------------
    # MODIFIED: Specific Information Extraction Logic
    # -------------------------------------------------------
    def extract_structured_data(self, html):
        soup = BeautifulSoup(html, "html.parser")
        data = {}

        # 1. Title/Name Scraping
        data['name'] = soup.find('h1').get_text(strip=True) if soup.find('h1') else "N/A"

        # 2. Extract Institution Details (Tables ya Lists se)
        details = {}
        # Tables search karein (jaisa aapne data diya hai)
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cols = row.find_all(['td', 'th'])
                if len(cols) == 2:
                    key = cols[0].get_text(strip=True)
                    val = cols[1].get_text(strip=True)
                    details[key] = val
        data['institution_details'] = details

        # 3. Extract Assessment/Outcomes (Section headings ke basis par)
        sections = {}
        for heading in soup.find_all(['h2', 'h3']):
            title = heading.get_text(strip=True)
            # Agla paragraph ya div content uthao
            content = []
            next_node = heading.find_next_sibling()
            while next_node and next_node.name not in ['h2', 'h3']:
                if next_node.name in ['p', 'div', 'ul']:
                    content.append(next_node.get_text(separator=" ", strip=True))
                next_node = next_node.find_next_sibling()
            sections[title] = " ".join(content)
        
        data['sections'] = sections
        return data

    def extract_links(self, html):
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for tag in soup.find_all("a", href=True):
            full_url = self.normalize_url(urljoin(self.base_url, tag["href"]))
            if self.is_internal(full_url) and full_url not in self.visited:
                links.append(full_url)
        return links

    def crawl(self):
        all_results = []
        
        while self.queue:
            url, depth = self.queue.pop(0)
            url = self.normalize_url(url)

            if url in self.visited or depth > self.max_depth:
                continue

            print(f"🔍 Scraping: {url}")
            self.visited.add(url)

            html = self.fetch(url)
            if not html: continue

            # Extracting Specific Information
            page_data = self.extract_structured_data(html)
            page_data['url'] = url
            all_results.append(page_data)

            # Print current page data in clean format
            print(f"--- Data found for {page_data['name']} ---")
            print(json.dumps(page_data, indent=2))

            # Next links
            for link in self.extract_links(html):
                self.queue.append((link, depth + 1))

            time.sleep(self.delay)
        
        return all_results

if __name__ == "__main__":
    # Aapka target URL yaha change karein
    crawler = SmartCrawler(
        base_url="http://wetherbyschool.co.uk", 
        max_depth=1, 
        delay=2
    )
    results = crawler.crawl()