"""
scrapers/nanotek.py - Nanotek.lk Modular Scraper
Engine: requests + BeautifulSoup (SSR / PHP)
Selectors: li.ty-catPage-productListItem
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from scrapers.base_scraper import BaseScraper


class NanotekScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_name="Nanotek", base_url="https://www.nanotek.lk")
        self.start_url = "https://www.nanotek.lk/category/graphics-card"
        self.category_queue = [self.start_url]
        self.visited_categories = set()

    def discover_categories(self, soup: BeautifulSoup, current_url: str):
        for a in soup.find_all("a", href=True):
            clean_url = urljoin(current_url, a["href"]).split("#")[0].split("?")[0]
            parsed = urlparse(clean_url)
            if "nanotek.lk" in parsed.netloc and "/category/" in parsed.path:
                if clean_url not in self.visited_categories and clean_url not in self.category_queue:
                    self.category_queue.append(clean_url)

    def scrape(self, max_pages_per_category: int = 15, max_categories: int = 15):
        print(f"\n[+] Starting Nanotek Scraper...")
        cats_scraped = 0

        while self.category_queue and cats_scraped < max_categories:
            cat_url = self.category_queue.pop(0)
            if cat_url in self.visited_categories:
                continue

            self.visited_categories.add(cat_url)
            cats_scraped += 1
            cat_slug = cat_url.split("/category/")[-1].replace("-", " ").title()
            print(f" -> [{cats_scraped}/{max_categories}] Category: {cat_slug}")

            page = 1
            prev_first_title = None

            while page <= max_pages_per_category:
                page_url = f"{cat_url}?page={page}"
                try:
                    res = requests.get(page_url, headers=self.get_headers(), timeout=15)
                    if res.status_code != 200:
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    self.discover_categories(soup, page_url)

                    items = soup.find_all("li", class_="ty-catPage-productListItem")
                    if not items:
                        break

                    first_title_el = items[0].find("div", class_="ty-productBlock-title")
                    first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                    if first_title and first_title == prev_first_title:
                        break
                    prev_first_title = first_title

                    for item in items:
                        title_el = item.find("div", class_="ty-productBlock-title")
                        price_el = item.find("div", class_="ty-productBlock-price")
                        link_el = item.find("a", href=True)
                        special_msg = item.find("div", class_="ty-productBlock-specialMsg")

                        title = title_el.get_text(strip=True) if title_el else None
                        price = price_el.get_text(strip=True) if price_el else "N/A"
                        url = urljoin(self.base_url, link_el["href"]) if link_el else ""
                        stock = special_msg.get_text(strip=True) if special_msg else "In Stock"

                        if title:
                            self.add_product(
                                category=cat_slug,
                                title=title,
                                price=price,
                                stock=stock,
                                url=url
                            )

                    page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error fetching {page_url}: {e}")
                    break

        return self.save_csv()


def run(max_pages: int = 15, max_categories: int = 15):
    scraper = NanotekScraper()
    return scraper.scrape(max_pages_per_category=max_pages, max_categories=max_categories)


if __name__ == "__main__":
    run(max_pages=2, max_categories=2)
