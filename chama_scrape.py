import csv
import re
import time
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.chamacomputers.lk"

# Crawl කිරීමට අවශ්‍ය Categories ලැයිස්තුව
TARGET_CATEGORIES = [
    "https://www.chamacomputers.lk/products/graphics%20cards",
    "https://www.chamacomputers.lk/products/processors",
    "https://www.chamacomputers.lk/products/motherboards",
    "https://www.chamacomputers.lk/products/memory",
    "https://www.chamacomputers.lk/products/power%20supply",
    "https://www.chamacomputers.lk/products/monitors%20%26%20displays",
    "https://www.chamacomputers.lk/products/laptops"
]

def scrape_chama_with_playwright():
    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        # Browser එක launch කිරීම
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for category_url in TARGET_CATEGORIES:
            category_name = unquote(category_url.split("/products/")[-1]).title()
            print(f"\n📂 Crawling Category: [{category_name}]")

            current_page = 1
            max_pages = 10  # Category එකකට පරීක්ෂා කරන උපරිම පිටු ගණන

            while current_page <= max_pages:
                page_url = f"{category_url}?page={current_page}"
                print(f"   -> Loading Page {current_page}: {page_url}")

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)  # JavaScript මඟින් භාණ්ඩ render වන තෙක් සුළු වේලාවක්

                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")

                    # Chama Computers හි භාණ්ඩ link එකක ව්‍යුහය: /products/<category>/<product-slug>
                    product_links = soup.find_all("a", href=True)
                    page_items = 0

                    for link in product_links:
                        href = link["href"]
                        parts = [p for p in href.split("?")[0].split("/") if p]

                        # /products/category/item ආකෘතියේ links පමණක් වෙන්කර ගැනීම
                        if len(parts) >= 3 and parts[0] == "products":
                            full_url = urljoin(BASE_URL, href).split("?")[0]

                            if full_url in seen_urls:
                                continue

                            # Card එකේ අඩංගු සම්පූර්ණ text එක
                            card_text = link.get_text(separator=" ", strip=True)

                            # මිල (Rs.) අගය regex මඟින් සෙවීම
                            price_match = re.search(r"Rs\.?\s*([\d,]+(?:\.\d{2})?)", card_text)
                            if not price_match:
                                continue

                            price = f"Rs. {price_match.group(1)}"

                            # Title එක ලබා ගැනීම (Link text එකෙන් හෝ image alt එකෙන්)
                            img_tag = link.find("img")
                            img_alt = img_tag.get("alt", "").strip() if img_tag else ""
                            
                            # නම පිරිසිදු කර ගැනීම
                            raw_title = img_alt if img_alt else card_text.split("Rs.")[0].strip()
                            # "In Stock", "Out of Stock", "New" වැනි අනවශ්‍ය වචන ඉවත් කිරීම
                            title = re.sub(r"^(In Stock|Out of Stock|New|Sale)\s*", "", raw_title, flags=re.IGNORECASE).strip()

                            if not title or len(title) < 4:
                                continue

                            # Stock තත්ත්වය
                            lower_text = card_text.lower()
                            if "out of stock" in lower_text:
                                stock = "Out of Stock"
                            elif "in stock" in lower_text or "add to cart" in lower_text:
                                stock = "In Stock"
                            else:
                                stock = "In Stock"

                            seen_urls.add(full_url)
                            all_products.append({
                                "Category": category_name,
                                "Title": title,
                                "Price": price,
                                "Stock": stock,
                                "URL": full_url
                            })

                            page_items += 1
                            print(f"      [{stock}] {title} -> {price}")

                    if page_items == 0:
                        print(f"      No more items found on Page {current_page}. Moving next.")
                        break

                    print(f"   ✔️ Extracted {page_items} items from Page {current_page}")
                    current_page += 1

                except Exception as err:
                    print(f"   ⚠️ Error loading page {current_page}: {err}")
                    break

        browser.close()

    # දත්ත CSV ගොනුවකට Save කිරීම
    save_to_csv(all_products)

def save_to_csv(data, filename="chamacomputers_products.csv"):
    if not data:
        print("\n❌ No products collected to save.")
        return

    fields = ["Category", "Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ All Done! Total {len(data)} items saved into '{filename}'.")

if __name__ == "__main__":
    scrape_chama_with_playwright()