"""Human-governed investigation case lifecycle."""

from __future__ import annotations

from brandshield.evidence import EvidenceStore, listing_identity_fingerprint
from brandshield.models import (
    CatalogProduct,
    CaseStatus,
    InvestigationCase,
    ListingInput,
)
from brandshield.reporting import draft_takedown_report
from brandshield.risk_engine import RiskEngine
from brandshield.storage import SQLiteCaseRepository


class InvalidTransitionError(ValueError):
    """Raised when a requested case status change is not allowed."""


class HumanDecisionRequiredError(PermissionError):
    """Raised when an automated identity attempts a human-only decision."""


class LowRiskCaseError(ValueError):
    """Raised when automation attempts to open a case below the review threshold."""


ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.NEW: {CaseStatus.UNDER_REVIEW},
    CaseStatus.UNDER_REVIEW: {CaseStatus.APPROVED, CaseStatus.REJECTED},
    CaseStatus.APPROVED: {CaseStatus.CLOSED},
    CaseStatus.REJECTED: {CaseStatus.CLOSED},
    CaseStatus.CLOSED: set(),
}

AUTOMATED_ACTORS = {"agent", "brandshield-agent", "brandshield-system", "system"}


class CaseWorkflow:
    def __init__(
        self,
        repository: SQLiteCaseRepository,
        risk_engine: RiskEngine | None = None,
        evidence_store: EvidenceStore | None = None,
        review_threshold: int = 25,
    ) -> None:
        self.repository = repository
        self.risk_engine = risk_engine or RiskEngine()
        self.evidence_store = evidence_store or EvidenceStore(repository.database_path.parent)
        self.review_threshold = review_threshold

    def open_case(
        self,
        listing: ListingInput,
        product: CatalogProduct,
        *,
        actor: str = "brandshield-system",
    ) -> InvestigationCase:
        assessment = self.risk_engine.assess(listing, product)
        if assessment.score < self.review_threshold:
            raise LowRiskCaseError(
                f"Risk score {assessment.score} is below the case threshold "
                f"of {self.review_threshold}; continue monitoring."
            )

        existing = self.repository.find_case_by_listing_id(listing.listing_id)
        if existing is not None:
            self.repository.append_event(
                existing.case_id,
                event_type="duplicate_listing_observed",
                actor=actor,
                details={"listing_id": listing.listing_id},
            )
            return existing

        evidence = self.evidence_store.capture(listing, product, assessment)
        prior_case = self.repository.find_case_by_identity_fingerprint(
            listing_identity_fingerprint(listing, product),
            exclude_listing_id=listing.listing_id,
        )
        case = InvestigationCase(
            case_id=self.repository.new_case_id(),
            listing=listing,
            product=product,
            assessment=assessment,
            evidence=evidence,
            reappeared_from_case_id=prior_case.case_id if prior_case else None,
        )
        created = self.repository.create_case(case, actor=actor)
        if prior_case is not None:
            self.repository.append_event(
                prior_case.case_id,
                event_type="listing_reappeared",
                actor=actor,
                details={
                    "new_case_id": created.case_id,
                    "new_listing_id": listing.listing_id,
                },
            )
            self.repository.append_event(
                created.case_id,
                event_type="reappearance_linked",
                actor=actor,
                details={"prior_case_id": prior_case.case_id},
            )
        return created

    def start_review(
        self,
        case_id: str,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> InvestigationCase:
        self._require_human_actor(reviewer)
        return self._transition(
            case_id,
            target_status=CaseStatus.UNDER_REVIEW,
            actor=reviewer,
            note=note,
            event_type="review_started",
        )

    def record_decision(
        self,
        case_id: str,
        *,
        approved: bool,
        reviewer: str,
        note: str,
    ) -> InvestigationCase:
        self._require_human_actor(reviewer)
        if not note.strip():
            raise HumanDecisionRequiredError("A human decision note is required.")
        target = CaseStatus.APPROVED if approved else CaseStatus.REJECTED
        event_type = "case_approved" if approved else "case_rejected"
        return self._transition(
            case_id,
            target_status=target,
            actor=reviewer,
            note=note.strip(),
            event_type=event_type,
        )

    def close_case(
        self,
        case_id: str,
        *,
        actor: str,
        note: str,
    ) -> InvestigationCase:
        self._require_human_actor(actor)
        return self._transition(
            case_id,
            target_status=CaseStatus.CLOSED,
            actor=actor,
            note=note.strip() or None,
            event_type="case_closed",
        )

    def create_report_draft(self, case_id: str, *, actor: str) -> str:
        case = self.repository.get_case(case_id)
        if case.status is not CaseStatus.APPROVED:
            raise InvalidTransitionError(
                "A report can be drafted only after a human approves the case."
            )
        report = draft_takedown_report(case)
        self.repository.append_event(
            case_id,
            event_type="report_drafted",
            actor=actor,
            details={"report_type": "marketplace_review_request"},
        )
        return report

    def simulate_submission(
        self,
        case_id: str,
        *,
        actor: str,
        note: str,
    ) -> None:
        """Record a no-network submission simulation for an approved, drafted case."""
        self._require_human_actor(actor)
        case = self.repository.get_case(case_id)
        if case.status is not CaseStatus.APPROVED:
            raise InvalidTransitionError(
                "Submission can be simulated only for a human-approved case."
            )
        if not self.repository.has_event(case_id, "report_drafted"):
            raise InvalidTransitionError(
                "Create and verify a report draft before simulating submission."
            )
        if not note.strip():
            raise HumanDecisionRequiredError(
                "A human simulation note is required."
            )
        self.repository.append_event(
            case_id,
            event_type="submission_simulated",
            actor=actor,
            details={
                "note": note.strip(),
                "external_request_sent": False,
            },
        )

    def _transition(
        self,
        case_id: str,
        *,
        target_status: CaseStatus,
        actor: str,
        note: str | None,
        event_type: str,
    ) -> InvestigationCase:
        current = self.repository.get_case(case_id)
        if target_status not in ALLOWED_TRANSITIONS[current.status]:
            raise InvalidTransitionError(
                f"Cannot transition case from {current.status.value} to {target_status.value}."
            )
        return self.repository.transition(
            case_id,
            target_status=target_status,
            actor=actor,
            note=note,
            event_type=event_type,
        )

    @staticmethod
    def _require_human_actor(actor: str) -> None:
        normalized = actor.strip().casefold()
        if not normalized or normalized in AUTOMATED_ACTORS:
            raise HumanDecisionRequiredError(
                "A named human reviewer is required for this action."
            )
