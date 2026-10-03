"""Cross-record quality checks run after per-cell cleanup.

These operate on the full record list rather than individual rows, catching
inconsistencies that per-cell validation can't see.
"""
from __future__ import annotations
from collections import defaultdict


def flag_description_pn_groups(records: list[dict]) -> list[dict]:
    """Flag records where the same (ATA, DESCRIPTION) group has multiple PNs.

    When several rows share an ATA chapter and normalised description but
    disagree on PART_NUMBER, that's worth an analyst glance — it could mean
    a data-entry typo, an undocumented mod, or a genuine interchangeable PN.
    Appends ``PART_NUMBER:pn_group_disagree`` to each affected row's _issues.
    """
    if not records:
        return records
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rec in records:
        ata = rec.get("ATA", "").strip()
        desc = rec.get("DESCRIPTION", "").strip().upper()
        pn = rec.get("PART_NUMBER", "").strip()
        if ata and desc and pn:
            groups[(ata, desc)].add(pn)

    disagree_keys = {k for k, pns in groups.items() if len(pns) > 1}
    if not disagree_keys:
        return records

    tag = "PART_NUMBER:pn_group_disagree"
    for rec in records:
        ata = rec.get("ATA", "").strip()
        desc = rec.get("DESCRIPTION", "").strip().upper()
        pn = rec.get("PART_NUMBER", "").strip()
        if not (ata and desc and pn):
            continue
        if (ata, desc) in disagree_keys:
            existing = rec.get("_issues", "")
            if existing:
                rec["_issues"] = f"{existing},{tag}"
            else:
                rec["_issues"] = tag

    return records
