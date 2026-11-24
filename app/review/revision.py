"""Late revision adjudication.

A revision file covers the same business scope as an already signed batch.
Its accepted rows are merged over the batch's effective rows; every changed
record is recorded for review.  Only a change that moves a case's business
conclusion -- its peak reading or its group verdict -- creates a new pending
successor batch.  All other revision effects are registered as no-impact and
the signed batch is left untouched.
"""

FIELDS = (
    "record",
    "case",
    "kind",
    "minute",
    "meter",
    "kw",
    "window_min",
    "required",
    "note",
)


def signature(report):
    """The business conclusion of every case group.

    Ordering-free case map so a revision can be compared without depending on
    row order or on evidence that does not move the conclusion.
    """
    result = {}
    for case in report.get("cases", []):
        measure = case.get("measure") or {}
        evidence = measure.get("evidence") or {}
        result[case["case"]] = {
            "status": case["status"],
            "peak": measure.get("value"),
            "peak_start_min": evidence.get("peak_start_min"),
        }
    return result


def merge_rows(base_rows, revision_rows):
    """Apply accepted revision rows over the effective signed rows.

    Records are replaced in place, new records append.  The returned change
    list is review evidence; impact is decided by the conclusion signature.
    """
    merged = [dict(row) for row in base_rows]
    index = {row["record"]: position for position, row in enumerate(merged)}
    changed = []
    for row in revision_rows:
        record = row["record"]
        if record in index:
            previous = merged[index[record]]
            if previous != row:
                regrouped = previous["case"] != row["case"]
                changed.append(
                    {
                        "record": record,
                        "case": row["case"],
                        "previous_case": previous["case"],
                        "regrouped": regrouped,
                        "fields": [
                            name
                            for name in FIELDS
                            if previous.get(name) != row.get(name)
                        ],
                    }
                )
                merged[index[record]] = dict(row)
        else:
            changed.append(
                {
                    "record": record,
                    "case": row["case"],
                    "previous_case": None,
                    "regrouped": False,
                    "fields": list(FIELDS),
                    "added": True,
                }
            )
            index[record] = len(merged)
            merged.append(dict(row))
    return merged, changed


def adjudicate(before, after, changed):
    """Compare two conclusion signatures, case by case.

    Peak-window movement alone is reported but is not a conclusion change.
    A peak value, group verdict, group set or a record moving to another
    business group does change the grouping determination and is an impact.
    """
    cases = []
    impacted = any(item["regrouped"] for item in changed)
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old is None:
            changes = ["GROUP_ADDED"]
        elif new is None:
            changes = ["GROUP_REMOVED"]
        else:
            changes = []
            if old["status"] != new["status"]:
                changes.append("STATUS")
            if old["peak"] != new["peak"]:
                changes.append("PEAK")
            if old["peak_start_min"] != new["peak_start_min"]:
                changes.append("PEAK_WINDOW")
        if set(changes) & {"GROUP_ADDED", "GROUP_REMOVED", "STATUS", "PEAK"}:
            impacted = True
        cases.append({"case": name, "before": old, "after": new, "changes": changes})
    return impacted, cases


def reason(changed, impacted, revision):
    """Explain a no-impact registration in reviewer terms."""
    if impacted:
        return None
    discarded = revision["rejected"] + revision["blank"] + revision["repeated"]
    if not changed:
        return "ISOLATED_ONLY" if discarded else "NO_EFFECTIVE_CHANGE"
    if all(set(item["fields"]) <= {"note"} for item in changed):
        return "NOTE_ONLY"
    return "NO_CONCLUSION_CHANGE"


def merged_intake(merged_rows, revision):
    """Intake totals for a successor: merged effective rows plus this file's discards.

    A signed base can only have been released with zero isolated rows, so any
    isolated, blank or repeated lines come from the revision file and stay
    visible to the successor's reviewer.  Totals balance by construction.
    """
    rejected = revision["rejected"]
    blank = revision["blank"]
    repeated = revision["repeated"]
    accepted = len(merged_rows)
    return {
        "input": accepted + rejected + blank + repeated,
        "accepted": accepted,
        "rejected": rejected,
        "blank": blank,
        "repeated": repeated,
        "reasons": revision["reasons"],
        "isolation": revision["isolation"],
        "rows": merged_rows,
    }


def detail(base_id, digest, revision, changed, cases, impacted, why):
    return {
        "base_id": base_id,
        "sha256": digest,
        "status": "IMPACT" if impacted else "NO_IMPACT",
        "reason": why,
        "regrouped": [
            {"record": item["record"], "from": item["previous_case"], "to": item["case"]}
            for item in changed
            if item["regrouped"]
        ],
        "changed_records": changed,
        "cases": cases,
        "revision": {
            key: revision[key]
            for key in ("input", "accepted", "rejected", "blank", "repeated", "reasons")
        },
    }
