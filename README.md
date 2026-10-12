EchoChain: Circular Economy & Secondary Market Lifecycle Analytics

Joining internal manufacturing data with secondary-market listings to show which product models are worth a buy-back and refurbishment program.

Built with: Python, pandas, SQL (SQLite), RapidFuzz, Power BI (DAX), Excel, Jupyter

This was a group project completed during a Data Analyst internship at Infotact Solutions Pvt. Ltd. AI tools were used as a coding and brainstorming assistant during development.

All data in this repository is simulated. The results demonstrate the method, not real market findings.


The problem

Manufacturers track products rigorously until the point of sale. After that, the product's lifecycle becomes a data blind spot. That makes it hard to measure true environmental impact, landfill diversion, or the potential for profitable refurbishment.

The idea: the Circularity Score

A Sustainability Executive needs one answer per product model: is a buy-back program worth running?

EchoChain combines two things the business already has or can see:

Internal data: the bill of materials (BOM) and warranty failure rates for each component
External data: what the same models and parts sell for on secondary marketplaces

If a model's critical component fails often, devices get scrapped. If the other parts still resell for a large share of their original cost, that value is being thrown away. The Circularity Score puts a number on that gap.

How it works
Stage	What happens
1. Data generation	Internal BOM and warranty data for 5 laptop models x 5 components, plus 600 simulated secondary-market listings across 4 platforms. Titles are deliberately messy: typos, naming variants, stray whitespace
2. Cleaning	Lowercase, strip punctuation, collapse whitespace
3. Fuzzy matching	Each listing is matched to a model with RapidFuzz (partial_ratio, cutoff 70). The component is detected from keywords. Low-confidence matches are dropped, as a production job would send them to a review queue
4. Aggregation	Median resale price per model and component, compared with the original unit cost to get a resale retention percentage
5. Scoring	Circularity Score and a buy-back flag per model
6. Storage and reporting	SQLite database, Excel report, CSVs for Power BI, and a dashboard
The score
circularity_score = critical_failure_rate x avg_salvageable_resale_retention
Critical failure rate: warranty failure rate of the component that gets a device scrapped (the motherboard)
Salvageable resale retention: average resale price as a percentage of original cost for the non-critical parts (display, battery, RAM, SSD)

A model is flagged as a buy-back candidate when critical failure is at least 8% and salvageable retention is at least 40%.

Results (simulated data, reference run)

Matching quality, measured against the true labels kept in the simulated data:

Metric	Result
Listings matched to the correct model	100% (600 of 600)
Listings matched to the correct component	98.5%

All 9 component errors share one cause: the noise step splits a word with a stray space (for example "motherboa rd"), and the keyword matcher misses the broken word. Fuzzy-matching the component keywords too would fix it.

Model	Critical failure	Salvageable retention	Circularity Score	Recoverable parts value	Status
Dell XPS 15	13.1%	58.7%	7.7	$109	Buy-back fit
Asus VivoBook 15	10.0%	64.4%	6.5	$124	Buy-back fit
Acer Aspire 5	9.8%	58.7%	5.8	$119	Buy-back fit
HP Pavilion 14	7.6%	62.7%	4.8	$111	Monitor
Lenovo ThinkPad T14	4.9%	75.0%	3.7	$140	Monitor

Reading the table:

Dell XPS 15 is the priority: the highest motherboard failure rate, with parts that still hold value.
HP Pavilion 14 is a near miss at 7.6%, just under the 8% threshold.
Lenovo ThinkPad T14 has the highest recoverable value but the lowest failure rate. Valuable parts are only an opportunity if devices actually come back, so there is little supply to harvest.

These figures are from one reference run of EchoChain_Analysis.ipynb. The saved notebook outputs and the CSVs in powerbi_data/ come from that same run. Re-running the notebook draws new random listings, so expect the same pattern but different figures: Dell XPS 15's Circularity Score has ranged from about 7 to 9 across runs, and the order of the other models can shuffle. Critical failure rates stay fixed, because the BOM data is seeded, which keeps Dell XPS 15's lead on motherboard failure stable.

Power BI dashboard

The Power BI model uses three tables joined on model:

Models  1 ---> *  Components
Models  1 ---> *  Listings

Measures written in DAX (full code in powerbi/EchoChain_Measures.dax.txt):

KPI	Measure
Buy-back candidates	Buy-back Candidates
Critical failure rate	Critical Failure Rate %
Salvageable retention	Salvageable Resale Retention %
Circularity score	Circularity Score
Recoverable value per device	Avg Recoverable Value per Device (USD)
Listings analysed	Total Listings
Matching accuracy	Model Match Accuracy %, Component Match Accuracy %

The two thresholds (8% failure, 40% retention) are measures too, so they can be changed in seconds and the dashboard updates.


Getting started

Requirements: Python 3.9 or newer.

bash
pip install -r requirements.txt notebook

Option A: the notebook (recommended). The whole pipeline in one file, with explanations and charts.

bash
jupyter notebook

Open EchoChain_Analysis.ipynb and choose Kernel, Restart & Run All. It creates echochain.db and an outputs/ folder next to itself.

Option B: the scripts. The same logic split into modules. Run them in order from the project folder:

bash
python generate_data.py
python etl_pipeline.py
python export_excel.py

Regenerate the Power BI tables. After either option above, this reads echochain.db and writes powerbi_data/Models.csv, Components.csv and Listings.csv:

bash
python export_powerbi_pack.py

The notebook and the scripts generate their own random data, so their figures differ. The scripts are seeded and give identical results on every run. The notebook is not fully seeded, so each run produces new figures. To make it reproducible, add np.random.seed(42) to the setup cell, and expect the numbers in this README to change.

Repository structure
.
├── README.md
├── requirements.txt
├── EchoChain_Analysis.ipynb      # full pipeline with saved outputs
├── paths.py                      # shared, portable path config for the scripts
├── generate_data.py              # simulated BOM and marketplace listings
├── etl_pipeline.py               # clean, fuzzy-match, aggregate, score
├── export_excel.py               # formatted Excel report
├── export_powerbi_pack.py        # CSV tables for Power BI
├── powerbi_data/                 # Models.csv, Components.csv, Listings.csv
├── powerbi/
│   ├── EchoChain_Measures.dax.txt
│   ├── EchoChain_Theme.json
│   ├── EchoChain_PowerQuery.m.txt
│   └── EchoChain_PowerBI_Build_Guide.md
├── dashboard/
│   └── echochain_dashboard.html  # standalone dashboard
├── docs/
│   └── EchoChain_Stakeholder_Talk_Track.md
└── images/

Design decisions
Simulated listings. Marketplace sites restrict scraping in their terms of service, so the listings are generated with the same shape and messiness a real scrape would have. To use real data, replace generate_scraped_listings() with a compliant scraper or an official marketplace API that writes the same columns. The rest of the pipeline is unchanged.
pandas and SQLite at this scale. With 600 listings these are the right tools. The transforms (clean, match, aggregate, score) are written as separate functions so they could be ported to a distributed engine if the volume grew.
A bug worth knowing about. RapidFuzz's process.extractOne does not lowercase the choices by default. Comparing lowercased titles with mixed-case model names silently dropped every Dell listing until the matcher was fixed with processor=utils.default_process.
Limitations
Simulated data. The BOM, warranty rates and listings are generated, so the ranking shows the method, not real findings about these laptops.
Simple score. It multiplies two rates. It ignores sales volume, refurbishment labour and logistics cost, so a high-scoring model with low volume may not be worth a program.
Asking prices. Secondary listings show asking prices, not final sale prices.
Judgement thresholds. The 8% and 40% cut-offs are placeholders for a business rule. HP Pavilion 14 becomes a candidate if the failure threshold is lowered slightly.
No time dimension. Listings have no scrape date, so trends over time are not analysed.
Possible improvements
Replace the simulated listings with a real marketplace API or compliant scraper
Weight the score by sales volume and add refurbishment cost to get a profit estimate
Add unit weights to estimate landfill diversion in tonnes
Fuzzy-match component keywords too, and route low-confidence matches to a review queue
Schedule the pipeline and track scores over time
Acknowledgements

Thanks to Infotact Solutions Pvt. Ltd. for the internship opportunity and project brief, for guidance, and to my teammates.
