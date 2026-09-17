"""
scrapers package - Registry for all 11 Sri Lankan PC Hardware Store Scrapers
"""

from typing import Dict, Any

SCRAPER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "nanotek": {
        "name": "Nanotek",
        "module": "scrapers.nanotek",
        "type": "SSR / requests",
        "engine": "Requests / BeautifulSoup",
        "url": "https://www.nanotek.lk",
        "csv_pattern": "nanotek",
        "description": "Nanotek.lk PHP/CS-Cart catalog scraper"
    },
    "mdcomputers": {
        "name": "MD Computers",
        "module": "scrapers.mdcomputers",
        "type": "curl_cffi",
        "engine": "curl_cffi (TLS Impersonate)",
        "url": "https://mdcomputers.lk",
        "csv_pattern": "mdcomputers",
        "description": "MDComputers.lk WooCommerce catalog scraper"
    },
    "tulip": {
        "name": "Tulip Computers",
        "module": "scrapers.tulip",
        "type": "Playwright CSR",
        "engine": "Playwright Chromium",
        "url": "https://tulipcom.lk",
        "csv_pattern": "tulip",
        "description": "Tulipcom.lk dynamic SPA storefront scraper"
    },
    "chama": {
        "name": "Chama Computers",
        "module": "scrapers.chamacomputers",
        "type": "Playwright CSR",
        "engine": "Playwright Chromium",
        "url": "https://chamacomputers.lk",
        "csv_pattern": "chama",
        "description": "Chamacomputers.lk React dynamic storefront scraper"
    },
    "gamestreet": {
        "name": "Game Street",
        "module": "scrapers.gamestreet",
        "type": "curl_cffi / requests",
        "engine": "curl_cffi / Requests",
        "url": "https://gamestreet.lk",
        "csv_pattern": "game_street",
        "description": "Gamestreet.lk Custom PHP catalog scraper"
    },
    "pcbuilders": {
        "name": "PC Builders",
        "module": "scrapers.pcbuilders",
        "type": "requests / curl_cffi",
        "engine": "Requests / BeautifulSoup",
        "url": "https://pcbuilders.lk",
        "csv_pattern": "pcbuilders",
        "description": "Pcbuilders.lk WooCommerce catalog scraper"
    },
    "redline": {
        "name": "Redline Technologies",
        "module": "scrapers.redlinetech",
        "type": "requests / curl_cffi",
        "engine": "Requests / BeautifulSoup",
        "url": "https://redlinetech.lk",
        "csv_pattern": "redlinetech",
        "description": "Redlinetech.lk WooCommerce catalog scraper"
    },
    "msk": {
        "name": "MSK Computers",
        "module": "scrapers.mskcomputers",
        "type": "Playwright AJAX",
        "engine": "Playwright Chromium",
        "url": "https://mskcomputers.lk",
        "csv_pattern": "msk",
        "description": "Mskcomputers.lk CSR with AJAX filter hydration"
    },
    "techzone": {
        "name": "Techzone",
        "module": "scrapers.techzone",
        "type": "curl_cffi + Playwright",
        "engine": "curl_cffi + Playwright",
        "url": "https://techzone.lk",
        "csv_pattern": "techzone",
        "description": "Techzone.lk WooCommerce with Cloudflare bypass"
    },
    "redtech": {
        "name": "Red Tech",
        "module": "scrapers.redtech",
        "type": "Playwright Woodmart",
        "engine": "Playwright Chromium",
        "url": "https://redtech.lk",
        "csv_pattern": "redtech",
        "description": "Redtech.lk Woodmart theme scraper"
    },
    "gallelaptop": {
        "name": "Galle Laptop",
        "module": "scrapers.gallelaptop",
        "type": "Playwright PHP",
        "engine": "Playwright Chromium",
        "url": "https://gallelaptop.lk",
        "csv_pattern": "galle",
        "description": "Gallelaptop.lk dynamic subcategory scraper"
    }
}
