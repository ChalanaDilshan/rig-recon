# Rig-Recon 🇱🇰

> Automated competitor pricing intelligence & inventory reconnaissance pipeline for Sri Lankan PC hardware retailers.

Rig-Recon continuously monitors, scrapes, normalizes, and compares hardware pricing and availability across Sri Lanka's leading computer stores. It features an automated multi-threaded scraping engine, a regex-driven categorization and data normalization pipeline, and an interactive executive pricing intelligence dashboard.

---

## 🚀 Key Features

- **Multi-Store Reconnaissance Engine**:
  Custom scrapers supporting static, dynamic CSR (Playwright), and anti-bot protected (Cloudflare / curl_cffi) storefronts:
  - **Nanotek** (nanotek.lk)
  - **MD Computers** (mdcomputers.lk)
  - **Chama Computers** (chamacomputers.lk)
  - **Game Street** (gamestreet.lk)
  - **Tulip Computers** (tulipcom.lk)
  - **PC Builders** (pcbuilders.lk)
  - **Redline Technologies** (redlinetech.lk)
  - **MSK Computers** (mskcomputers.lk)

- **High-Precision Data Normalization (`cleaner.py`)**:
  - Currency normalization (extracts pure numerical LKR prices from installments, formatted strings, and promo banners).
  - Strict hierarchical categorization across 9 standard hardware categories (`GPU`, `Laptop`, `Monitor`, `Motherboard`, `CPU`, `RAM`, `Storage`, `PSU`, `Casing`).
  - Distinguishes complete systems (Laptops and prebuilt gaming PCs) from standalone components (GPUs, CPUs, RAM) to eliminate category leakage.

- **Unified Master Dataset & Indexing (`merger.py`)**:
  - Automatic deduplication across vendors.
  - Generates master CSV (`data/sri_lanka_pc_market_data.csv`).
  - Compiles indexed SQLite database (`data/market_data.db`) for sub-millisecond query performance.

- **Executive Intelligence Dashboard (`dashboard.py`)**:
  - FastAPI backend serving a responsive, dark-mode glassmorphic interface.
  - Live filtering across stores, categories, and stock status.
  - Real-time cross-store price comparison matrix with automatic savings spread calculation.

---

## 🛠️ Project Structure

```
rig-recon/
├── cleaner.py          # Data normalization & category classification engine
├── merger.py           # Master dataset compiler & SQLite indexing
├── orchestrator.py     # Scraper pipeline execution runner
├── dashboard.py        # FastAPI intelligence dashboard backend
├── requirements.txt    # Python dependencies
├── scrapers/           # Modular store scraper modules
│   ├── base_scraper.py
│   ├── chamacomputers.py
│   ├── gamestreet.py
│   ├── mdcomputers.py
│   ├── mskcomputers.py
│   ├── nanotek.py
│   ├── pcbuilders.py
│   ├── redlinetech.py
│   ├── tulip.py
│   └── ...
├── data/               # Raw & processed market data
│   ├── raw/            # Scraped CSV catalogs per store
│   ├── market_data.db  # Indexed SQLite database
│   └── sri_lanka_pc_market_data.csv
├── templates/          # Dashboard HTML templates
└── static/             # Vanilla CSS and JS assets
```

---

## ⚡ Quick Start

### 1. Installation

```bash
git clone https://github.com/ChalanaDilshan/rig-recon.git
cd rig-recon
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the Dashboard

```bash
python dashboard.py
```
Open your browser at **`http://127.0.0.1:8000`** to view the live dashboard.

### 3. Run Store Scrapers & Refresh Data

To run all scrapers and compile the master database:
```bash
python orchestrator.py --all
```

To run a specific store scraper (e.g. Nanotek):
```bash
python orchestrator.py --store nanotek --pages 5
```

To re-compile and index existing raw data:
```bash
python merger.py
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
