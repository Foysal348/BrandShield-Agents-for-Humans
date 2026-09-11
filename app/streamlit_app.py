"""Streamlit demo for BrandShield's human-governed investigation workflow."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from brandshield.agent import generate_reviewer_narrative  # noqa: E402
from brandshield.config import Settings  # noqa: E402
from brandshield.models import CatalogProduct, CaseStatus, ListingInput  # noqa: E402
from brandshield.risk_engine import RiskEngine, render_case_file  # noqa: E402
from brandshield.storage import SQLiteCaseRepository  # noqa: E402
from brandshield.workflow import CaseWorkflow  # noqa: E402


def _catalog_from_row(row: pd.Series) -> CatalogProduct:
    data = row.to_dict()
    data["authorized_sellers"] = [
        seller.strip()
        for seller in str(data["authorized_sellers"]).split("|")
        if seller.strip()
    ]
    data["reference_image_url"] = data.get("reference_image_url") or None
    return CatalogProduct.model_validate(data)


def _listing_from_row(row: pd.Series) -> ListingInput:
    data = row.to_dict()
    for field in ("claimed_sku", "listing_url", "image_url"):
        value = data.get(field)
        data[field] = None if pd.isna(value) or value == "" else value
    return ListingInput.model_validate(data)


def _resolved_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _display_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo("Asia/Dhaka")).strftime("%d %b %Y, %I:%M:%S %p")


def _display_details(details: dict[str, object]) -> str:
    return " | ".join(
        f"{key.replace('_', ' ').title()}: {value}"
        for key, value in details.items()
        if value is not None
    )


def _compact_markdown(document: str) -> str:
    """Reduce downloaded-document headings when previewed inside the app."""
    lines: list[str] = []
    for line in document.splitlines():
        if line.startswith("# "):
            line = f"### {line[2:]}"
        elif line.startswith("## "):
            line = f"#### {line[3:]}"
        lines.append(line)
    return "\n".join(lines)


def _status_color(status: CaseStatus) -> str:
    return {
        CaseStatus.NEW: "blue",
        CaseStatus.UNDER_REVIEW: "orange",
        CaseStatus.APPROVED: "green",
        CaseStatus.REJECTED: "red",
        CaseStatus.CLOSED: "gray",
    }[status]


@st.cache_data
def _load_demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = pd.read_csv(ROOT / "data" / "sample_catalog.csv", keep_default_na=False)
    listings = pd.read_csv(ROOT / "data" / "sample_listings.csv", keep_default_na=False)
    return catalog, listings


@st.cache_resource
def _build_workflow(database_path: str) -> CaseWorkflow:
    return CaseWorkflow(SQLiteCaseRepository(database_path))


settings = Settings.from_env()
workflow = _build_workflow(str(_resolved_path(settings.database_path)))
repository = workflow.repository

st.set_page_config(page_title="BrandShield", page_icon="🛡️", layout="wide")
st.title("🛡️ BrandShield")
st.caption("Transparent counterfeit-risk triage with human-controlled enforcement")

catalog_df, listings_df = _load_demo_data()

analyze_tab, dashboard_tab = st.tabs(["Analyze listing", "Case dashboard"])

with analyze_tab:
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
    score_col.metric("Risk score", f"{assessment.score}/100", border=True)
    level_col.metric("Priority", assessment.level.value.upper(), border=True)
    seller_col.metric(
        "Seller status",
        "AUTHORIZED"
        if not any(signal.code == "unauthorized_seller" for signal in assessment.signals)
        else "NOT ON ALLOWLIST",
        border=True,
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
            width="stretch",
        )
    else:
        st.success("No configured risk signals were triggered.")

    st.subheader("Recommended next step")
    st.write(assessment.recommended_action)
    can_open_case = assessment.score >= 25
    with st.container(horizontal=True):
        if st.button(
            "Open investigation case",
            type="primary",
            icon=":material/create_new_folder:",
            disabled=not can_open_case,
            help=(
                None
                if can_open_case
                else "Low-risk listings remain in monitoring and do not need a case."
            ),
        ):
            opened_case = workflow.open_case(listing, product)
            st.session_state["selected_case_id"] = opened_case.case_id
            st.success(f"Created {opened_case.case_id}. Open the Case dashboard tab.")
        st.download_button(
            "Download assessment",
            data=case_file,
            file_name=f"brandshield-assessment-{listing.listing_id}.md",
            mime="text/markdown",
            icon=":material/download:",
        )
    if not can_open_case:
        st.caption("Low-risk result: continue monitoring; no investigation case is needed.")

    with st.expander("View assessment"):
        st.markdown(_compact_markdown(case_file))

    with st.expander("Optional Strands + Amazon Bedrock narrative"):
        st.warning(
            "This optional action calls Amazon Bedrock and may consume AWS credits. "
            "The deterministic workflow does not use AWS."
        )
        if st.button("Generate reviewer narrative with Bedrock"):
            try:
                with st.spinner("Generating a human-review narrative..."):
                    st.write(generate_reviewer_narrative(case_file))
            except Exception as exc:
                st.error(
                    "Bedrock could not be called. Confirm AWS credentials, region, model "
                    f"access, and BEDROCK_MODEL_ID. Details: {exc}"
                )

with dashboard_tab:
    cases = repository.list_cases()
    st.subheader("Investigation queue")
    if not cases:
        st.info("No cases yet. Open one from the Analyze listing tab.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Case": case.case_id,
                        "Listing": case.listing.listing_id,
                        "Score": case.assessment.score,
                        "Priority": case.assessment.level.value.upper(),
                        "Status": case.status.value.upper().replace("_", " "),
                        "Updated": _display_time(case.updated_at),
                    }
                    for case in cases
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%d",
                ),
                "Case": st.column_config.TextColumn("Case", pinned=True),
            },
        )
        st.caption("Times shown in Asia/Dhaka.")

        case_ids = [case.case_id for case in cases]
        default_case_id = st.session_state.get("selected_case_id")
        default_index = case_ids.index(default_case_id) if default_case_id in case_ids else 0
        selected_case_id = st.selectbox("Select a case", case_ids, index=default_index)
        st.session_state["selected_case_id"] = selected_case_id
        selected_case = repository.get_case(selected_case_id)

        status_col, score_col, reviewer_col = st.columns(3)
        status_col.metric(
            "Status",
            selected_case.status.value.upper().replace("_", " "),
            border=True,
        )
        score_col.metric(
            "Risk score",
            f"{selected_case.assessment.score}/100",
            border=True,
        )
        reviewer_col.metric(
            "Reviewer",
            selected_case.reviewer_name or "Not assigned",
            border=True,
        )
        with st.container(horizontal=True):
            st.badge(
                selected_case.status.value.upper().replace("_", " "),
                color=_status_color(selected_case.status),
            )
            st.badge(
                selected_case.assessment.level.value.upper(),
                color=(
                    "red"
                    if selected_case.assessment.score >= 75
                    else "orange"
                    if selected_case.assessment.score >= 50
                    else "blue"
                ),
            )

        st.markdown("#### Human decision controls")
        reviewer = st.text_input(
            "Reviewer name",
            value=selected_case.reviewer_name or "",
            key=f"reviewer-{selected_case_id}",
        )
        decision_note = st.text_area(
            "Decision note",
            value=selected_case.reviewer_note or "",
            key=f"note-{selected_case_id}",
            help="A reason is mandatory when approving or rejecting a case.",
        )

        try:
            if selected_case.status is CaseStatus.NEW:
                if st.button("Start human review", type="primary"):
                    workflow.start_review(
                        selected_case_id,
                        reviewer=reviewer,
                        note=decision_note or None,
                    )
                    st.rerun()
            elif selected_case.status is CaseStatus.UNDER_REVIEW:
                with st.container(horizontal=True):
                    if st.button(
                        "Approve for report drafting",
                        type="primary",
                        icon=":material/check_circle:",
                    ):
                        workflow.record_decision(
                            selected_case_id,
                            approved=True,
                            reviewer=reviewer,
                            note=decision_note,
                        )
                        st.rerun()
                    if st.button("Reject case", icon=":material/cancel:"):
                        workflow.record_decision(
                            selected_case_id,
                            approved=False,
                            reviewer=reviewer,
                            note=decision_note,
                        )
                        st.rerun()
            elif selected_case.status in {CaseStatus.APPROVED, CaseStatus.REJECTED}:
                with st.container(horizontal=True):
                    if selected_case.status is CaseStatus.APPROVED:
                        if st.button(
                            "Create takedown report draft",
                            type="primary",
                            icon=":material/draft:",
                        ):
                            report = workflow.create_report_draft(
                                selected_case_id,
                                actor=reviewer or "human-reviewer",
                            )
                            st.session_state[f"report-{selected_case_id}"] = report
                    if st.button("Close case", icon=":material/archive:"):
                        workflow.close_case(
                            selected_case_id,
                            actor=reviewer,
                            note=decision_note,
                        )
                        st.rerun()
            else:
                st.success("This case is closed and read-only.")
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))

        report_key = f"report-{selected_case_id}"
        if report_key in st.session_state:
            st.markdown("#### Draft report")
            st.warning("Draft only — a human must verify and send it outside BrandShield.")
            st.download_button(
                "Download report draft",
                data=st.session_state[report_key],
                file_name=f"brandshield-report-{selected_case_id}.md",
                mime="text/markdown",
            )
            with st.expander("Preview report draft"):
                st.markdown(st.session_state[report_key])

        st.markdown("#### Evidence audit trail")
        events = repository.list_events(selected_case_id)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Time": _display_time(event.occurred_at),
                        "Event": event.event_type,
                        "Actor": event.actor,
                        "Details": _display_details(event.details),
                    }
                    for event in events
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Time": st.column_config.TextColumn("Time", width="medium"),
                "Event": st.column_config.TextColumn("Event", width="small"),
                "Actor": st.column_config.TextColumn("Actor", width="medium"),
                "Details": st.column_config.TextColumn("Details", width="large"),
            },
        )
