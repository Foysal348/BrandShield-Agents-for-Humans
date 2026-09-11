# BrandShield — Agents for Humans

BrandShield is a human-governed brand-protection agent built with the Strands Agents SDK.
It identifies suspicious signals in product listings, creates auditable investigation case
files, and keeps every legal or enforcement decision under human control.

> BrandShield produces review-priority assessments, not counterfeit verdicts.

## Current milestone

- Validated product-catalog and marketplace-listing models
- Transparent deterministic scoring for seller, price, brand, SKU, language, and title signals
- Downloadable Markdown investigation case files
- Streamlit demo using clearly synthetic data
- Optional Strands + Amazon Bedrock reviewer narrative
- Persistent SQLite investigation cases with controlled lifecycle transitions
- Named human approval/rejection with mandatory decision notes
- Database-enforced append-only evidence audit trail
- Human-gated marketplace review/takedown report drafts
- Case-management dashboard and automated workflow tests
- Autonomous batch monitoring that continues past malformed records
- Duplicate suppression and seller/product reappearance linking
- Content-addressed JSON evidence snapshots with SHA-256 integrity verification
- Persisted monitoring-run summaries and a decision-only analyst queue
- Strands human-in-the-loop confirmation before report-drafting tool calls
- Safe submission simulation that never sends a network request

## Local setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest
streamlit run app\streamlit_app.py
```

The deterministic demo, monitoring cycle, evidence capture, and tests do not need AWS
credentials and do not call paid services.

## Demo flow

1. Open **Autonomous monitoring** and run the synthetic feed.
2. Confirm that low-risk items stay quiet while review-worthy listings create cases.
3. Observe `LIST-004` being linked as a reappearance of the earlier seller/product offer.
4. Open **Case dashboard**, verify the evidence SHA-256, and start a named human review.
5. Approve the case, create a report draft, then use **Simulate marketplace submission**.
6. Inspect the audit trail: the simulation records `external_request_sent: false`.

Running the same feed again reuses existing cases and records duplicate observations instead
of creating an endless queue.

## Optional AWS narrative

The Bedrock narrative button is optional. Configure `AWS_PROFILE`, `AWS_REGION`, and
`BEDROCK_MODEL_ID` in your local `.env`, then ensure that profile has narrowly scoped Bedrock
permissions. Calling Bedrock may consume AWS credits. Never commit `.env` or AWS credentials.

## Project structure

```text
app/                    Streamlit demo
data/                   Synthetic catalog and listing fixtures
src/brandshield/        Models, scoring, monitoring, evidence, workflow, agent, and tools
tests/                  Deterministic unit tests
docs/                   Architecture and submission documentation
assets/                 Diagrams and demo assets
```

## Human governance

The scoring engine explains every point it adds. The optional language model may summarize
the resulting case, but it cannot submit a takedown or make the final determination. A human
reviewer must verify evidence and approve any external action.

The agent intentionally has no approve, reject, close, or send-takedown tool. Those actions
remain behind named human controls in the dashboard. Report drafts are available only after a
case moves through `new -> under_review -> approved`.

The Strands agent exposes six purposeful tools: single-listing assessment, autonomous batch
monitoring, case opening, case lookup, case-list filtering, and approved report drafting. A
Strands intervention pauses before the report-drafting tool and requires an explicit human
confirmation. Even after confirmation, BrandShield only produces a draft; it has no external
submission integration.

## License

MIT
