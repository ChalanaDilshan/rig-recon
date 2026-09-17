"""
scrapers/mdcomputers.py - MDComputers.lk Modular Scraper
Engine: curl_cffi (impersonate="chrome120") + BeautifulSoup
Pagination: https://mdcomputers.lk/shop/page/{n}/
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


class MDComputersScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_name="MD Computers", base_url="https://mdcomputers.lk")
        self.shop_url = "https://mdcomputers.lk/shop/"

    def scrape(self, max_pages: int = 50):
        print(f"\n[+] Starting MD Computers Scraper...")
        page = 1
        prev_first_title = None

        while page <= max_pages:
            page_url = self.shop_url if page == 1 else f"{self.shop_url}page/{page}/"
            print(f" -> Page {page}: {page_url}")

            try:
                if HAS_CURL_CFFI:
                    res = c_requests.get(page_url, impersonate="chrome120", timeout=20)
                else:
                    res = c_requests.get(page_url, headers=self.get_headers(), timeout=20)

                if res.status_code == 404:
                    print("    End of catalog reached (404).")
                    break
                if res.status_code != 200:
                    print(f"    Status code {res.status_code}. Stopping.")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                cards = soup.select("li.product, div.product, .type-product")
                if not cards:
                    print("    No products found on page.")
                    break

                first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3")
                first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                if first_title and first_title == prev_first_title:
                    print("    Duplicate page detected. Reached end.")
                    break
                prev_first_title = first_title

                for card in cards:
                    title_el = card.select_one(".woocommerce-loop-product__title, h2, h3")
                    price_el = card.select_one(".price ins, .price .amount, .price")
                    link_el = card.select_one("a[href]")

                    title = title_el.get_text(strip=True) if title_el else None
                    price = price_el.get_text(strip=True) if price_el else "N/A"
                    url = urljoin(self.base_url, link_el["href"]) if link_el else ""

                    card_classes = " ".join(card.get("class", []))
                    card_text = card.get_text(separator=" ", strip=True).lower()
                    if "out-of-stock" in card_classes or "out of stock" in card_text:
                        stock = "Out of Stock"
                    elif "in-stock" in card_classes or "add to cart" in card_text:
                        stock = "In Stock"
                    else:
                        stock = "Available / On Order"

                    if title:
                        self.add_product(
                            category="Hardware",
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


def run(max_pages: int = 50):
    scraper = MDComputersScraper()
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=2)
