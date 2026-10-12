"""
EchoChain — ETL pipeline.

Architecture note (for the real deployment): this script implements the same
transforms a PySpark job would run on Databricks against Delta Lake tables —
clean -> fuzzy-match -> aggregate -> score. At this data volume pandas is
the right tool; at production scale (millions of scraped listings/day) each
function below maps directly onto a PySpark equivalent:

    clean_title()        -> a Spark UDF or built-in regexp_replace
    match_listings()      -> a broadcast-join + rapidfuzz UDF, or Spark's
                             approxSimilarityJoin (MinHash LSH) for scale
    aggregate + score     -> groupBy().agg() on a Spark DataFrame, written
                             out as a Delta table partitioned by model

Swap pandas.DataFrame for spark.DataFrame and this file is ~80% of the way
to the Databricks job.
"""
import os
import re
import sqlite3
import pandas as pd
from rapidfuzz import fuzz, process, utils
from paths import OUTPUT_DIR, DB_PATH


# ---------------------------------------------------------------------------
# 1. Clean the messy scraped titles
# ---------------------------------------------------------------------------
def clean_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


# ---------------------------------------------------------------------------
# 2. Fuzzy-match each listing to a model (and, for part listings, a component)
# ---------------------------------------------------------------------------
COMPONENT_KEYWORDS = {
    "Display Panel": ["screen", "display", "lcd", "led panel", "panel"],
    "Battery": ["battery"],
    "Motherboard": ["motherboard", "logic board"],
    "RAM Module": ["ram", "memory module", "memory stick"],
    "SSD Storage": ["ssd", "nvme", "storage drive"],
}


def match_component(clean_text: str):
    for component, keywords in COMPONENT_KEYWORDS.items():
        if any(kw in clean_text for kw in keywords):
            return component
    return "Whole Device"


def match_listings(listings: pd.DataFrame, bom: pd.DataFrame,
                    score_cutoff: int = 70) -> pd.DataFrame:
    models = bom["model"].unique().tolist()
    listings = listings.copy()
    listings["clean_title"] = listings["raw_title"].apply(clean_title)

    matched_models, match_scores = [], []
    for text in listings["clean_title"]:
        best = process.extractOne(text, models, scorer=fuzz.partial_ratio,
                                   processor=utils.default_process)
        if best and best[1] >= score_cutoff:
            matched_models.append(best[0])
            match_scores.append(best[1])
        else:
            matched_models.append(None)
            match_scores.append(best[1] if best else 0)

    listings["matched_model"] = matched_models
    listings["match_score"] = match_scores
    listings["matched_component"] = listings["clean_title"].apply(match_component)

    # unmatched listings are dropped, same as a production job would quarantine
    # low-confidence matches to a review queue rather than let them corrupt metrics
    return listings[listings["matched_model"].notna()].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Aggregate resale value per (model, component) and compute scores
# ---------------------------------------------------------------------------
def aggregate_resale_value(matched: pd.DataFrame) -> pd.DataFrame:
    agg = (
        matched.groupby(["matched_model", "matched_component"])
        .agg(
            median_resale_price_usd=("price_usd", "median"),
            listing_count=("price_usd", "size"),
        )
        .reset_index()
        .rename(columns={"matched_model": "model", "matched_component": "component"})
    )
    return agg


def compute_circularity_scores(bom: pd.DataFrame, resale: pd.DataFrame) -> pd.DataFrame:
    # component-level: join BOM cost/failure data onto observed resale value
    comp = bom.merge(resale, on=["model", "component"], how="left")
    comp["median_resale_price_usd"] = comp["median_resale_price_usd"].fillna(0)
    comp["listing_count"] = comp["listing_count"].fillna(0).astype(int)
    comp["resale_retention_pct"] = (
        comp["median_resale_price_usd"] / comp["unit_cost_usd"] * 100
    ).round(1)

    # model-level circularity score:
    #   - critical_failure_rate: how often the device gets scrapped (motherboard)
    #   - harvest_value: average resale retention of the NON-critical, salvageable
    #     components (display, battery, RAM, SSD) — value recoverable via refurb
    rows = []
    for model, grp in comp.groupby("model"):
        critical = grp[grp["critical_component"]]
        salvageable = grp[~grp["critical_component"]]

        critical_failure_rate = critical["warranty_failure_rate_pct"].mean()
        harvest_value = salvageable["resale_retention_pct"].mean()

        # Circularity Score (0-100): scrapped devices (high critical failure)
        # whose parts are still worth harvesting (high resale retention) score
        # highest — that's exactly the buy-back/refurb opportunity.
        circularity_score = round(
            (critical_failure_rate / 100) * harvest_value, 1
        )

        rows.append({
            "model": model,
            "critical_failure_rate_pct": round(critical_failure_rate, 1),
            "avg_salvageable_resale_retention_pct": round(harvest_value, 1),
            "circularity_score": circularity_score,
            "recommend_buyback_program": bool(
                critical_failure_rate >= 8 and harvest_value >= 40
            ),
        })

    model_scores = pd.DataFrame(rows).sort_values(
        "circularity_score", ascending=False
    ).reset_index(drop=True)
    return comp, model_scores


# ---------------------------------------------------------------------------
# 4. Persist to SQLite (stand-in for the Delta Lake tables)
# ---------------------------------------------------------------------------
def persist(bom, matched_listings, component_scores, model_scores):
    conn = sqlite3.connect(DB_PATH)
    bom.to_sql("bom", conn, if_exists="replace", index=False)
    matched_listings.to_sql("matched_listings", conn, if_exists="replace", index=False)
    component_scores.to_sql("component_scores", conn, if_exists="replace", index=False)
    model_scores.to_sql("model_scores", conn, if_exists="replace", index=False)
    conn.close()


if __name__ == "__main__":
    bom = pd.read_csv(os.path.join(OUTPUT_DIR, "internal_bom.csv"))
    listings = pd.read_csv(os.path.join(OUTPUT_DIR, "scraped_listings_raw.csv"))

    matched = match_listings(listings, bom)
    match_accuracy = (matched["matched_model"] == matched["_true_model"]).mean() * 100
    component_accuracy = (
        matched["matched_component"] == matched["_true_component"]
    ).mean() * 100

    resale = aggregate_resale_value(matched)
    component_scores, model_scores = compute_circularity_scores(bom, resale)

    persist(bom, matched, component_scores, model_scores)

    component_scores.to_csv(os.path.join(OUTPUT_DIR, "component_circularity.csv"), index=False)
    model_scores.to_csv(os.path.join(OUTPUT_DIR, "model_circularity_scores.csv"), index=False)

    print(f"Matched {len(matched)}/{len(listings)} listings "
          f"(model-match accuracy vs ground truth: {match_accuracy:.1f}%, "
          f"component-match accuracy: {component_accuracy:.1f}%)")
    print("\n--- Model Circularity Scores ---")
    print(model_scores.to_string(index=False))
    print("\n--- Component-level detail ---")
    print(component_scores[["model", "component", "unit_cost_usd",
                             "warranty_failure_rate_pct", "median_resale_price_usd",
                             "resale_retention_pct", "listing_count"]].to_string(index=False))
