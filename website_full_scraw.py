import csv
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

START_URL = "https://www.nanotek.lk"
DOMAIN = "www.nanotek.lk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class NanotekPaginatedCrawler:
    def __init__(self, start_url, max_categories=10):
        self.category_queue = [start_url]
        self.visited_categories = set()
        self.max_categories = max_categories
        self.all_products = []

    def is_valid_category_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != DOMAIN:
            return False
        return "/category/" in parsed.path

    def discover_categories(self, soup, current_url):
        """Find other category links from the navigation menu."""
        for a_tag in soup.find_all("a", href=True):
            clean_url = urljoin(current_url, a_tag["href"]).split("#")[0].split("?")[0]
            if self.is_valid_category_url(clean_url):
                if clean_url not in self.visited_categories and clean_url not in self.category_queue:
                    self.category_queue.append(clean_url)

    def scrape_category_with_pagination(self, category_url):
        """Crawl all pagination pages (Page 1, 2, 3...) for a single category."""
        category_name = category_url.split("/category/")[-1].replace("-", " ").title()
        page_number = 1
        total_category_items = 0
        previous_page_first_title = None

        print(f"\n📂 Crawling Category: [{category_name}]")

        while True:
            # Build paginated URL (e.g. ?page=1, ?page=2)
            page_url = f"{category_url}?page={page_number}"
            print(f"   -> Fetching Page {page_number}: {page_url}")

            try:
                res = requests.get(page_url, headers=HEADERS, timeout=12)
                if res.status_code != 200:
                    print(f"      Status {res.status_code}. Ending pagination for this category.")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                product_items = soup.find_all("li", class_="ty-catPage-productListItem")

                # Stop condition 1: No products found on this page
                if not product_items:
                    print(f"      No more products found on page {page_number}.")
                    break

                # Stop condition 2: Infinite redirect check (some sites repeat Page 1 if out of bounds)
                first_title_div = product_items[0].find("div", class_="ty-productBlock-title")
                first_title = first_title_div.get_text(strip=True) if first_title_div else ""
                
                if first_title == previous_page_first_title:
                    print("      Duplicate page detected (reached end of pagination).")
                    break
                previous_page_first_title = first_title

                # Extract items from the current page
                for item in product_items:
                    title_div = item.find("div", class_="ty-productBlock-title")
                    price_div = item.find("div", class_="ty-productBlock-price")
                    link_tag = item.find("a", href=True)
                    special_msg = item.find("div", class_="ty-productBlock-specialMsg")

                    title = title_div.get_text(strip=True) if title_div else None
                    price = price_div.get_text(strip=True) if price_div else "N/A"
                    product_url = urljoin(START_URL, link_tag["href"]) if link_tag else "N/A"
                    stock = special_msg.get_text(strip=True) if special_msg else "In Stock"

                    if title:
                        self.all_products.append({
                            "Category": category_name,
                            "Title": title,
                            "Price": price,
                            "Stock": stock,
                            "URL": product_url
                        })
                        total_category_items += 1

                print(f"      Extracted {len(product_items)} items from Page {page_number}")
                page_number += 1
                time.sleep(1)  # Delay between page requests

            except requests.RequestException as err:
                print(f"      Network error on page {page_number}: {err}")
                break

        print(f"✔️ Finished [{category_name}]: Total {total_category_items} items collected.")

    def run(self):
        crawled_categories = 0

        while self.category_queue and crawled_categories < self.max_categories:
            current_category = self.category_queue.pop(0)

            if current_category in self.visited_categories:
                continue

            self.visited_categories.add(current_category)

            # 1. First request to discover category links from page navigation
            try:
                res = requests.get(current_category, headers=HEADERS, timeout=12)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    self.discover_categories(soup, current_category)
            except requests.RequestException:
                pass

            # 2. Scrape all pages of this category
            if "/category/" in current_category:
                self.scrape_category_with_pagination(current_category)
                crawled_categories += 1

            time.sleep(1.5)

        self.save_results()

    def save_results(self, filename="nanotek_complete_catalog.csv"):
        if not self.all_products:
            print("\nNo products collected.")
            return

        fields = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.all_products)

        print(f"\n✅ All Done! Successfully saved {len(self.all_products)} total items to '{filename}'.")

if __name__ == "__main__":
    # If you only want Graphics Cards pagination first, pass the exact URL:
    crawler = NanotekPaginatedCrawler(
        start_url="https://www.nanotek.lk/category/graphics-card",
        max_categories=1  # Change to 5 or 10 to crawl multiple full categories
    )
    crawler.run()