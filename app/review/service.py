from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.intake.service import inspect
from app.modules.pipeline import assemble
from app.review import revision as revisions


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def execute(store, data):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f"{RULE_VERSION}:{fingerprint}".encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    intake = inspect(data)
    report = assemble(intake)
    report["manifest"] = dict(
        sha256=fingerprint,
        version=RULE_VERSION,
        created=now(),
        duration_ms=round((monotonic() - start) * 1000, 3),
        bytes=len(data),
        run_id=run_id,
    )
    return store.register(run_id, report, rows=intake["rows"])


def _render(store, base_id, record):
    successor = None
    if record["successor_id"]:
        run = store.load(record["successor_id"])
        successor = {
            "id": run["id"],
            "status": run["status"],
            "revision": run["revision"],
        }
    return dict(
        base_id=base_id,
        id=record["successor_id"],
        digest=record["digest"],
        outcome=record["outcome"],
        impact=record["detail"],
        created=record["created"],
        successor=successor,
    )


def revise(store, base_id, data):
    """Adjudicate one late revision file against a signed batch.

    The first execution is recorded under (base_id, digest); replays return the
    stored record unchanged, so no second successor is ever produced.
    """
    base = store.load(base_id)
    if base["status"] != "APPROVED":
        raise DomainIssue("REVISION_BASE_PENDING")
    if not base["rows"]:
        raise DomainIssue("REVISION_BASE_UNSUPPORTED")
    digest = sha256(data).hexdigest()
    existing = store.revision(base_id, digest)
    if existing is not None:
        return _render(store, base_id, existing)

    start = monotonic()
    intake = inspect(data)
    merged, changed = revisions.merge_rows(base["rows"], intake["rows"])
    report = assemble(revisions.merged_intake(merged, intake))
    impacted, cases = revisions.adjudicate(
        revisions.signature(base["report"]), revisions.signature(report), changed
    )
    why = revisions.reason(changed, impacted, intake)
    if impacted:
        outcome = "SUCCESSOR"
        successor_id = sha256(
            f"{RULE_VERSION}:revision:{base_id}:{digest}".encode()
        ).hexdigest()
        report["manifest"] = dict(
            sha256=digest,
            version=RULE_VERSION,
            created=now(),
            duration_ms=round((monotonic() - start) * 1000, 3),
            bytes=len(data),
            run_id=successor_id,
            base_id=base_id,
        )
        store.register(
            successor_id, report, rows=merged, kind="REVISION", base_id=base_id
        )
    else:
        outcome = "NO_IMPACT"
        successor_id = None
    detail = revisions.detail(
        base_id, digest, intake, changed, cases, impacted, why
    )
    record = store.record_revision(
        base_id, digest, outcome, successor_id, detail, now()
    )
    return _render(store, base_id, record)


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue("REVIEW_FIELDS")
    revision, status, note = (values.get(key) for key in ("revision", "status", "note"))
    if (
        type(revision) is not int
        or revision < 0
        or status not in ("APPROVED", "HELD")
        or not isinstance(note, str)
        or not (3 <= len(note.strip()) <= 200)
    ):
        raise DomainIssue("REVIEW_FIELDS")
    current = store.load(run_id)
    if revision != current["revision"]:
        raise DomainIssue("STALE_REVIEW")
    if current["status"] == "APPROVED":
        raise DomainIssue("RUN_FINALIZED")
    if status == "APPROVED" and not current["report"]["balance"]["releasable"]:
        raise DomainIssue("UNRESOLVED_ISSUES")
    return store.revise(run_id, revision, status, note.strip(), now())
