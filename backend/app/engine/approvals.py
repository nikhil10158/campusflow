from app.engine.types import BookingRequest, Snapshot
from app.rules import Rules


def approval_chain(request: BookingRequest, snapshot: Snapshot, rules: Rules) -> list[str]:
    if request.resource_type == "venue":
        venue = snapshot.venue(request.resource_id)
        rule = rules.for_venue_type(venue.type)
        scopes: list[str] = []
        for step in rule.approval_chain:
            if step == "lab_incharge":
                scopes.append(f"lab_incharge:{venue.lab_type}")
            elif step == "hod":
                dept = request.requester_dept or (venue.eligible_depts[0] if venue.eligible_depts else "CSE")
                scopes.append(f"hod:{dept}")
            elif step == "dean_if_large":
                if request.attendees > rule.dean_approval_above_attendees:
                    scopes.append("dean")
            else:
                scopes.append(step)
        return scopes
    return list(rules.resources[request.resource_type].approval_chain)


def scope_matches(user_scopes: list[str], step_scope: str) -> bool:
    return step_scope in user_scopes
