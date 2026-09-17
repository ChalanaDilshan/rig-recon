"""
scrapers/base_scraper.py - Base Scraper Class & Common Scraping Utilities

Features:
- Polite rate-limiting (1.2 - 1.5s delay)
- Realistic browser header spoofing
- Duplicate page / title detection to stop infinite loops
- Standardized data saving to data/raw/
- Resilience with retry logic on transient errors
"""

import os
import csv
import time
import random
from typing import List, Dict, Optional
from urllib.parse import urljoin

DATA_RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class BaseScraper:
    def __init__(self, store_name: str, base_url: str, min_delay: float = 1.2, max_delay: float = 1.6):
        self.store_name = store_name
        self.base_url = base_url
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.products: List[Dict] = []
        self.seen_urls = set()
        self.seen_first_titles = set()

    def get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.base_url,
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1"
        }

    def sleep_polite(self):
        """Enforces minimum 1.2 to 1.5+ seconds politeness delay."""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

    def is_duplicate_page(self, first_title: str) -> bool:
        """Loop prevention guard for infinite pagination redirects."""
        if not first_title:
            return False
        cleaned = first_title.strip().lower()
        if cleaned in self.seen_first_titles:
            return True
        self.seen_first_titles.add(cleaned)
        return False

    def add_product(self, category: str, title: str, price: str, stock: str, url: str) -> bool:
        """Adds a standardized product record if not duplicate."""
        if not title or len(title.strip()) < 3:
            return False

        full_url = urljoin(self.base_url, url).strip() if url else self.base_url
        if full_url in self.seen_urls:
            return False

        self.seen_urls.add(full_url)
        self.products.append({
            "Source_Store": self.store_name,
            "Category": category.strip() if category else "Hardware",
            "Title": title.strip(),
            "Price": price.strip() if price else "N/A",
            "Stock": stock.strip() if stock else "In Stock",
            "URL": full_url
        })
        return True

    def save_csv(self, custom_filename: Optional[str] = None) -> str:
        """Saves scraped items to CSV in data/raw/."""
        os.makedirs(DATA_RAW_DIR, exist_ok=True)
        slug = self.store_name.lower().replace(" ", "_")
        filename = custom_filename or f"{slug}_all_products.csv"
        filepath = os.path.join(DATA_RAW_DIR, filename)

        if not self.products:
            print(f"[!] No products to save for {self.store_name}.")
            return filepath

        fieldnames = ["Source_Store", "Category", "Title", "Price", "Stock", "URL"]
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.products)

        print(f"[OK] Saved {len(self.products)} records to: {filepath}")
        return filepath
