"""
scrapers/redlinetech.py - Redline Technologies Modular Scraper
Engine: requests / curl_cffi + BeautifulSoup (WooCommerce / Custom)
Routing: /category/<cat-slug> or /product-category/
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from scrapers.base_scraper import BaseScraper

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

CATEGORIES = [
    ("GPU", "https://www.redlinetech.lk/product-category/graphics-card/"),
    ("CPU", "https://www.redlinetech.lk/product-category/processors/"),
    ("Motherboard", "https://www.redlinetech.lk/product-category/motherboard/"),
    ("RAM", "https://www.redlinetech.lk/product-category/ram/"),
    ("Storage", "https://www.redlinetech.lk/product-category/storage/"),
    ("PSU", "https://www.redlinetech.lk/product-category/power-supply/"),
    ("Casing", "https://www.redlinetech.lk/product-category/casing/"),
    ("Monitor", "https://www.redlinetech.lk/product-category/monitors/"),
    ("Laptop", "https://www.redlinetech.lk/product-category/laptops/")
]


class RedlineTechScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_name="Redline Technologies", base_url="https://www.redlinetech.lk")

    def fetch(self, url: str):
        if HAS_CURL_CFFI:
            try:
                return c_requests.get(url, impersonate="chrome120", timeout=15)
            except Exception:
                pass
        return requests.get(url, headers=self.get_headers(), timeout=15)

    def scrape(self, max_pages: int = 8):
        print(f"\n[+] Starting Redline Technologies Scraper...")

        for cat_name, cat_url in CATEGORIES:
            print(f" -> Category: [{cat_name}] -> {cat_url}")
            page = 1
            prev_first_title = None

            while page <= max_pages:
                page_url = cat_url if page == 1 else f"{cat_url.rstrip('/')}/page/{page}/"

                try:
                    res = self.fetch(page_url)
                    if res.status_code in [404, 403]:
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    cards = soup.select("li.product, div.product, .type-product, div.product-small, .product-item")
                    if not cards:
                        # Fallback for custom catalog
                        cards = soup.find_all("div", class_=lambda c: c and "product" in c.lower())

                    if not cards:
                        break

                    first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3, a.product-title")
                    first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                    if first_title and first_title == prev_first_title:
                        break
                    prev_first_title = first_title

                    for card in cards:
                        title_el = card.select_one(".woocommerce-loop-product__title, h2, h3, .product-title")
                        price_el = card.select_one(".price ins, .price .amount, .price")
                        link_el = card.select_one("a[href]")

                        title = title_el.get_text(strip=True) if title_el else None
                        price = price_el.get_text(strip=True) if price_el else "N/A"
                        url = urljoin(self.base_url, link_el["href"]) if link_el else ""

                        card_classes = " ".join(card.get("class", []))
                        card_text = card.get_text(separator=" ", strip=True).lower()
                        if "out-of-stock" in card_classes or "out of stock" in card_text:
                            stock = "Out of Stock"
                        else:
                            stock = "In Stock"

                        if title:
                            self.add_product(
                                category=cat_name,
                                title=title,
                                price=price,
                                stock=stock,
                                url=url
                            )

                    page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error requesting {page_url}: {e}")
                    break

        return self.save_csv()


def run(max_pages: int = 8):
    scraper = RedlineTechScraper()
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
