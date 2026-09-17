"""
scrapers/techzone.py - Techzone.lk Modular Scraper
Engine: curl_cffi (impersonate="chrome120") + BeautifulSoup with Playwright fallback for Cloudflare
Pagination: /page/{n}/
"""

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base_scraper import BaseScraper

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as c_requests
    HAS_CURL_CFFI = False

CATEGORIES = [
    ("GPU", "https://techzone.lk/product-category/computer-components/graphic-card/"),
    ("CPU", "https://techzone.lk/product-category/computer-components/processor/"),
    ("Motherboard", "https://techzone.lk/product-category/computer-components/motherboard/"),
    ("RAM", "https://techzone.lk/product-category/computer-components/memory-ram/"),
    ("Storage", "https://techzone.lk/product-category/storage/"),
    ("PSU", "https://techzone.lk/product-category/computer-components/power-supply/"),
    ("Casing", "https://techzone.lk/product-category/computer-components/casing/"),
    ("Monitor", "https://techzone.lk/product-category/monitors/"),
    ("Laptop", "https://techzone.lk/product-category/laptops/")
]


class TechzoneScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Techzone", base_url="https://techzone.lk")
        self.headless = headless

    def _scrape_with_playwright(self, cat_name: str, cat_url: str, max_pages: int):
        from playwright.sync_api import sync_playwright
        print(f"   [!] Using Playwright fallback for {cat_name}...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=self.get_headers()["User-Agent"]
                )
                page = context.new_page()

                p_idx = 1
                prev_title = None

                while p_idx <= max_pages:
                    page_url = cat_url if p_idx == 1 else f"{cat_url.rstrip('/')}/page/{p_idx}/"
                    res = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    if res and res.status in [404, 403]:
                        break

                    soup = BeautifulSoup(page.content(), "html.parser")
                    cards = soup.select("li.product, div.product-small, .product-item, .type-product")
                    if not cards:
                        break

                    first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3")
                    first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                    if first_title and first_title == prev_title:
                        break
                    prev_title = first_title

                    self._parse_cards(cards, cat_name)
                    p_idx += 1
                    self.sleep_polite()

                browser.close()
        except Exception as e:
            print(f"   [!] Playwright error on {cat_name}: {e}")

    def _parse_cards(self, cards, cat_name: str):
        for card in cards:
            title_el = card.select_one(".woocommerce-loop-product__title, .name.product-title, h2, h3")
            price_el = card.select_one(".price ins .woocommerce-Price-amount, .price .woocommerce-Price-amount, .price")
            link_el = card.select_one("a[href]")

            title = title_el.get_text(strip=True) if title_el else None
            price = price_el.get_text(strip=True) if price_el else "N/A"
            url = urljoin(self.base_url, link_el["href"]) if link_el else ""

            card_classes = " ".join(card.get("class", []))
            card_text = card.get_text(separator=" ", strip=True).lower()
            if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                stock = "Out of Stock"
            else:
                stock = "In Stock"

            if title:
                self.add_product(category=cat_name, title=title, price=price, stock=stock, url=url)

    def scrape(self, max_pages_per_category: int = 5):
        print(f"\n[+] Starting Techzone Scraper...")

        for cat_name, cat_url in CATEGORIES:
            print(f" -> Category: {cat_name} -> {cat_url}")
            page = 1
            prev_first_title = None
            use_playwright = False

            while page <= max_pages_per_category:
                page_url = cat_url if page == 1 else f"{cat_url.rstrip('/')}/page/{page}/"

                try:
                    if HAS_CURL_CFFI:
                        res = c_requests.get(page_url, impersonate="chrome120", timeout=15)
                    else:
                        res = c_requests.get(page_url, headers=self.get_headers(), timeout=15)

                    if res.status_code == 403:
                        use_playwright = True
                        break
                    if res.status_code in [404, 500]:
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    cards = soup.select("li.product, div.product-small, .product-item, .type-product")
                    if not cards:
                        break

                    first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3")
                    first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                    if first_title and first_title == prev_first_title:
                        break
                    prev_first_title = first_title

                    self._parse_cards(cards, cat_name)
                    page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error requesting {page_url}: {e}")
                    use_playwright = True
                    break

            if use_playwright:
                self._scrape_with_playwright(cat_name, cat_url, max_pages_per_category)

        return self.save_csv()


def run(max_pages: int = 5, headless: bool = True):
    scraper = TechzoneScraper(headless=headless)
    return scraper.scrape(max_pages_per_category=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
