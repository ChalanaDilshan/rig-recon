"""
scrapers/chamacomputers.py - Chama Computers Modular Scraper
Engine: Playwright (Client-Side Rendered / React)
Patterns: /products/<category>?page={n}, regex price matching
"""

import re
import time
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base_scraper import BaseScraper

TARGET_CATEGORIES = [
    ("GPU", "https://www.chamacomputers.lk/products/graphics%20cards"),
    ("CPU", "https://www.chamacomputers.lk/products/processors"),
    ("Motherboard", "https://www.chamacomputers.lk/products/motherboards"),
    ("RAM", "https://www.chamacomputers.lk/products/memory"),
    ("PSU", "https://www.chamacomputers.lk/products/power%20supply"),
    ("Monitor", "https://www.chamacomputers.lk/products/monitors%20%26%20displays"),
    ("Laptop", "https://www.chamacomputers.lk/products/laptops")
]


class ChamaScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Chama Computers", base_url="https://www.chamacomputers.lk")
        self.headless = headless

    def scrape(self, max_pages_per_category: int = 10):
        print(f"\n[+] Starting Chama Computers Scraper...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=self.get_headers()["User-Agent"]
            )
            page = context.new_page()

            for cat_name, cat_url in TARGET_CATEGORIES:
                print(f" -> Category: [{cat_name}] -> {cat_url}")
                current_page = 1

                while current_page <= max_pages_per_category:
                    page_url = f"{cat_url}?page={current_page}"
                    try:
                        res = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        if res and res.status in [404, 403]:
                            break

                        time.sleep(1.5)  # Wait for React to render product cards

                        soup = BeautifulSoup(page.content(), "html.parser")
                        product_links = soup.find_all("a", href=True)
                        page_items = 0

                        for link in product_links:
                            href = link["href"]
                            parts = [p for p in href.split("?")[0].split("/") if p]
                            if len(parts) >= 3 and parts[0] == "products":
                                full_url = urljoin(self.base_url, href).split("?")[0]
                                card_text = link.get_text(separator=" ", strip=True)

                                price_match = re.search(r"Rs\.?\s*([\d,]+(?:\.\d{2})?)", card_text)
                                if not price_match:
                                    continue
                                price = f"Rs. {price_match.group(1)}"

                                img_tag = link.find("img")
                                img_alt = img_tag.get("alt", "").strip() if img_tag else ""
                                raw_title = img_alt if img_alt else card_text.split("Rs.")[0].strip()
                                title = re.sub(r"^(In Stock|Out of Stock|New|Sale)\s*", "", raw_title, flags=re.IGNORECASE).strip()

                                if not title or len(title) < 4:
                                    continue

                                lower_text = card_text.lower()
                                stock = "Out of Stock" if "out of stock" in lower_text else "In Stock"

                                if self.add_product(
                                    category=cat_name,
                                    title=title,
                                    price=price,
                                    stock=stock,
                                    url=full_url
                                ):
                                    page_items += 1

                        if page_items == 0:
                            break

                        current_page += 1
                        self.sleep_polite()

                    except Exception as e:
                        print(f"    [!] Error crawling {page_url}: {e}")
                        break

            browser.close()

        return self.save_csv()


def run(max_pages: int = 10, headless: bool = True):
    scraper = ChamaScraper(headless=headless)
    return scraper.scrape(max_pages_per_category=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
