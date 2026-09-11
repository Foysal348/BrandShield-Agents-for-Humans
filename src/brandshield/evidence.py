"""Content-addressed evidence snapshots for reproducible investigations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from brandshield.models import (
    CatalogProduct,
    EvidenceArtifact,
    ListingInput,
    RiskAssessment,
)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def listing_identity_fingerprint(listing: ListingInput, product: CatalogProduct) -> str:
    """Identify a seller/product offer while allowing a new marketplace listing ID."""
    normalized_title = " ".join(re.findall(r"[a-z0-9]+", listing.title.casefold()))
    identity = {
        "marketplace": listing.marketplace.casefold(),
        "seller_id": listing.seller_id.casefold(),
        "catalog_sku": product.sku.casefold(),
        "normalized_title": normalized_title,
    }
    return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


class EvidenceStore:
    """Write immutable-by-name JSON snapshots under a controlled artifact directory."""

    def __init__(self, root_path: str | Path) -> None:
        self.root_path = Path(root_path)

    def capture(
        self,
        listing: ListingInput,
        product: CatalogProduct,
        assessment: RiskAssessment,
    ) -> EvidenceArtifact:
        captured_at = datetime.now(UTC)
        payload = {
            "schema_version": "evidence-v1",
            "listing": listing.model_dump(mode="json"),
            "catalog_product": product.model_dump(mode="json"),
            "assessment": assessment.model_dump(mode="json"),
        }
        canonical = _canonical_json(payload)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        relative_path = Path("evidence") / f"{digest}.json"
        target = self.root_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
        return EvidenceArtifact(
            sha256=digest,
            relative_path=relative_path.as_posix(),
            identity_fingerprint=listing_identity_fingerprint(listing, product),
            captured_at=captured_at,
        )

    def verify(self, artifact: EvidenceArtifact) -> bool:
        """Verify that a stored snapshot still matches its recorded SHA-256 digest."""
        target = (self.root_path / artifact.relative_path).resolve()
        root = self.root_path.resolve()
        if root not in target.parents or not target.is_file():
            return False
        payload = json.loads(target.read_text(encoding="utf-8"))
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        return digest == artifact.sha256
