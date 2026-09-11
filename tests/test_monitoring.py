import sqlite3
from decimal import Decimal

from strands.interventions import Confirm, Proceed

from brandshield.interventions import DraftReportApprovalIntervention
from brandshield.models import CatalogProduct, MonitoringOutcome
from brandshield.monitoring import MonitoringService
from brandshield.storage import SQLiteCaseRepository
from brandshield.workflow import CaseWorkflow


def _product() -> CatalogProduct:
    return CatalogProduct(
        sku="BS-100",
        brand="Northstar",
        official_title="Northstar Trail Runner Pro",
        msrp=Decimal("120.00"),
        authorized_sellers=["official"],
    )


def _listing(listing_id: str, *, risky: bool = True) -> dict[str, object]:
    return {
        "listing_id": listing_id,
        "marketplace": "DemoMarket",
        "title": "Northstar Trail Runner Pro",
        "claimed_brand": "Northstar",
        "claimed_sku": "BS-100",
        "seller_id": "unknown" if risky else "official",
        "seller_name": "Unknown Deals" if risky else "Official Store",
        "price": "30.00" if risky else "120.00",
        "currency": "USD",
    }


def test_monitoring_continues_after_error_and_links_reappearance(tmp_path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    workflow = CaseWorkflow(repository)
    service = MonitoringService(workflow)
    malformed = _listing("BROKEN")
    malformed["price"] = "0"

    run = service.scan_batch(
        [
            _listing("LOW", risky=False),
            _listing("RISK-1"),
            malformed,
            _listing("RISK-2"),
        ],
        [_product()],
    )

    assert run.total_listings == 4
    assert run.low_risk_count == 1
    assert run.cases_created_count == 1
    assert run.reappearance_count == 1
    assert run.error_count == 1
    assert [result.outcome for result in run.results] == [
        MonitoringOutcome.LOW_RISK,
        MonitoringOutcome.CASE_CREATED,
        MonitoringOutcome.ERROR,
        MonitoringOutcome.REAPPEARANCE,
    ]
    reappearance = repository.get_case(run.results[3].case_id or "")
    assert reappearance.reappeared_from_case_id == run.results[1].case_id
    assert repository.list_monitoring_runs(limit=1)[0].run_id == run.run_id


def test_repeat_scan_reuses_case_and_audits_duplicate(tmp_path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    service = MonitoringService(CaseWorkflow(repository))

    first = service.scan_batch([_listing("RISK-1")], [_product()])
    second = service.scan_batch([_listing("RISK-1")], [_product()])

    assert second.duplicate_count == 1
    assert second.results[0].case_id == first.results[0].case_id
    events = repository.list_events(first.results[0].case_id or "")
    assert events[-1].event_type == "duplicate_listing_observed"


def test_evidence_snapshot_is_content_addressed_and_verifiable(tmp_path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    workflow = CaseWorkflow(repository)
    run = MonitoringService(workflow).scan_batch([_listing("RISK-1")], [_product()])
    case = repository.get_case(run.results[0].case_id or "")

    assert case.evidence is not None
    assert len(case.evidence.sha256) == 64
    assert workflow.evidence_store.verify(case.evidence) is True
    assert (tmp_path / case.evidence.relative_path).is_file()


def test_strands_intervention_confirms_only_report_drafting() -> None:
    intervention = DraftReportApprovalIntervention()
    draft_event = type(
        "Event",
        (),
        {"tool_use": {"name": "draft_case_report", "input": {"case_id": "CASE-1"}}},
    )()
    assess_event = type(
        "Event",
        (),
        {"tool_use": {"name": "assess_listing", "input": {}}},
    )()

    confirmation = intervention.before_tool_call(draft_event)

    assert isinstance(confirmation, Confirm)
    assert "CASE-1" in confirmation.prompt
    assert isinstance(intervention.before_tool_call(assess_event), Proceed)


def test_existing_milestone_two_database_is_migrated(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE investigation_cases (
                case_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                listing_json TEXT NOT NULL,
                product_json TEXT NOT NULL,
                assessment_json TEXT NOT NULL,
                reviewer_name TEXT,
                reviewer_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL
            );
            CREATE TABLE audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            """
        )

    repository = SQLiteCaseRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(investigation_cases)")
        }
        monitoring_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'monitoring_runs'"
        ).fetchone()
    assert {"evidence_json", "reappeared_from_case_id"} <= columns
    assert monitoring_table is not None
    assert repository.list_monitoring_runs() == []
