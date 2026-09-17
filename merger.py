"""
merger.py - Master Dataset Aggregator & SQLite Compiler

Aggregates individual raw store CSVs into:
1. data/sri_lanka_pc_market_data.csv (Master CSV)
2. data/market_data.db (SQLite database with indexing for fast querying)
"""

import os
import glob
import sqlite3
import pandas as pd
from typing import List, Dict
from datetime import datetime
from cleaner import clean_record, normalize_store_name

DATA_RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MASTER_CSV_PATH = os.path.join(DATA_DIR, "sri_lanka_pc_market_data.csv")
DB_PATH = os.path.join(DATA_DIR, "market_data.db")

COLUMNS = [
    "Source_Store",
    "Category",
    "Title",
    "Raw_Price",
    "Cleaned_Price_LKR",
    "Stock_Status",
    "Product_URL",
    "Scraped_Date"
]


def load_and_clean_csv(file_path: str) -> List[Dict]:
    """Loads a raw CSV file and normalizes its records."""
    filename = os.path.basename(file_path)
    store_name = normalize_store_name(filename)

    records = []
    try:
        # Read with utf-8 or utf-8-sig
        df = pd.read_csv(file_path, encoding="utf-8-sig", on_bad_lines="skip")
    except Exception:
        try:
            df = pd.read_csv(file_path, encoding="latin1", on_bad_lines="skip")
        except Exception as e:
            print(f"[-] Could not read {file_path}: {e}")
            return []

    if df.empty:
        return []

    for _, row in df.iterrows():
        raw_dict = row.to_dict()
        cleaned = clean_record(raw_dict, default_store=store_name)
        # Filter out empty or placeholder titles
        if cleaned["Title"] and cleaned["Title"] != "Unknown Product" and len(cleaned["Title"]) >= 3:
            records.append(cleaned)

    return records


def compile_master_dataset(raw_dir: str = DATA_RAW_DIR) -> pd.DataFrame:
    """Discovers all raw CSVs, normalizes, deduplicates, and saves master dataset."""
    os.makedirs(DATA_DIR, exist_ok=True)
    all_csv_files = glob.glob(os.path.join(raw_dir, "*.csv"))

    if not all_csv_files:
        print(f"[!] No CSV files found in {raw_dir}")
        # Check root directory fallback
        all_csv_files = glob.glob("*.csv")

    all_records: List[Dict] = []
    processed_files = set()

    for csv_file in all_csv_files:
        basename = os.path.basename(csv_file)
        # Skip previously generated master CSV
        if "sri_lanka_pc_market_data" in basename:
            continue
        if basename in processed_files:
            continue

        processed_files.add(basename)
        recs = load_and_clean_csv(csv_file)
        if recs:
            print(f"[+] Loaded {len(recs):>5} items from {basename}")
            all_records.extend(recs)

    if not all_records:
        print("[-] No records extracted.")
        return pd.DataFrame(columns=COLUMNS)

    df_master = pd.DataFrame(all_records, columns=COLUMNS)

    # Deduplicate based on Store + Title + Product_URL
    initial_count = len(df_master)
    # If URL is available, deduplicate by Store + URL; else Store + Title
    df_master = df_master.drop_duplicates(subset=["Source_Store", "Product_URL"], keep="first")
    df_master = df_master.drop_duplicates(subset=["Source_Store", "Title"], keep="first")
    final_count = len(df_master)

    print(f"\n[OK] Aggregation complete: {initial_count} records merged -> {final_count} unique items.")

    # Save to Master CSV (explicit LF line terminator for cross-OS git consistency)
    df_master.to_csv(MASTER_CSV_PATH, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"[OK] Master CSV saved: {MASTER_CSV_PATH}")

    # Ingest into SQLite Database
    save_to_sqlite(df_master, DB_PATH)

    # Pre-render static JSON datasets for GitHub Pages
    try:
        from export_static import export_static_data
        export_static_data(DB_PATH)
    except Exception as e:
        print(f"[!] Warning: static JSON export skipped: {e}")

    # Print Summary Report
    print_market_summary(df_master)

    return df_master


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH):
    """Saves DataFrame into indexed SQLite database for high-performance querying."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing table to refresh
    cursor.execute("DROP TABLE IF EXISTS market_products;")

    # Create table with optimal types
    cursor.execute("""
        CREATE TABLE market_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Source_Store TEXT NOT NULL,
            Category TEXT NOT NULL,
            Title TEXT NOT NULL,
            Raw_Price TEXT,
            Cleaned_Price_LKR REAL,
            Stock_Status TEXT NOT NULL,
            Product_URL TEXT,
            Scraped_Date TEXT
        );
    """)

    # Insert data
    df.to_sql("market_products", conn, if_exists="append", index=False)

    # Create Indexes for fast filtering & search
    cursor.execute("CREATE INDEX idx_products_category ON market_products(Category);")
    cursor.execute("CREATE INDEX idx_products_store ON market_products(Source_Store);")
    cursor.execute("CREATE INDEX idx_products_price ON market_products(Cleaned_Price_LKR);")
    cursor.execute("CREATE INDEX idx_products_stock ON market_products(Stock_Status);")
    cursor.execute("CREATE INDEX idx_products_title ON market_products(Title);")

    conn.commit()
    conn.close()
    print(f"[OK] SQLite Database indexed and saved: {db_path}")


def print_market_summary(df: pd.DataFrame):
    """Prints an executive summary of the scraped competitor intelligence."""
    print("\n" + "=" * 60)
    print("      SRI LANKA PC HARDWARE MARKET INTELLIGENCE SUMMARY      ")
    print("=" * 60)
    print(f"Total Unique SKUs Tracked : {len(df):,}")
    print(f"Active Competitor Stores   : {df['Source_Store'].nunique()}")
    print("-" * 60)

    print("Store Breakdown:")
    store_counts = df["Source_Store"].value_counts()
    for store, count in store_counts.items():
        in_stock = len(df[(df["Source_Store"] == store) & (df["Stock_Status"] == "In Stock")])
        pct = (in_stock / count * 100) if count else 0
        print(f"  - {store:<22}: {count:>5} SKUs ({pct:>5.1f}% In Stock)")

    print("-" * 60)
    print("Category Breakdown:")
    cat_counts = df["Category"].value_counts()
    for cat, count in cat_counts.items():
        cat_df = df[(df["Category"] == cat) & (df["Cleaned_Price_LKR"].notnull())]
        avg_price = cat_df["Cleaned_Price_LKR"].median() if not cat_df.empty else 0
        print(f"  - {cat:<18}: {count:>5} SKUs | Median Price: LKR {avg_price:,.0f}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    compile_master_dataset()
