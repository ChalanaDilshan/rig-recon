import csv
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

START_URL = "https://www.nanotek.lk/category/graphics-card"
DOMAIN = "www.nanotek.lk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class FullyAutomaticCrawler:
    def __init__(self, start_url):
        self.category_queue = [start_url]
        self.visited_categories = set()
        self.all_products = []

    def is_valid_category_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != DOMAIN:
            return False
        return "/category/" in parsed.path

    def discover_categories(self, soup, current_url):
        """Discovers new category links from the page and adds them to the queue automatically."""
        for a_tag in soup.find_all("a", href=True):
            clean_url = urljoin(current_url, a_tag["href"]).split("#")[0].split("?")[0]
            if self.is_valid_category_url(clean_url):
                if clean_url not in self.visited_categories and clean_url not in self.category_queue:
                    self.category_queue.append(clean_url)

    def scrape_category_pagination(self, category_url):
        """Crawls all pages (page=1, page=2, etc.) of a specific category until it finishes completely."""
        category_name = category_url.split("/category/")[-1].replace("-", " ").title()
        page_number = 1
        total_items = 0
        previous_first_title = None

        print(f"\n📂 Starting Category: [{category_name}]")

        while True:
            page_url = f"{category_url}?page={page_number}"
            print(f"   -> Crawling Page {page_number}: {page_url}")

            try:
                res = requests.get(page_url, headers=HEADERS, timeout=12)
                if res.status_code != 200:
                    print(f"      Status {res.status_code}. Reached end of category pages.")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                
                # Continuously discover other categories from the sidebar/menu as it crawls
                self.discover_categories(soup, page_url)

                product_items = soup.find_all("li", class_="ty-catPage-productListItem")

                # Stop condition: No products on this page
                if not product_items:
                    print(f"      No products found on page {page_number}. Moving to next category.")
                    break

                # Stop condition: Prevent infinite loops if pagination redirects back to page 1
                first_title_div = product_items[0].find("div", class_="ty-productBlock-title")
                first_title = first_title_div.get_text(strip=True) if first_title_div else ""
                
                if first_title == previous_first_title:
                    print("      Page repeated (End of pagination reached).")
                    break
                previous_first_title = first_title

                # Extract items
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
                        total_items += 1

                print(f"      Found {len(product_items)} items on Page {page_number}")
                page_number += 1
                time.sleep(1)

            except requests.RequestException as err:
                print(f"      Network error: {err}")
                break

        print(f"✔️ Completed [{category_name}]: Collected {total_items} items.")

    def run(self):
        """Processes categories in the queue sequentially until every category on the site is done."""
        while self.category_queue:
            current_category = self.category_queue.pop(0)

            if current_category in self.visited_categories:
                continue

            self.visited_categories.add(current_category)

            # Scrape all pagination pages for this category
            self.scrape_category_pagination(current_category)

            time.sleep(1.5)

        self.save_results()

    def save_results(self, filename="nanotek_all_categories_complete.csv"):
        if not self.all_products:
            print("\nNo products collected.")
            return

        fields = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.all_products)

        print(f"\n✅ All categories finished! Saved {len(self.all_products)} total items to '{filename}'.")

if __name__ == "__main__":
    # Starts with Graphics Card, automatically discovers and crawls ALL other site categories and their pagination pages!
    crawler = FullyAutomaticCrawler(start_url="https://www.nanotek.lk/category/graphics-card")
    crawler.run()