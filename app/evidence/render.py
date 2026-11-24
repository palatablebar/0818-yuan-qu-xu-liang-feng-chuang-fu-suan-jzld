import json


def artifact(run):
    packet = {
        "schema": "review-evidence/1",
        "manifest": run["report"]["manifest"],
        "balance": run["report"]["balance"],
        "cases": run["report"]["cases"],
        "intake": run["report"]["intake"],
        "review": {key: run[key] for key in ("status", "revision", "note", "reviewed")},
    }
    if run.get("kind") == "REVISION" and run.get("base_id"):
        packet["lineage"] = {"kind": "REVISION", "base_id": run["base_id"]}
    return (
        json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
