from decimal import Decimal
import sqlite3

import pytest

from brandshield.models import CatalogProduct, CaseStatus, ListingInput
from brandshield.storage import SQLiteCaseRepository
from brandshield.workflow import (
    CaseWorkflow,
    HumanDecisionRequiredError,
    InvalidTransitionError,
)


@pytest.fixture
def product() -> CatalogProduct:
    return CatalogProduct(
        sku="BS-100",
        brand="Northstar",
        official_title="Northstar Trail Runner Pro",
        msrp=Decimal("120.00"),
        currency="USD",
        authorized_sellers=["seller-official", "Northstar Store"],
    )


@pytest.fixture
def listing() -> ListingInput:
    return ListingInput(
        listing_id="LIST-RISKY",
        marketplace="DemoMarket",
        title="Northstar Trail Runner Pro Clearance",
        claimed_brand="Northstar",
        claimed_sku="BS-100",
        seller_id="unknown-77",
        seller_name="Unknown Deals",
        price=Decimal("30.00"),
        currency="USD",
    )


@pytest.fixture
def repository(tmp_path) -> SQLiteCaseRepository:
    return SQLiteCaseRepository(tmp_path / "cases.db")


@pytest.fixture
def workflow(repository: SQLiteCaseRepository) -> CaseWorkflow:
    return CaseWorkflow(repository)


def test_open_case_persists_assessment_and_audit_event(
    workflow: CaseWorkflow,
    repository: SQLiteCaseRepository,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)

    stored = repository.get_case(case.case_id)
    events = repository.list_events(case.case_id)

    assert stored.status is CaseStatus.NEW
    assert stored.assessment.score == 65
    assert stored.version == 1
    assert [event.event_type for event in events] == ["case_created"]


def test_human_can_review_approve_and_create_report(
    workflow: CaseWorkflow,
    repository: SQLiteCaseRepository,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)
    reviewing = workflow.start_review(case.case_id, reviewer="Ayesha Rahman")
    approved = workflow.record_decision(
        case.case_id,
        approved=True,
        reviewer="Ayesha Rahman",
        note="Seller and discount require a platform policy review.",
    )
    report = workflow.create_report_draft(case.case_id, actor="brandshield-agent")

    assert reviewing.status is CaseStatus.UNDER_REVIEW
    assert approved.status is CaseStatus.APPROVED
    assert approved.reviewer_name == "Ayesha Rahman"
    assert "DRAFT" in report
    assert "Do not send" in report
    assert "Listing price: 30.00 USD" in report
    assert "Catalog MSRP: 120.00 USD" in report
    assert "Price-to-MSRP ratio: 25.0%" in report
    assert "Seller is not authorized (+30)" in report
    assert [event.event_type for event in repository.list_events(case.case_id)] == [
        "case_created",
        "review_started",
        "case_approved",
        "report_drafted",
    ]


def test_agent_identity_cannot_make_human_decision(
    workflow: CaseWorkflow,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)

    with pytest.raises(HumanDecisionRequiredError):
        workflow.start_review(case.case_id, reviewer="brandshield-agent")


def test_decision_requires_note(
    workflow: CaseWorkflow,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)
    workflow.start_review(case.case_id, reviewer="Human Reviewer")

    with pytest.raises(HumanDecisionRequiredError):
        workflow.record_decision(
            case.case_id,
            approved=False,
            reviewer="Human Reviewer",
            note="  ",
        )


def test_invalid_transition_and_early_report_are_blocked(
    workflow: CaseWorkflow,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)

    with pytest.raises(InvalidTransitionError):
        workflow.record_decision(
            case.case_id,
            approved=True,
            reviewer="Human Reviewer",
            note="Attempted too early.",
        )
    with pytest.raises(InvalidTransitionError):
        workflow.create_report_draft(case.case_id, actor="brandshield-agent")


def test_rejected_case_can_be_closed(
    workflow: CaseWorkflow,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)
    workflow.start_review(case.case_id, reviewer="Human Reviewer")
    workflow.record_decision(
        case.case_id,
        approved=False,
        reviewer="Human Reviewer",
        note="Evidence was insufficient after manual verification.",
    )

    closed = workflow.close_case(
        case.case_id,
        actor="Human Reviewer",
        note="No further action.",
    )

    assert closed.status is CaseStatus.CLOSED
    assert closed.version == 4


def test_audit_events_cannot_be_updated_or_deleted(
    workflow: CaseWorkflow,
    repository: SQLiteCaseRepository,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)

    connection = sqlite3.connect(repository.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"):
            connection.execute(
                "UPDATE audit_events SET actor = 'changed' WHERE case_id = ?",
                (case.case_id,),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"):
            connection.execute(
                "DELETE FROM audit_events WHERE case_id = ?",
                (case.case_id,),
            )
    finally:
        connection.close()


def test_list_cases_can_filter_by_status(
    workflow: CaseWorkflow,
    repository: SQLiteCaseRepository,
    listing: ListingInput,
    product: CatalogProduct,
) -> None:
    case = workflow.open_case(listing, product)
    workflow.start_review(case.case_id, reviewer="Human Reviewer")

    assert [item.case_id for item in repository.list_cases(CaseStatus.UNDER_REVIEW)] == [
        case.case_id
    ]
    assert repository.list_cases(CaseStatus.APPROVED) == []
