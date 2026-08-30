"""
Phase 7 — Evidence Grouping Service.

Groups evidence observations by structural origin:
- By Webhook Event (SAME_WEBHOOK_EVENT)
- By Payment Event (SAME_PAYMENT_EVENT)
- By System Source (SAME_SOURCE)

Preserves raw evidence records as immutable; groups represent organizational structures.
"""
from __future__ import annotations

from typing import List, Dict
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_structure import EvidenceGroup, EvidenceGroupMember
from app.models.structure_types import GroupType


class GroupingService:
    """
    Deterministic grouping engine for evidence observations.
    """

    RULE_VERSION = "1.0"

    @classmethod
    def group_payment_evidence(
        cls,
        db: Session,
        payment_id: str,
        observations: List[EvidenceObservation],
    ) -> List[EvidenceGroup]:
        """
        Groups all observations for a payment across supported structural axes.
        Returns the list of EvidenceGroups formed.
        """
        if not observations:
            return []

        # 1. Group by Payment Event
        by_payment_event: Dict[int, List[EvidenceObservation]] = {}
        # 2. Group by Webhook Event
        by_webhook_event: Dict[int, List[EvidenceObservation]] = {}
        # 3. Group by Source Type
        by_source: Dict[str, List[EvidenceObservation]] = {}

        for obs in observations:
            if obs.payment_event_id is not None:
                by_payment_event.setdefault(obs.payment_event_id, []).append(obs)
            if obs.webhook_event_id is not None:
                by_webhook_event.setdefault(obs.webhook_event_id, []).append(obs)
            if obs.source_type:
                by_source.setdefault(obs.source_type, []).append(obs)

        groups: List[EvidenceGroup] = []

        # Create/Update SAME_PAYMENT_EVENT groups
        for pe_id, items in by_payment_event.items():
            grp = cls._get_or_create_group(
                db=db,
                payment_id=payment_id,
                group_type=GroupType.SAME_PAYMENT_EVENT.value,
                grouping_key=f"payment_event_{pe_id}",
                metadata={"payment_event_id": pe_id, "observation_count": len(items)},
            )
            cls._ensure_members(db, grp, items)
            groups.append(grp)

        # Create/Update SAME_WEBHOOK_EVENT groups
        for we_id, items in by_webhook_event.items():
            grp = cls._get_or_create_group(
                db=db,
                payment_id=payment_id,
                group_type=GroupType.SAME_WEBHOOK_EVENT.value,
                grouping_key=f"webhook_event_{we_id}",
                metadata={"webhook_event_id": we_id, "observation_count": len(items)},
            )
            cls._ensure_members(db, grp, items)
            groups.append(grp)

        # Create/Update SAME_SOURCE groups
        for src, items in by_source.items():
            grp = cls._get_or_create_group(
                db=db,
                payment_id=payment_id,
                group_type=GroupType.SAME_SOURCE.value,
                grouping_key=f"source_{src}",
                metadata={"source_type": src, "observation_count": len(items)},
            )
            cls._ensure_members(db, grp, items)
            groups.append(grp)

        db.flush()
        return groups

    @classmethod
    def _get_or_create_group(
        cls,
        db: Session,
        payment_id: str,
        group_type: str,
        grouping_key: str,
        metadata: dict,
    ) -> EvidenceGroup:
        grp = (
            db.query(EvidenceGroup)
            .filter(
                EvidenceGroup.payment_id == payment_id,
                EvidenceGroup.group_type == group_type,
                EvidenceGroup.grouping_key == grouping_key,
            )
            .first()
        )
        if not grp:
            grp = EvidenceGroup(
                payment_id=payment_id,
                group_type=group_type,
                grouping_key=grouping_key,
                rule_version=cls.RULE_VERSION,
                metadata_=metadata,
            )
            db.add(grp)
            db.flush()
        else:
            grp.metadata_ = metadata
            grp.rule_version = cls.RULE_VERSION

        return grp

    @classmethod
    def _ensure_members(
        cls,
        db: Session,
        group: EvidenceGroup,
        observations: List[EvidenceObservation],
    ) -> None:
        for obs in observations:
            member = (
                db.query(EvidenceGroupMember)
                .filter(
                    EvidenceGroupMember.group_id == group.internal_id,
                    EvidenceGroupMember.evidence_id == obs.internal_id,
                )
                .first()
            )
            if not member:
                member = EvidenceGroupMember(
                    group_id=group.internal_id,
                    evidence_id=obs.internal_id,
                )
                db.add(member)
