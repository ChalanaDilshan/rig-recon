import csv
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.nanotek.lk"
START_URL = "https://www.nanotek.lk/category/graphics-card"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class NanotekCrawler:
    def __init__(self, target_categories=None):
        # Crawl කළ යුතු Categories ලැයිස්තුව (Queue)
        self.queue = target_categories or [START_URL]
        self.visited = set()
        self.collected_products = []

    def fetch_page(self, url):
        """HTTP GET request එකක් යවා BeautifulSoup object එකක් ලබා ගනී."""
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            print(f"Failed to fetch {url} (Status: {response.status_code})")
        except requests.RequestException as e:
            print(f"Network error on {url}: {e}")
        return None

    def discover_categories(self, soup):
        """පිටුවේ navigation menu එකෙන් අනෙකුත් category links සොයා ගනී."""
        discovered = []
        # Header/Navigation එකේ ඇති සියලු category links සෙවීම
        category_links = soup.select("a[href*='/category/']")
        
        for link in category_links:
            href = link.get("href")
            full_url = urljoin(BASE_URL, href)
            # Graphics card, Processor, RAM වැනි category URLs පමණක් පෙරීම
            if "/category/" in full_url and full_url not in self.visited and full_url not in self.queue:
                discovered.append(full_url)
                self.queue.append(full_url)
                
        print(f"Discovered {len(discovered)} new category URLs.")

    def parse_products(self, soup, current_url):
        """අදාළ category පිටුවේ ඇති සියලුම භාණ්ඩ extract කරයි."""
        category_name = current_url.split("/category/")[-1].replace("-", " ").title()
        product_items = soup.find_all("li", class_="ty-catPage-productListItem")
        
        print(f"[{category_name}] Found {len(product_items)} items.")

        for item in product_items:
            title_tag = item.find("div", class_="ty-productBlock-title")
            price_tag = item.find("div", class_="ty-productBlock-price")
            link_tag = item.find("a", href=True)
            special_msg = item.find("div", class_="ty-productBlock-specialMsg")

            title = title_tag.get_text(strip=True) if title_tag else "N/A"
            price = price_tag.get_text(strip=True) if price_tag else "N/A"
            product_url = urljoin(BASE_URL, link_tag["href"]) if link_tag else "N/A"
            stock = special_msg.get_text(strip=True) if special_msg else "In Stock"

            self.collected_products.append({
                "Category": category_name,
                "Title": title,
                "Price": price,
                "Stock": stock,
                "URL": product_url
            })

    def run(self, max_categories=5):
        """Crawler එක ක්‍රියාත්මක කිරීම."""
        crawled_count = 0

        while self.queue and crawled_count < max_categories:
            current_url = self.queue.pop(0)

            if current_url in self.visited:
                continue

            print(f"\nCrawling [{crawled_count + 1}/{max_categories}]: {current_url}")
            soup = self.fetch_page(current_url)
            self.visited.add(current_url)

            if soup:
                # 1. Menu එකෙන් තවත් categories සොයා ගැනීම (Link Discovery)
                self.discover_categories(soup)
                
                # 2. අදාළ පිටුවේ භාණ්ඩ extract කිරීම
                self.parse_products(soup, current_url)

            crawled_count += 1
            # Server එකට බරක් නොවීමට තත්පර 2ක විවේකයක් (Politeness delay)
            time.sleep(2)

        self.export_to_csv()

    def export_to_csv(self, filename="nanotek_multi_category.csv"):
        if not self.collected_products:
            print("No data collected.")
            return

        keys = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.collected_products)

        print(f"\n✅ Crawling complete! {len(self.collected_products)} total items saved to '{filename}'.")

if __name__ == "__main__":
    # ඔබ කැමති categories කිහිපයක් පමණක් crawl කිරීමට නම් මෙසේ ලබා දිය හැක:
    TARGET_CATEGORIES = [
        "https://www.nanotek.lk/category/graphics-card",
        "https://www.nanotek.lk/category/processor",
        "https://www.nanotek.lk/category/motherboards"
    ]
    
    # max_categories මඟින් crawl කරන උපරිම පිටු ගණන පාලනය කළ හැක
    crawler = NanotekCrawler(target_categories=TARGET_CATEGORIES)
    crawler.run(max_categories=3)