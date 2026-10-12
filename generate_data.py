"""
EchoChain — synthetic data generator.

Live eBay scraping isn't available in this environment (no network access to
marketplace sites, and eBay's ToS restricts scraping). This script stands in
for the Scrapy spider output + internal BOM export, producing data with the
same shape, messiness, and relationships a real pipeline would see. Swap
`generate_scraped_listings()` for a real Scrapy pipeline (or eBay's Browse
API) and the rest of the pipeline is unchanged.
"""
import os
import random
import pandas as pd
from faker import Faker
from paths import OUTPUT_DIR

random.seed(42)
fake = Faker()

# ---------------------------------------------------------------------------
# 1. Internal manufacturing data: models -> components (the BOM)
# ---------------------------------------------------------------------------
MODELS = [
    "Dell XPS 15",
    "HP Pavilion 14",
    "Lenovo ThinkPad T14",
    "Asus VivoBook 15",
    "Acer Aspire 5",
]

# component: (unit_cost_usd, critical, base_failure_rate_pct)
# "critical" = device is usually scrapped (not user-repaired) when this fails
COMPONENT_TEMPLATE = {
    "Motherboard":    (180, True,  None),
    "Display Panel":  (90,  False, None),
    "Battery":        (35,  False, None),
    "RAM Module":      (25,  False, None),
    "SSD Storage":    (45,  False, None),
}

# Per-model failure-rate multipliers so some models are visibly worse than others
MODEL_RELIABILITY = {
    "Dell XPS 15": 1.4,        # known motherboard issues
    "HP Pavilion 14": 0.8,
    "Lenovo ThinkPad T14": 0.6,  # built tough
    "Asus VivoBook 15": 1.1,
    "Acer Aspire 5": 1.0,
}

BASE_FAILURE_RATE = {
    "Motherboard": 9.0,
    "Display Panel": 4.0,
    "Battery": 11.0,
    "RAM Module": 1.5,
    "SSD Storage": 2.5,
}


def generate_bom():
    rows = []
    sku_counter = 1000
    for model in MODELS:
        for component, (cost, critical, _) in COMPONENT_TEMPLATE.items():
            sku_counter += 1
            failure_rate = round(
                BASE_FAILURE_RATE[component] * MODEL_RELIABILITY[model]
                * random.uniform(0.85, 1.15), 2
            )
            rows.append({
                "sku": f"SKU-{sku_counter}",
                "model": model,
                "component": component,
                "unit_cost_usd": cost,
                "critical_component": critical,
                "warranty_failure_rate_pct": failure_rate,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Simulated scraped secondary-market listings (messy, like real scrapes)
# ---------------------------------------------------------------------------
CONDITIONS = ["New", "Open Box", "Used - Like New", "Used - Good",
              "Used - Fair", "For Parts/Repair"]

# Messy real-world naming variants scrapers actually encounter
MODEL_ALIASES = {
    "Dell XPS 15": ["Dell XPS 15 9530", "DELL XPS15", "Dell Xps 15 laptop", "XPS 15 9520"],
    "HP Pavilion 14": ["HP Pavilion 14", "HP Pavillion 14 dv", "Hewlett Packard Pavilion 14"],
    "Lenovo ThinkPad T14": ["Lenovo ThinkPad T14", "ThinkPad T14 Gen 2", "Lenovo Think Pad T 14"],
    "Asus VivoBook 15": ["ASUS Vivobook 15", "Asus Vivo Book 15", "Asus VivoBook15 X1500"],
    "Acer Aspire 5": ["Acer Aspire 5", "ACER ASPIRE5", "Acer Aspire-5 A515"],
}

COMPONENT_LISTING_PHRASES = {
    "Display Panel": ["LCD screen assembly", "display panel replacement",
                       "screen (genuine OEM)", "LED display"],
    "Battery": ["replacement battery", "OEM battery pack", "battery (used, tested)"],
    "Motherboard": ["motherboard (untested)", "logic board for parts",
                     "motherboard - boots fine"],
    "RAM Module": ["RAM stick", "memory module"],
    "SSD Storage": ["SSD drive", "NVMe storage"],
}

PLATFORMS = ["eBay", "OLX", "Cashify", "Quikr"]


def _resale_price(base_cost, condition, is_part):
    multiplier = {
        "New": 1.1, "Open Box": 0.9, "Used - Like New": 0.75,
        "Used - Good": 0.55, "Used - Fair": 0.35, "For Parts/Repair": 0.2,
    }[condition]
    # Whole-device listings are priced off a notional device value, not component cost
    base = base_cost if is_part else base_cost * random.uniform(5.5, 7.5)
    noise = random.uniform(0.85, 1.15)
    return round(base * multiplier * noise, 2)


def generate_scraped_listings(bom_df, n_listings=600):
    rows = []
    for _ in range(n_listings):
        row = bom_df.sample(1).iloc[0]
        model, component = row["model"], row["component"]
        is_part_listing = random.random() < 0.55  # most secondary listings are parts

        condition = random.choice(CONDITIONS)
        if is_part_listing:
            phrase = random.choice(COMPONENT_LISTING_PHRASES[component])
            title = f"{random.choice(MODEL_ALIASES[model])} {phrase} {condition}"
            price = _resale_price(row["unit_cost_usd"], condition, is_part=True)
        else:
            title = f"{random.choice(MODEL_ALIASES[model])} laptop {condition}"
            price = _resale_price(row["unit_cost_usd"], condition, is_part=False)

        # realistic scrape noise: stray whitespace, random case, occasional typo
        if random.random() < 0.15:
            title = title.replace("a", "a ", 1)
        title = title.strip()

        rows.append({
            "listing_id": fake.uuid4()[:8],
            "raw_title": title,
            "platform": random.choice(PLATFORMS),
            "price_usd": price,
            "condition": condition,
            "is_part_listing": is_part_listing,
            # ground truth kept only to validate the fuzzy-matcher later, a real
            # scrape would NOT have these — the matcher has to infer them
            "_true_model": model,
            "_true_component": component if is_part_listing else "Whole Device",
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    bom = generate_bom()
    listings = generate_scraped_listings(bom)
    bom.to_csv(os.path.join(OUTPUT_DIR, "internal_bom.csv"), index=False)
    listings.to_csv(os.path.join(OUTPUT_DIR, "scraped_listings_raw.csv"), index=False)
    print(f"BOM rows: {len(bom)} | Listings rows: {len(listings)}")
    print(bom.head())
    print(listings.head())
