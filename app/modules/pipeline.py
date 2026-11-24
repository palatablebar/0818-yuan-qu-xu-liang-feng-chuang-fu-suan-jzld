from app.business import DomainIssue
from app.intake.service import inspect
from app.modules.calculate import compute
from app.modules.grouping import case_groups
from app.modules.policy import policy
from app.modules.prepare import prepare
from app.modules.reconcile import balance


def evaluate(rows, stage):
    case = {
        "case": rows[0]["case"],
        "records": [r["record"] for r in rows],
        "status": "READY",
    }
    try:
        case["prep"], payload = prepare(rows)
        if stage >= 3:
            case["measure"] = compute(payload)
        if stage >= 4:
            case.update(policy(case["measure"]))
    except DomainIssue as error:
        case["status"] = error.code
    return case


def assemble(intake, stage=5):
    """Build the stage report from an already inspected intake.

    Revision handling needs to evaluate merged effective rows that never
    existed as one source file, so the intake/report split is explicit.
    """
    output = {"intake": {k: v for k, v in intake.items() if k != "rows"}}
    if stage == 1:
        return output
    cases = [evaluate(rows, stage) for _, rows in case_groups(intake["rows"])]
    output["cases"] = cases
    if stage >= 5:
        output["balance"] = balance(intake, cases)
    return output


def run(data, stage=5):
    return assemble(inspect(data), stage)
