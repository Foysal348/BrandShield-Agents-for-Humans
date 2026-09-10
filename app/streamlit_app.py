"""Streamlit demo for the BrandShield deterministic review workflow."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from brandshield.agent import generate_reviewer_narrative  # noqa: E402
from brandshield.models import CatalogProduct, ListingInput  # noqa: E402
from brandshield.risk_engine import RiskEngine, render_case_file  # noqa: E402


def _catalog_from_row(row: pd.Series) -> CatalogProduct:
    data = row.to_dict()
    data["authorized_sellers"] = [
        seller.strip() for seller in str(data["authorized_sellers"]).split("|") if seller.strip()
    ]
    data["reference_image_url"] = data.get("reference_image_url") or None
    return CatalogProduct.model_validate(data)


def _listing_from_row(row: pd.Series) -> ListingInput:
    data = row.to_dict()
    for field in ("claimed_sku", "listing_url", "image_url"):
        value = data.get(field)
        data[field] = None if pd.isna(value) or value == "" else value
    return ListingInput.model_validate(data)


st.set_page_config(page_title="BrandShield", page_icon="🛡️", layout="wide")
st.title("🛡️ BrandShield")
st.caption("Transparent counterfeit-risk triage with human-controlled enforcement")

catalog_df = pd.read_csv(ROOT / "data" / "sample_catalog.csv", keep_default_na=False)
listings_df = pd.read_csv(ROOT / "data" / "sample_listings.csv", keep_default_na=False)

selected_id = st.selectbox(
    "Choose a synthetic marketplace listing",
    listings_df["listing_id"].tolist(),
    format_func=lambda listing_id: (
        f"{listing_id} — "
        f"{listings_df.loc[listings_df['listing_id'] == listing_id, 'title'].iloc[0]}"
    ),
)

listing_row = listings_df.loc[listings_df["listing_id"] == selected_id].iloc[0]
listing = _listing_from_row(listing_row)
product_row = catalog_df.loc[catalog_df["sku"] == listing.claimed_sku]

if product_row.empty:
    st.error("No matching catalog product exists for this listing.")
    st.stop()

product = _catalog_from_row(product_row.iloc[0])
assessment = RiskEngine().assess(listing, product)
case_file = render_case_file(listing, product, assessment)

score_col, level_col, seller_col = st.columns(3)
score_col.metric("Risk score", f"{assessment.score}/100")
level_col.metric("Priority", assessment.level.value.upper())
seller_col.metric(
    "Seller status",
    "AUTHORIZED"
    if not any(signal.code == "unauthorized_seller" for signal in assessment.signals)
    else "NOT ON ALLOWLIST",
)

st.info(assessment.disclaimer)
st.subheader("Observed evidence signals")
if assessment.signals:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Signal": signal.label,
                    "Points": signal.points,
                    "Explanation": signal.explanation,
                }
                for signal in assessment.signals
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.success("No configured risk signals were triggered.")

st.subheader("Human review")
st.write(assessment.recommended_action)
st.download_button(
    "Download auditable case file",
    data=case_file,
    file_name=f"brandshield-case-{listing.listing_id}.md",
    mime="text/markdown",
)

with st.expander("View case file"):
    st.markdown(case_file)

with st.expander("Optional Strands + Amazon Bedrock narrative"):
    st.warning(
        "This optional action calls Amazon Bedrock and may consume AWS credits. "
        "The deterministic assessment above does not use AWS."
    )
    if st.button("Generate reviewer narrative with Bedrock"):
        try:
            with st.spinner("Generating a human-review narrative..."):
                st.write(generate_reviewer_narrative(case_file))
        except Exception as exc:  # The UI should explain missing credentials/access cleanly.
            st.error(
                "Bedrock could not be called. Confirm AWS credentials, region, model access, "
                f"and BEDROCK_MODEL_ID. Details: {exc}"
            )
