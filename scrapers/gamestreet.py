"""
scrapers/gamestreet.py - Game Street Modular Scraper
Engine: curl_cffi / requests + BeautifulSoup (Custom PHP Catalog)
URLs: products.php?cat=... and product_view.php?pid=...
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base_scraper import BaseScraper

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as c_requests
    HAS_CURL_CFFI = False


class GameStreetScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_name="Game Street", base_url="https://www.gamestreet.lk")
        self.category_queue = []
        self.visited_categories = set()

    def fetch(self, url: str):
        if HAS_CURL_CFFI:
            return c_requests.get(url, impersonate="chrome120", timeout=20)
        return c_requests.get(url, headers=self.get_headers(), timeout=20)

    def discover_categories(self):
        try:
            res = self.fetch(self.base_url)
            if res.status_code != 200:
                return

            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "products.php?cat=" in href:
                    clean_url = urljoin(self.base_url, href).split("#")[0]
                    cat_name = a.get_text(strip=True) or "Hardware"
                    if clean_url not in self.visited_categories and clean_url not in [u for _, u in self.category_queue]:
                        self.category_queue.append((cat_name, clean_url))
        except Exception as e:
            print(f"[!] Error discovering categories: {e}")

    def scrape(self, max_categories: int = 15, max_pages: int = 8):
        print(f"\n[+] Starting Game Street Scraper...")
        self.discover_categories()

        # Fallback categories if menu is dynamic
        if not self.category_queue:
            self.category_queue = [
                ("Graphic Cards", "https://www.gamestreet.lk/products.php?cat=Mg=="),
                ("Processors", "https://www.gamestreet.lk/products.php?cat=MQ=="),
                ("Motherboards", "https://www.gamestreet.lk/products.php?cat=Mw=="),
                ("Memory", "https://www.gamestreet.lk/products.php?cat=NA=="),
                ("Storage", "https://www.gamestreet.lk/products.php?cat=NQ=="),
                ("Power Supply", "https://www.gamestreet.lk/products.php?cat=Ng=="),
                ("Casing", "https://www.gamestreet.lk/products.php?cat=Nw=="),
                ("Monitors", "https://www.gamestreet.lk/products.php?cat=MTA="),
                ("Laptops", "https://www.gamestreet.lk/products.php?cat=MTE=")
            ]

        cats_done = 0
        while self.category_queue and cats_done < max_categories:
            cat_name, cat_url = self.category_queue.pop(0)
            if cat_url in self.visited_categories:
                continue

            self.visited_categories.add(cat_url)
            cats_done += 1
            print(f" -> Category: [{cat_name}] -> {cat_url}")

            page = 1
            prev_first_title = None

            while page <= max_pages:
                page_url = f"{cat_url}&page={page}" if page > 1 else cat_url
                try:
                    res = self.fetch(page_url)
                    if res.status_code in [404, 403]:
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    product_links = soup.find_all("a", href=lambda h: h and "product_view.php?pid=" in h)
                    if not product_links:
                        break

                    first_title = product_links[0].get_text(strip=True)
                    if first_title and first_title == prev_first_title:
                        break
                    prev_first_title = first_title

                    page_items = 0
                    for a in product_links:
                        card = a.find_parent("div", class_=lambda c: c and ("col-" in c or "product" in c)) or a
                        card_text = card.get_text(separator=" ", strip=True)

                        # Extract Title
                        title = a.get_text(strip=True)
                        if not title or len(title) < 3 or "view details" in title.lower():
                            img = card.find("img", alt=True)
                            title = img["alt"].strip() if img else None

                        if not title:
                            continue

                        # Extract Price
                        price_match = re.search(r"(?:Rs\.?|LKR)\s*[\d,]+(?:\.\d{2})?", card_text)
                        price = price_match.group(0) if price_match else "N/A"

                        # Extract URL
                        url = urljoin(self.base_url, a["href"]).split("#")[0]

                        # Stock
                        stock = "Out of Stock" if "out of stock" in card_text.lower() else "In Stock"

                        if self.add_product(
                            category=cat_name,
                            title=title,
                            price=price,
                            stock=stock,
                            url=url
                        ):
                            page_items += 1

                    if page_items == 0:
                        break

                    page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error requesting {page_url}: {e}")
                    break

        return self.save_csv()


def run(max_categories: int = 15, max_pages: int = 8):
    scraper = GameStreetScraper()
    return scraper.scrape(max_categories=max_categories, max_pages=max_pages)


if __name__ == "__main__":
    run(max_categories=2, max_pages=1)
