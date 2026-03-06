# Domain Flipper Configuration

# Datenbank
DB_PATH = "data/expired_domains.db"

# Scraping-Limits (Rate-Limiting)
REQUESTS_PER_MINUTE = 30
DELAY_BETWEEN_REQUESTS = 2  # Sekunden

# Bewertungs-Kriterien
MIN_DOMAIN_LENGTH = 3
MAX_DOMAIN_LENGTH = 30
HIGH_POTENTIAL_THRESHOLD = 70  # Score 0-100

# TLD-Prioritäten (0-20 Punkte)
TLD_SCORES = {
    "com": 20,
    "ai": 18,
    "io": 17,
    "co": 16,
    "app": 15,
    "de": 15,
    "net": 12,
    "org": 12,
    "info": 8,
    "xyz": 8,
}

# Keywords die Wert erhöhen
PREMIUM_KEYWORDS = [
    "ai", "app", "tech", "crypto", "nft", "web3", "cloud", "data",
    "health", "money", "pay", "shop", "store", "game", "play",
    "home", "auto", "car", "fit", "gym", "food", "eat"
]

# API-Keys (werden aus .env geladen)
DYNADOT_API_KEY = None  # Aus .env: DYNADOT_API_KEY
NAMECHEAP_API_USER = None
NAMECHEAP_API_KEY = None

# Budget-Limits für Auto-Kauf (VORSICHT!)
MAX_AUTO_BUY_BUDGET = 0  # 0 = deaktiviert, erst manuelle Freigabe
SINGLE_DOMAIN_MAX_PRICE = 100  # USD

# Reporting
TOP_N_DOMAINS = 10
REPORT_OUTPUT_PATH = "data/daily_report.txt"
