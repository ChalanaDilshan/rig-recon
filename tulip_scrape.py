import csv
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.tulipcom.lk"

def get_all_tulip_categories(page):
    """Tulip මුල් පිටුවෙන් සක්‍රීය Category Links සොයා ගැනීම."""
    print(f"Discovering categories from {BASE_URL}...")
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(3)

    soup = BeautifulSoup(page.content(), "html.parser")
    category_links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/product/c/" in href:
            clean_url = urljoin(BASE_URL, href).split("#")[0].split("?")[0].rstrip("/")
            if clean_url not in category_links and clean_url != f"{BASE_URL}/product/c":
                cat_name = clean_url.split("/product/c/")[-1].replace("_", " ").replace("-", " ").title()
                category_links.append((cat_name, clean_url))

    print(f"Discovered {len(category_links)} categories.\n")
    return category_links

def clean_title_from_url(url):
    """HTML එකෙන් නම නොලැබුණහොත් URL slug එකෙන් නම සාදා ගැනීම."""
    parts = [p for p in url.split("?")[0].split("/") if p]
    if parts:
        slug = parts[-1]
        cleaned = slug.replace("-", " ").replace("_", " ").strip().title()
        if not re.match(r"^\d+$", cleaned):
            return cleaned
    return "N/A"

def scrape_tulip_store():
    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        categories = get_all_tulip_categories(page)

        if not categories:
            categories = [
                ("Laptops", "https://www.tulipcom.lk/product/c/laptops"),
                ("Used Desktop", "https://www.tulipcom.lk/product/c/used_desktop"),
                ("Graphics Card", "https://www.tulipcom.lk/product/c/graphics_card"),
                ("Processors", "https://www.tulipcom.lk/product/c/processors"),
            ]

        for cat_name, cat_url in categories:
            print(f"\n📂 Crawling Category: [{cat_name}] -> {cat_url}")
            current_page = 1
            max_pages = 8

            while current_page <= max_pages:
                page_url = cat_url if current_page == 1 else f"{cat_url}?page={current_page}"
                print(f"   -> Loading: {page_url}")

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=35000)
                    time.sleep(2)

                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                    soup = BeautifulSoup(page.content(), "html.parser")
                    product_links = soup.find_all("a", href=lambda h: h and ("/product/v/" in h or "/product/" in h))
                    page_items = 0

                    for link in product_links:
                        href = link["href"].strip()
                        if "/product/c/" in href:
                            continue

                        product_url = urljoin(BASE_URL, href).split("?")[0]
                        if product_url in seen_urls or product_url == cat_url:
                            continue

                        card = link.find_parent("div", class_=lambda c: c and any(k in c.lower() for k in ["col", "product", "item", "card"]))
                        container = card if card else link
                        card_text = container.get_text(separator=" ", strip=True)

                        # 1. Price ලබා ගැනීම: Rs. හෝ LKR අනිවාර්ය කර model numbers (RTX 4050 ආදිය) මඟහැරීම
                        price_match = re.search(r"(?:Rs\.?|LKR)\s*([\d,]+(?:\.\d{2})?)", card_text, re.IGNORECASE)
                        if not price_match:
                            continue

                        price_val = price_match.group(1).strip()
                        # අවම වශයෙන් ඉලක්කම් 3ක් සහිත සැබෑ මිලක් බව තහවුරු කිරීම
                        if len(price_val.replace(",", "").split(".")[0]) < 3:
                            continue

                        price = f"Rs. {price_val}"

                        # 2. Product Title ලබා ගැනීම
                        title = None
                        candidates = container.find_all(["h2", "h3", "h4", "h5", "a", "p"])
                        for el in candidates:
                            txt = el.get_text(strip=True)
                            # මිල (Rs.) හෝ බොත්තම් අඩංගු නොවන සැබෑ නම පමණක් තේරීම
                            if len(txt) > 5 and not re.search(r"(?:Rs\.?|LKR|\bAdd to cart\b|\bBuy now\b)", txt, re.I):
                                if not re.match(r"^[\d,.\s]+$", txt):
                                    title = txt
                                    break

                        if not title:
                            img = container.find("img", alt=True)
                            if img and len(img["alt"].strip()) > 3:
                                alt_txt = img["alt"].strip()
                                if not re.search(r"(?:Rs\.?|LKR)", alt_txt, re.I):
                                    title = alt_txt

                        if not title:
                            title = clean_title_from_url(product_url)

                        if not title or len(title) < 3:
                            continue

                        # 3. Stock Status Check
                        lower_text = card_text.lower()
                        if "out of stock" in lower_text:
                            stock = "Out of Stock"
                        elif "in stock" in lower_text or "add to cart" in lower_text or "buy" in lower_text:
                            stock = "In Stock"
                        else:
                            stock = "In Stock"

                        seen_urls.add(product_url)
                        all_products.append({
                            "Category": cat_name,
                            "Title": title,
                            "Price": price,
                            "Stock": stock,
                            "URL": product_url
                        })

                        page_items += 1
                        print(f"      [{stock}] {title} -> {price}")

                    if page_items == 0:
                        print(f"      No more items found on page {current_page}.")
                        break

                    print(f"   ✔️ Extracted {page_items} items from Page {current_page}")

                    has_next_page = soup.find("a", href=lambda h: h and f"page={current_page + 1}" in h)
                    if not has_next_page and current_page > 1:
                        break

                    current_page += 1

                except Exception as err:
                    print(f"   ⚠️ Error: {err}")
                    break

        browser.close()

    save_to_csv(all_products)

def save_to_csv(data, filename="tulip_all_products.csv"):
    if not data:
        print("\n❌ No products collected.")
        return

    fields = ["Category", "Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ All Done! Total {len(data)} items saved into '{filename}'.")

if __name__ == "__main__":
    scrape_tulip_store()