# Remote Job Bot V4 — verified roles + 80/20 prioritization

This is an update of V3. Install dependencies with `py -m pip install -r requirements.txt`, then run `py job_bot.py`.

## Search configuration
- **Primary**: 80% software development (full stack, frontend, backend, web/software development, Shopify, eCommerce, Bubble).
- **Secondary**: 20% AI training, coding evaluation, annotation, labeling, categorization.
- Quotas are *targets* for up to 100 listings. When one group has too few matches, the other fills remaining slots. It does not invent jobs.
- Specific stacks such as Java, Spring Boot, NestJS, Prisma, React, Node.js, and Python are **not claimed as verified skills**. Broad full-stack listings may mention them, but no stack-specific keyword targeting is activated until you confirm them.
- 7 years full stack, 5 years Shopify/eCommerce, 3 years Bubble, and 2 months annotation/AI evaluation are used as profile metadata; no claim is made about skill level in other technologies.
- Existing job sources and excluded Lemon.io remain unchanged.
- Job eligibility remains **likely eligible** or **needs verification**, not guaranteed. Set `strict_eligibility_only` to true to exclude unverified listings.

## Export
`output/jobs_YYYY-MM-DD.csv` includes exactly `Company Name`, `Role`, `Compensation`, `Job Link`. CSV opens in Excel. Compensation is not invented.

## Important limitations
The 80/20 split is applied to the *exported top 100*, not enforced as a minimum number of listings. The source APIs may return fewer jobs. Some job-board APIs can change or fail; the script logs source errors. A role title match does not establish that the employer accepts Philippines-based applicants; review before applying. This release does not add new source APIs.
