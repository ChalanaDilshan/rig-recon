import csv
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.gallelaptop.lk"
START_URL = "https://www.gallelaptop.lk"

def discover_all_subcategories(page):
    """මුල් පිටුවෙන් සහ Dropdown Menu වලින් සියලුම Subcategories (sci=) සොයා ගැනීම."""
    print("Discovering all sub-categories from menu...")
    page.goto(START_URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(3)

    soup = BeautifulSoup(page.content(), "html.parser")
    subcat_urls = []
    seen = set()

    # Dropdown menu සහ links අතරින් sci= අඩංගු සැබෑ භාණ්ඩ කාණ්ඩ වෙන්කර ගැනීම
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "products.php" in href and "sci=" in href:
            clean_url = urljoin(BASE_URL, href).split("#")[0]
            if clean_url not in seen:
                cat_name = a.get_text(strip=True) or "Hardware"
                seen.add(clean_url)
                subcat_urls.append((cat_name, clean_url))

    # Dropdown links හසු නොවුවහොත් fallback links භාවිතය
    if not subcat_urls:
        print("Fallback: Adding core category URLs...")
        subcat_urls = [
            ("Graphic Cards", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjM="),
            ("Processors", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjE="),
            ("Motherboards", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjI="),
            ("Memory RAM", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjQ="),
            ("Storage", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjU="),
            ("Power Supply", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=Mjc="),
            ("Casings", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=Mjg="),
            ("Laptops", "https://www.gallelaptop.lk/products.php?ci=MQ==&sci=MQ=="),
        ]

    print(f"Found {len(subcat_urls)} active sub-categories.\n")
    return subcat_urls

def scrape_gallelaptop_store():
    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        subcategories = discover_all_subcategories(page)

        for cat_name, cat_url in subcategories:
            print(f"\n📂 Crawling Category: [{cat_name}] -> {cat_url}")
            current_page = 1
            max_pages = 8

            while current_page <= max_pages:
                page_param = f"&page={current_page}" if current_page > 1 else ""
                target_url = f"{cat_url}{page_param}"
                print(f"   -> Loading: {target_url}")

                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=35000)
                    time.sleep(2)

                    # Lazy loading images/content load වීමට scroll කිරීම
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                    soup = BeautifulSoup(page.content(), "html.parser")

                    # Product links සෙවීම
                    product_links = soup.find_all("a", href=lambda h: h and any(k in h for k in ["product", "item", "pid=", "detail", "view"]))
                    page_items = 0

                    for link in product_links:
                        href = link["href"].strip()
                        if "products.php" in href or "cart" in href:
                            continue

                        product_url = urljoin(BASE_URL, href).split("&page=")[0]
                        if product_url in seen_urls:
                            continue

                        # Container එක හඳුනා ගැනීම
                        card = link.find_parent("div", class_=lambda c: c and any(k in c.lower() for k in ["col", "product", "item", "card"]))
                        container = card if card else link
                        card_text = container.get_text(separator=" ", strip=True)

                        # 1. Price ලබා ගැනීම (Rs. හෝ LKR අගය)
                        price_match = re.search(r"(?:Rs\.?|LKR)\s*([\d,]+(?:\.\d{2})?)", card_text, re.IGNORECASE)
                        if not price_match:
                            continue

                        price = f"Rs. {price_match.group(1)}"

                        # 2. Product Title ලබා ගැනීම
                        title = None
                        for heading in container.find_all(["h2", "h3", "h4", "h5", "h6"]):
                            h_txt = heading.get_text(strip=True)
                            if len(h_txt) > 5 and not re.search(r"(?:Rs\.?|LKR)", h_txt, re.I):
                                title = h_txt
                                break

                        if not title:
                            img = container.find("img", alt=True)
                            if img and len(img["alt"].strip()) > 4:
                                title = img["alt"].strip()

                        if not title:
                            txt_cands = [t.strip() for t in link.stripped_strings if len(t.strip()) > 5 and not re.search(r"(?:Rs\.?|LKR)", t, re.I)]
                            if txt_cands:
                                title = txt_cands[0]

                        if not title or len(title) < 4:
                            continue

                        # 3. Stock Status
                        lower_text = card_text.lower()
                        if "out of stock" in lower_text or "sold out" in lower_text:
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
                        print(f"      No items on page {current_page}. Category complete.")
                        break

                    print(f"   ✔️ Extracted {page_items} items from Page {current_page}")

                    # Next page පරීක්ෂාව
                    has_next = soup.find("a", href=lambda h: h and f"page={current_page + 1}" in h)
                    if not has_next and current_page > 1:
                        break

                    current_page += 1

                except Exception as err:
                    print(f"   ⚠️ Error: {err}")
                    break

        browser.close()

    save_to_csv(all_products)

def save_to_csv(data, filename="gallelaptop_all_products.csv"):
    if not data:
        print("\n❌ No products collected.")
        return

    fields = ["Category", "Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ Finished! Successfully saved {len(data)} items to '{filename}'.")

if __name__ == "__main__":
    scrape_gallelaptop_store()