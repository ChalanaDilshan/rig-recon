"""
orchestrator.py - Master Pipeline Orchestrator for Sri Lanka PC Pricing Intelligence

Orchestrates:
1. Target store scrapers execution (with isolated error recovery)
2. Data normalization (cleaner.py)
3. Master dataset compilation & SQLite DB indexing (merger.py)
"""

import sys
import time
import argparse
import importlib
from datetime import datetime
from typing import List, Dict
from scrapers import SCRAPER_REGISTRY
from merger import compile_master_dataset


def run_single_scraper(store_key: str, max_pages: int = 5, headless: bool = True) -> Dict:
    """Executes a single store scraper with isolated error recovery."""
    info = SCRAPER_REGISTRY.get(store_key)
    if not info:
        return {"store": store_key, "status": "NOT FOUND", "duration": 0, "error": "Unknown store"}

    store_name = info["name"]
    module_name = info["module"]
    print("\n" + "=" * 65)
    print(f"  EXECUTING SCRAPER: [{store_name}] ({info['type']})")
    print(f"  Description: {info['description']}")
    print("=" * 65)

    start_time = time.time()
    try:
        mod = importlib.import_module(module_name)

        # Inspect if run function accepts headless parameter
        import inspect
        sig = inspect.signature(mod.run)
        kwargs = {"max_pages": max_pages}
        if "headless" in sig.parameters:
            kwargs["headless"] = headless

        saved_csv = mod.run(**kwargs)
        duration = round(time.time() - start_time, 2)
        print(f"[OK] Completed {store_name} in {duration}s -> {saved_csv}")
        return {"store": store_name, "status": "SUCCESS", "duration": duration, "error": None}

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        print(f"[FAILED] Scraper failed for {store_name} after {duration}s: {e}")
        return {"store": store_name, "status": "FAILED", "duration": duration, "error": str(e)}


def list_stores():
    """Prints all supported competitor stores."""
    print("\nSupported Sri Lankan PC Hardware Stores:")
    print("-" * 65)
    for key, info in SCRAPER_REGISTRY.items():
        print(f"  - {key:<14}: {info['name']:<22} [{info['type']}]")
    print("-" * 65 + "\n")


def orchestrate_pipeline(
    target_stores: List[str],
    max_pages: int = 5,
    headless: bool = True,
    auto_merge: bool = True
):
    """Orchestrates the entire scraping and intelligence compilation pipeline."""
    pipeline_start = time.time()
    results = []

    print("\n" + "#" * 65)
    print("  STARTING PC HARDWARE COMPETITOR PRICING INTELLIGENCE PIPELINE  ")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target Stores: {len(target_stores)} selected")
    print("#" * 65)

    for store_key in target_stores:
        res = run_single_scraper(store_key, max_pages=max_pages, headless=headless)
        results.append(res)
        # Brief pause between store scraper runs
        time.sleep(2)

    # Print Scraper Execution Summary
    print("\n" + "=" * 65)
    print("                SCRAPER EXECUTION SUMMARY                ")
    print("=" * 65)
    for r in results:
        status_tag = "[PASS]" if r["status"] == "SUCCESS" else "[FAIL]"
        err_msg = f" (Error: {r['error']})" if r["error"] else ""
        print(f"  {status_tag:<7} {r['store']:<24} {r['duration']:>6.1f}s {err_msg}")
    print("=" * 65)

    # Post-scraping Data Compilation
    if auto_merge:
        print("\n[+] Triggering Master Compilation & SQLite Ingestion...")
        df_master = compile_master_dataset()
        print(f"[OK] Master pipeline finished with {len(df_master):,} total SKUs.")

    total_time = round(time.time() - pipeline_start, 2)
    print(f"\n[OK] Entire pipeline executed in {total_time} seconds.\n")


def main():
    parser = argparse.ArgumentParser(description="Sri Lanka PC Pricing Intelligence Pipeline")
    parser.add_argument("--all", action="store_true", help="Run scrapers for all supported stores")
    parser.add_argument("--store", nargs="+", help="Run scrapers for specific store(s) by key")
    parser.add_argument("--list", action="store_true", help="List all registered competitor stores")
    parser.add_argument("--merge-only", action="store_true", help="Compile and normalize raw data without re-scraping")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages to crawl per category (default: 5)")
    parser.add_argument("--headful", action="store_true", help="Launch Playwright browsers in visible headful mode")
    parser.add_argument("--no-merge", action="store_true", help="Skip automatic master dataset compilation")

    args = parser.parse_args()

    if args.list:
        list_stores()
        return

    if args.merge_only:
        print("\n[+] Running Master Dataset Merger & Cleaner...")
        compile_master_dataset()
        return

    headless = not args.headful

    if args.all:
        target_keys = list(SCRAPER_REGISTRY.keys())
    elif args.store:
        target_keys = []
        for s in args.store:
            key = s.lower().strip()
            if key in SCRAPER_REGISTRY:
                target_keys.append(key)
            else:
                print(f"[!] Warning: Store key '{s}' not recognized. Use --list to view valid keys.")
    else:
        print("[!] No action specified. Use --all, --store <names>, --merge-only, or --list.")
        parser.print_help()
        return

    if not target_keys:
        print("[!] No valid stores to scrape.")
        return

    orchestrate_pipeline(
        target_stores=target_keys,
        max_pages=args.max_pages,
        headless=headless,
        auto_merge=not args.no_merge
    )


if __name__ == "__main__":
    main()
