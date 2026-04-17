import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time


class SmartCrawler:
    def __init__(self, base_url, max_depth=2, delay=1):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc

        self.max_depth = max_depth
        self.delay = delay

        self.visited = set()
        self.queue = [(self.base_url, 0)]

        # 🔴 Blacklist (skip junk URLs)
        self.skip_keywords = {
            "login", "signup", "cart", "checkout",
            "wp-admin","team", "wp-login",
            "mailto:", "tel:",
            ".pdf", ".jpg", ".png", ".zip",
            "?reply", "?share", "?utm"
        }

        # 🟢 Whitelist (focus pages) — optional but powerful
        self.allowed_keywords = {
            "about", "course", "program",
            "admission", "faculty", "contact"
        }

    # -------------------------------
    # URL HELPERS
    # -------------------------------
    def normalize_url(self, url):
        return url.split("#")[0].rstrip("/")

    def is_internal(self, url):
        return self.domain in urlparse(url).netloc

    def is_valid(self, url):
        url_lower = url.lower()

        # Skip unwanted patterns
        if any(word in url_lower for word in self.skip_keywords):
            return False

        return True

    def is_relevant(self, url):
        url_lower = url.lower()
        return any(word in url_lower for word in self.allowed_keywords)

    # -------------------------------
    # FETCH PAGE
    # -------------------------------
    def fetch(self, url):
        try:
            res = requests.get(url, timeout=5)

            if "text/html" not in res.headers.get("Content-Type", ""):
                return None

            return res.text

        except Exception as e:
            print(f"❌ Error fetching {url}: {e}")
            return None

    # -------------------------------
    # PARSE CONTENT
    # -------------------------------
    def extract_text(self, html):
        soup = BeautifulSoup(html, "html.parser")

        # Remove junk tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Skip thin pages
        if len(text) < 200:
            return None

        return text

    # -------------------------------
    # EXTRACT LINKS
    # -------------------------------
    def extract_links(self, html):
        soup = BeautifulSoup(html, "html.parser")
        links = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            full_url = self.normalize_url(urljoin(self.base_url, href))

            if (
                self.is_internal(full_url)
                and self.is_valid(full_url)
                and full_url not in self.visited
            ):
                links.append(full_url)

        return links

    # -------------------------------
    # MAIN CRAWLER
    # -------------------------------
    def crawl(self):
        while self.queue:
            url, depth = self.queue.pop(0)

            url = self.normalize_url(url)

            if url in self.visited or depth > self.max_depth:
                continue

            print(f"\n🔍 Crawling: {url}")
            self.visited.add(url)

            html = self.fetch(url)
            if not html:
                continue

            text = self.extract_text(html)
            if not text:
                continue

            # 🎯 Print limited content
            print(text)

            # Extract and enqueue links
            links = self.extract_links(html)

            for link in links:
                # OPTIONAL: only crawl relevant pages
                if self.is_relevant(link):
                    self.queue.append((link, depth + 1))

            # ⏳ Rate limiting
            time.sleep(self.delay)


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    crawler = SmartCrawler(
        base_url="http://wetherbyschool.co.uk",
        max_depth=2,
        delay=1
    )

    crawler.crawl() 