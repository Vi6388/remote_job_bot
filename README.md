# Remote Job Discovery Bot — MVP

Searches public job APIs, deduplicates results, scores developer positions, and exports new listings to CSV and SQLite. No paid API key is needed.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python job_bot.py
```

The report appears in `output/new_jobs_YYYY-MM-DD.csv`. The SQLite file stores seen URLs, so subsequent runs only export newly found postings. Delete `jobs.sqlite3` to reset history.

## Schedule daily

Create a GitHub repository and commit these files, including `.github/workflows/daily.yml`. In the GitHub Actions tab, run the workflow manually or wait for its daily schedule. Download the CSV from the run's **Artifacts** section. GitHub Actions schedules may be delayed; job history does not persist between hosted runs unless external storage is added. As provided, each hosted run starts with a new database and its CSV contains all currently matching jobs, not only jobs newly seen since the prior GitHub run.

## Increase coverage

Add real company board identifiers to `greenhouse_boards` and `ashby_boards` in `config.json`. Example: `https://boards.greenhouse.io/COMPANY` means board identifier `COMPANY`. Only add boards you have verified; the bot does not discover employer headquarters automatically.

## Important limitations

- 100 **new, eligible** roles per day cannot be guaranteed from two public feeds. Add verified employer career pages and other authorized feeds to increase coverage.
- `likely_eligible` is a keyword heuristic, not a verified legal hiring entitlement. Always read the complete JD before applying.
- Europe/Australia prioritization is inferred from listing text, **not verified employer headquarters**. Future version should use a curated company registry.
- The location filter is conservative but cannot catch every restriction. Remote-only eligibility must be reviewed.
- Some public API fields can be missing, stale, or change format. The program handles failed sources and exports available results.
- Do not scrape sites that prohibit it or automatically submit applications without permission.
- This MVP does **not** generate tailored resumes or send notifications yet.
