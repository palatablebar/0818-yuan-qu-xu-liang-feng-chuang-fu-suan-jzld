import io

import pytest

from app.business import DomainIssue
from app.evidence.render import artifact
from app.intake.service import inspect
from app.review.service import execute, review, revise
from conftest import csv_data


def source_rows(data):
    return [
        [
            row["record"],
            row["case"],
            row["kind"],
            str(row["minute"]),
            str(row["meter"]),
            str(row["kw"]),
            str(row["window_min"]),
            str(row["required"]),
            row["note"],
        ]
        for row in inspect(data)["rows"]
    ]


def revision_of(data, **changes):
    """Return a same-scope revision file with record-keyed field overrides."""
    rows = source_rows(data)
    for record, fields in changes.items():
        row = next(item for item in rows if item[0] == record)
        for column, value in fields.items():
            row[{"minute": 3, "meter": 4, "kw": 5, "window_min": 6, "required": 7, "note": 8}[column]] = str(value)
    return csv_data(rows)


def signed(store, data):
    run = execute(store, data)
    return review(store, run["id"], dict(revision=0, status="APPROVED", note="月末签发"))


def test_peak_revision_creates_one_pending_successor(store, clean):
    base = signed(store, clean)
    revision = revision_of(clean, **{"000107": {"kw": 90}})
    result = revise(store, base["id"], revision)
    assert result["outcome"] == "SUCCESSOR"
    assert result["id"] and result["id"] != base["id"]
    successor = store.load(result["id"])
    assert successor["status"] == "PENDING" and successor["kind"] == "REVISION"
    assert successor["base_id"] == base["id"]
    assert result["impact"]["status"] == "IMPACT"
    assert any(
        "PEAK" in case["changes"] for case in result["impact"]["cases"]
    )


def test_signed_base_keeps_original_evidence(store, clean):
    base = signed(store, clean)
    original = artifact(store.load(base["id"]))
    revise(store, base["id"], revision_of(clean, **{"000107": {"kw": 90}}))
    assert store.load(base["id"])["status"] == "APPROVED"
    assert artifact(store.load(base["id"])) == original


def test_replaying_same_revision_never_duplicates(store, clean):
    base = signed(store, clean)
    revision = revision_of(clean, **{"000107": {"kw": 90}})
    first = revise(store, base["id"], revision)
    second = revise(store, base["id"], revision)
    assert first == second
    assert len(store.list()) == 2
    assert len(store.revisions(base["id"])) == 1


def test_note_only_revision_is_no_impact(store, clean):
    base = signed(store, clean)
    result = revise(
        store, base["id"], revision_of(clean, **{"000107": {"note": "月末核对"}})
    )
    assert result["outcome"] == "NO_IMPACT"
    assert result["impact"]["reason"] == "NOTE_ONLY"
    assert result["successor"] is None
    assert len(store.list()) == 1


def test_isolated_line_revision_is_no_impact(store, clean):
    base = signed(store, clean)
    revision = revision_of(clean) + "\n\n,broken\n".encode()
    result = revise(store, base["id"], revision)
    assert result["outcome"] == "NO_IMPACT"
    assert result["impact"]["reason"] == "ISOLATED_ONLY"
    assert result["impact"]["revision"]["rejected"] == 1
    assert len(store.list()) == 1


def test_reading_change_without_conclusion_is_no_impact(store, clean):
    base = signed(store, clean)
    result = revise(store, base["id"], revision_of(clean, **{"000104": {"kw": 45}}))
    assert result["outcome"] == "NO_IMPACT"
    assert result["impact"]["reason"] == "NO_CONCLUSION_CHANGE"
    assert result["impact"]["changed_records"][0]["record"] == "000104"
    assert len(store.list()) == 1


def test_peak_window_move_with_same_peak_is_no_impact(store, clean):
    base = signed(store, clean)
    result = revise(store, base["id"], revision_of(clean, **{"000104": {"kw": 70}}))
    assert result["outcome"] == "NO_IMPACT"
    assert result["impact"]["reason"] == "NO_CONCLUSION_CHANGE"
    moved = next(
        case for case in result["impact"]["cases"] if case["case"] == "0001"
    )
    assert moved["changes"] == ["PEAK_WINDOW"]


def test_record_moved_between_groups_is_impact(store, clean):
    base = signed(store, clean)
    rows = source_rows(clean)
    next(row for row in rows if row[0] == "000203")[1] = "0001"
    result = revise(store, base["id"], csv_data(rows))
    assert result["outcome"] == "SUCCESSOR"
    assert result["impact"]["regrouped"] == [
        {"record": "000203", "from": "0002", "to": "0001"}
    ]


def test_new_group_revision_is_impact(store, clean):
    base = signed(store, clean)
    rows = source_rows(clean) + [
        ["000901", "0009", "invoice", "0", "0", "10", "15", "1", "新组"],
        ["000902", "0009", "meter", "0", "1", "0", "0", "0", "新组"],
        ["000903", "0009", "reading", "0", "1", "10", "0", "0", "新组"],
    ]
    result = revise(store, base["id"], csv_data(rows))
    assert result["outcome"] == "SUCCESSOR"
    added = next(case for case in result["impact"]["cases"] if case["case"] == "0009")
    assert added["changes"] == ["GROUP_ADDED"]


def test_peak_change_keeps_ready_and_successor_can_release(store, clean):
    base = signed(store, clean)
    revision = revision_of(
        clean,
        **{"000101": {"kw": 90}, "000106": {"kw": 30}},
    )
    result = revise(store, base["id"], revision)
    successor = store.load(result["id"])
    assert successor["report"]["balance"]["releasable"] is True
    approved = review(
        store,
        successor["id"],
        dict(revision=0, status="APPROVED", note="修订后复核通过"),
    )
    assert approved["status"] == "APPROVED"
    assert store.load(base["id"])["status"] == "APPROVED"


def test_partial_revision_merges_with_unchanged_rows(store, clean):
    base = signed(store, clean)
    revision = csv_data(
        [["000107", "0001", "reading", "25", "2", "90", "0", "0", "月末提取"]]
    )
    result = revise(store, base["id"], revision)
    assert result["outcome"] == "SUCCESSOR"
    successor = store.load(result["id"])
    assert len(successor["rows"]) == len(inspect(clean)["rows"])
    assert successor["report"]["balance"]["accepted"] == len(successor["rows"])


def test_impact_keeps_revision_isolated_lines_visible(store, clean):
    base = signed(store, clean)
    revision = revision_of(clean, **{"000107": {"kw": 90}}) + "\n\n,broken\n".encode()
    result = revise(store, base["id"], revision)
    assert result["outcome"] == "SUCCESSOR"
    successor = store.load(result["id"])
    assert successor["report"]["balance"]["isolated"] == 1
    assert successor["report"]["balance"]["balanced"] is True


def test_same_revision_against_two_bases_keeps_digest_per_base(store, clean):
    first = signed(store, clean)
    alternate = revision_of(clean, **{"000107": {"note": "另版底稿"}})
    second = signed(store, alternate)
    revision = revision_of(clean, **{"000107": {"kw": 90}})
    a = revise(store, first["id"], revision)
    b = revise(store, second["id"], revision)
    assert a["base_id"] == first["id"] and b["base_id"] == second["id"]
    assert a["id"] != b["id"]


def test_pending_base_rejects_revision(store, clean):
    base = execute(store, clean)
    with pytest.raises(DomainIssue, match="REVISION_BASE_PENDING"):
        revise(store, base["id"], clean)


def test_revision_endpoint_and_history(client, clean):
    base = client.post("/api/runs", data={"sample": "clean"}).json
    client.patch(
        "/api/runs/" + base["id"],
        json=dict(revision=0, status="APPROVED", note="月末签发"),
    )
    revision = revision_of(clean, **{"000107": {"kw": 90}})
    response = client.post(
        "/api/runs/" + base["id"] + "/revisions",
        data={"file": (io.BytesIO(revision), "revision.csv")},
    )
    assert response.status_code == 200
    body = response.json
    assert body["outcome"] == "SUCCESSOR"
    listed = client.get("/api/runs/" + base["id"] + "/revisions").json["items"]
    assert len(listed) == 1 and listed[0]["successor_id"] == body["id"]
    assert len(client.get("/api/runs").json["items"]) == 2


def test_successor_evidence_records_lineage(client, clean):
    base = client.post("/api/runs", data={"sample": "clean"}).json
    client.patch(
        "/api/runs/" + base["id"],
        json=dict(revision=0, status="APPROVED", note="月末签发"),
    )
    revision = revision_of(clean, **{"000107": {"kw": 90}})
    body = client.post(
        "/api/runs/" + base["id"] + "/revisions",
        data={"file": (io.BytesIO(revision), "revision.csv")},
    ).json
    evidence = client.get("/api/runs/" + body["id"] + "/evidence").json
    assert evidence["lineage"] == {"kind": "REVISION", "base_id": base["id"]}
