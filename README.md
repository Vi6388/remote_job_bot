# A Complete Job Platform

A **single Streamlit application** containing the existing Remote Job Bot V4 and Job Application Studio V2.1, now linked by the latest bot CSV. No previous ZIP is required.

## Windows installation

1. Extract the ZIP to a writable directory.
2. Install Python 3.10+ and ensure `py` works in PowerShell.
3. Open PowerShell inside the extracted `A_Complete_Job_Platform` directory.
4. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501 if the browser does not open automatically.

## Workflow

1. Open **Job Discovery** in the Streamlit sidebar. Click **Find jobs now**. It fetches public remote-job APIs and writes `bot/output/jobs_YYYY-MM-DD.csv` with exactly: `Company Name`, `Role`, `Compensation`, `Job Link`.
2. Open **Application Studio**. It automatically detects the latest bot CSV; you can instead upload a CSV manually.
3. Upload your **verified, structured master resume JSON** (use `master_resume.example.json` as a format reference). Do not assume the example resume describes your actual employment history.
4. Enter an OpenAI API key (or set `OPENAI_API_KEY` in your environment). Choose a supported model, select jobs, paste full descriptions when a job site blocks extraction, and generate.
5. Download `application_packages.zip`. Each successfully processed job gets its own folder with `A_resume.docx`, `A_resume.pdf`, `A_cover_letter.docx`, and `job_description.txt`.

## Constraints and safety

- Bot target: **100 daily leads**, **80% software / 20% AI**; targets are not guaranteed. Job descriptions may omit or ambiguously describe work authorization. **Check that the employer explicitly accepts Philippines-based remote applicants.** The bot excludes obvious regional restrictions but cannot reliably prove eligibility.
- The bot searches only job titles matching verified role families (full stack, web/software development, Shopify/eCommerce, Bubble, coding AI evaluation, annotation). It does **not** assume React, Node.js, Java, Spring Boot, Prisma, etc. You may edit `bot/config.json` after verifying additional skills.
- Sources: Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas and optionally configured public company boards. The application does **not** scrape all previously discussed job websites.
- The Studio calls OpenAI only when you click Generate. API usage is billed separately. The Studio does not automatically submit job applications.
- Review AI-produced claims and job descriptions. The code preserves structured employment company, title and dates, but **human verification remains essential**.
- Run locally only; do not expose the Streamlit service publicly. Job page fetching is not hardened for hostile multi-user deployments.
- `bot/jobs.sqlite3` stores past discovered postings locally. The ZIP does not include real job data or a completed personal resume.

## Offline checks

Run `py -m pytest tests -q` to check configuration, filename conventions, and CSV normalization without contacting job websites or OpenAI.
