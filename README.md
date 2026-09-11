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

The deterministic demo and tests do not need AWS credentials and do not call paid services.

## Optional AWS narrative

The Bedrock narrative button is optional. Configure `AWS_PROFILE`, `AWS_REGION`, and
`BEDROCK_MODEL_ID` in your local `.env`, then ensure that profile has narrowly scoped Bedrock
permissions. Calling Bedrock may consume AWS credits. Never commit `.env` or AWS credentials.

## Project structure

```text
app/                    Streamlit demo
data/                   Synthetic catalog and listing fixtures
src/brandshield/        Models, scoring, workflow, storage, reporting, agent, and tools
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

## License

MIT
