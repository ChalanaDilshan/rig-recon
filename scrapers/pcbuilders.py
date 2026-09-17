"""
scrapers/pcbuilders.py - PC Builders Modular Scraper
Engine: requests / curl_cffi + BeautifulSoup (WooCommerce)
Pagination: /page/{n}/ with duplicate-title loop detection
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base_scraper import BaseScraper

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

CATEGORIES = [
    ("GPU", "https://pcbuilders.lk/product-category/graphic-cards/"),
    ("CPU", "https://pcbuilders.lk/product-category/processors/"),
    ("Motherboard", "https://pcbuilders.lk/product-category/motherboards/"),
    ("RAM", "https://pcbuilders.lk/product-category/ram/"),
    ("Storage", "https://pcbuilders.lk/product-category/storage/"),
    ("PSU", "https://pcbuilders.lk/product-category/power-supplies/"),
    ("Casing", "https://pcbuilders.lk/product-category/casings/"),
    ("Monitor", "https://pcbuilders.lk/product-category/monitors/")
]


class PCBuildersScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_name="PC Builders", base_url="https://pcbuilders.lk")

    def fetch(self, url: str):
        if HAS_CURL_CFFI:
            try:
                return c_requests.get(url, impersonate="chrome120", timeout=15)
            except Exception:
                pass
        return requests.get(url, headers=self.get_headers(), timeout=15)

    def scrape(self, max_pages: int = 10):
        print(f"\n[+] Starting PC Builders Scraper...")

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
                    cards = soup.select("li.product, div.product, .type-product")
                    if not cards:
                        break

                    first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3, .product-title")
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


def run(max_pages: int = 10):
    scraper = PCBuildersScraper()
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
