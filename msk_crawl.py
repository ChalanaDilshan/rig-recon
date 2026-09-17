import csv
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.mskcomputers.lk"

# MSK Computers සැබෑ Category URLs
CATEGORIES = [
    ("Graphic Cards", "https://www.mskcomputers.lk/categories/graphic-card"),
    ("Processors", "https://www.mskcomputers.lk/categories/processor"),
    ("Motherboards", "https://www.mskcomputers.lk/categories/motherboards"),
    ("RAM", "https://www.mskcomputers.lk/categories/memory-ram"),
    ("Storage", "https://www.mskcomputers.lk/categories/storage"),
    ("Power Supplies", "https://www.mskcomputers.lk/categories/power-supply"),
    ("Casings", "https://www.mskcomputers.lk/categories/casing"),
    ("Monitors", "https://www.mskcomputers.lk/categories/monitors")
]

def scrape_msk_store():
    all_products = []
    seen_items = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for cat_name, cat_url in CATEGORIES:
            print(f"\n📂 Loading Category: [{cat_name}] -> {cat_url}")

            try:
                page.goto(cat_url, wait_until="domcontentloaded", timeout=45000)

                # AJAX Filter System එක හරහා භාණ්ඩ load වන තෙක් රැඳී සිටීම
                try:
                    page.wait_for_selector(".product-card", timeout=8000)
                except Exception:
                    print(f"   ⚠️ No products loaded (Category might be empty or out of stock).")
                    continue

                # Lazy-loaded images සහ cards සම්පූර්ණයෙන් render වීමට scroll කිරීම
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)

                soup = BeautifulSoup(page.content(), "html.parser")

                # div හෝ a tag දෙකටම ගැලපෙන පරිදි .product-card selector එක භාවිතය
                product_cards = soup.select(".product-card")
                print(f"   ✔️ Found {len(product_cards)} products in [{cat_name}]")

                for card in product_cards:
                    card_text = card.get_text(separator=" ", strip=True)

                    # 1. Product Title (DevTools එකේ ඇති h3 tag එකෙන්)
                    title_el = card.select_one("h3")
                    if title_el:
                        title = title_el.get_text(strip=True)
                    else:
                        img_el = card.select_one("img[alt]")
                        title = img_el["alt"].strip() if img_el else "N/A"

                    # 2. Product Price (LKR අගය)
                    price_match = re.search(r"LKR\s*[\d,]+(?:\.\d{2})?", card_text)
                    price = price_match.group(0) if price_match else "N/A"

                    # 3. Stock Status (DevTools හි පෙනෙන Stock badge එකෙන්)
                    upper_text = card_text.upper()
                    if "OUT OF STOCK" in upper_text:
                        stock = "Out of Stock"
                    elif "IN STOCK" in upper_text:
                        stock = "In Stock"
                    else:
                        stock = "In Stock"

                    # 4. Product Link
                    if card.name == "a" and card.get("href"):
                        product_url = urljoin(BASE_URL, card["href"])
                    else:
                        link_el = card.select_one("a[href]")
                        product_url = urljoin(BASE_URL, link_el["href"]) if link_el else cat_url

                    # Deduplication
                    item_key = f"{title}_{price}"
                    if item_key in seen_items or len(title) < 4:
                        continue

                    seen_items.add(item_key)
                    all_products.append({
                        "Category": cat_name,
                        "Title": title,
                        "Price": price,
                        "Stock": stock,
                        "URL": product_url
                    })

                    print(f"      [{stock}] {title} | {price}")

            except Exception as err:
                print(f"   ⚠️ Connection error on [{cat_name}]: {err}")

        browser.close()

    save_to_csv(all_products)

def save_to_csv(data, filename="mskcomputers_all_products.csv"):
    if not data:
        print("\n❌ No products collected.")
        return

    fields = ["Category", "Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ All Done! Saved {len(data)} total items into '{filename}'.")

if __name__ == "__main__":
    scrape_msk_store()