"""The Applications tab: a household-visible tracker on the shared Google Sheet.

Every job that reaches state `applied` becomes one row, however it got there -
the engine after a real submission, her "I applied by hand" on a queue card,
or a plain tick on the jobs list. Sync is append-only and idempotent: the
Fingerprint column keys what is already written, so each cycle costs one read
and (usually) zero writes. Nothing here ever deletes or edits a row - the
sheet is hers to annotate, and a re-run must never eat her notes.
"""

from __future__ import annotations

from typing import Any

TAB = "Applications"
HEADER = ["Applied on", "Company", "Title", "How", "Link", "Fingerprint"]

# How the application happened, judged from the queue's own record:
#   submitted by the engine        -> "automatic"
#   submitted, note 'applied by hand' (the queue card button) -> "by hand"
#   applied status with no queue item (the tick on the jobs list) -> "marked applied"


def _how(fp: str, queue_items: dict[str, dict]) -> str:
    item = queue_items.get(fp)
    if not item or item.get("kind") != "application":
        return "marked applied"
    if item.get("state") != "submitted":
        return "marked applied"
    if "by hand" in str(item.get("note") or "").lower():
        return "by hand"
    return "automatic"


def applied_rows(
    statuses: dict[str, dict],
    store_by_fp: dict[str, dict],
    queue_items: dict[str, dict],
) -> list[list[str]]:
    """One sheet row per applied fingerprint, oldest first."""
    rows: list[list[str]] = []
    for fp, entry in statuses.items():
        if entry.get("state") != "applied":
            continue
        job = store_by_fp.get(fp) or {}
        rows.append([
            str(entry.get("at") or "")[:10],
            str(job.get("company") or ""),
            str(job.get("title") or ""),
            _how(fp, queue_items),
            str(job.get("url") or ""),
            fp,
        ])
    rows.sort(key=lambda r: r[0])
    return rows


def sync(client: Any, spreadsheet_id: str, statuses: dict[str, dict],
         store_by_fp: dict[str, dict], queue_items: dict[str, dict]) -> int:
    """Append rows for applied jobs the sheet does not know yet.

    Returns how many rows were written. Raises whatever the client raises -
    the caller decides how loud a Google problem should be."""
    wanted = applied_rows(statuses, store_by_fp, queue_items)
    if not wanted:
        return 0

    existing = client.sheet_tab_rows(spreadsheet_id, TAB)
    if existing is None:
        client.sheet_add_tab(spreadsheet_id, TAB)
        existing = []
    if not existing:
        client.sheet_append(spreadsheet_id, TAB, [HEADER])

    known = {row[-1] for row in existing[1:] if row}
    # Her own annotations may reorder or extend columns; keying on the last
    # non-empty cell would be fragile, so scan the whole row for fingerprints.
    for row in existing[1:]:
        known.update(cell for cell in row if cell)

    fresh = [row for row in wanted if row[-1] not in known]
    if fresh:
        client.sheet_append(spreadsheet_id, TAB, fresh)
    return len(fresh)
