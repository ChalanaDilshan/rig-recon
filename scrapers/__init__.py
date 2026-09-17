"""
scrapers package - Registry for all 10 Sri Lankan PC Hardware Store Scrapers
"""

from typing import Dict, Any

SCRAPER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "nanotek": {
        "name": "Nanotek",
        "module": "scrapers.nanotek",
        "type": "SSR / requests",
        "description": "Nanotek.lk PHP/CS-Cart catalog scraper"
    },
    "techzone": {
        "name": "Techzone",
        "module": "scrapers.techzone",
        "type": "curl_cffi + Playwright",
        "description": "Techzone.lk WooCommerce with Cloudflare bypass"
    },
    "mdcomputers": {
        "name": "MD Computers",
        "module": "scrapers.mdcomputers",
        "type": "curl_cffi",
        "description": "MDComputers.lk WooCommerce catalog scraper"
    },
    "chama": {
        "name": "Chama Computers",
        "module": "scrapers.chamacomputers",
        "type": "Playwright CSR",
        "description": "Chamacomputers.lk React dynamic storefront scraper"
    },
    "gamestreet": {
        "name": "Game Street",
        "module": "scrapers.gamestreet",
        "type": "curl_cffi / requests",
        "description": "Gamestreet.lk Custom PHP catalog scraper"
    },
    "msk": {
        "name": "MSK Computers",
        "module": "scrapers.mskcomputers",
        "type": "Playwright AJAX",
        "description": "Mskcomputers.lk CSR with AJAX filter hydration"
    },
    "pcbuilders": {
        "name": "PC Builders",
        "module": "scrapers.pcbuilders",
        "type": "requests / curl_cffi",
        "description": "Pcbuilders.lk WooCommerce catalog scraper"
    },
    "tulip": {
        "name": "Tulip Computers",
        "module": "scrapers.tulip",
        "type": "Playwright CSR",
        "description": "Tulipcom.lk dynamic SPA storefront scraper"
    },
    "redline": {
        "name": "Redline Technologies",
        "module": "scrapers.redlinetech",
        "type": "requests / curl_cffi",
        "description": "Redlinetech.lk WooCommerce catalog scraper"
    },
    "redtech": {
        "name": "Red Tech",
        "module": "scrapers.redtech",
        "type": "Playwright Woodmart",
        "description": "Redtech.lk Woodmart theme scraper"
    },
    "gallelaptop": {
        "name": "Galle Laptop",
        "module": "scrapers.gallelaptop",
        "type": "Playwright PHP",
        "description": "Gallelaptop.lk dynamic subcategory scraper"
    }
}
