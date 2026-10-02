# Automation Architecture

## Execution pipeline

1. Discover public job links.
2. Normalize and deduplicate jobs.
3. Persist jobs in the SQLite job library.
4. Match jobs against a saved profile.
5. Analyze requirements and application readiness.
6. Launch a persistent Playwright browser session.
7. Detect form fields across pages and frames.
8. Classify fields semantically.
9. Auto-fill only verified profile facts.
10. Pause for missing, sensitive, legal, or ambiguous questions.
11. Re-scan after dynamic UI changes.
12. Upload a compatible resume input when detected.
13. Validate visible errors.
14. Navigate through Next/Continue steps.
15. Stop at final submission for explicit human approval.
16. Click submit exactly once.
17. Verify a portal confirmation.
18. Persist lifecycle events and application state.

## Safety boundaries

- CAPTCHA and access challenges are manual.
- MFA and login are manual.
- Sensitive/legal answers are never inferred silently.
- Final submission requires explicit human approval.
- An uncertain submission is never automatically retried.
- Duplicate logical applications are blocked by persistent application identity.

## Local deployment

Copy `.env.example` to `.env`, configure `LOCAL_API_TOKEN`, then run the existing unit-test and API/frontend commands from the project root.

## Docker

Use `docker compose up --build` to start the API and Streamlit frontend with persistent local state.

API health endpoint: `/health`

Frontend port: `8501`

Production deployments should place the API behind TLS and use a managed secret store and database when multiple hosts/workers are required.
