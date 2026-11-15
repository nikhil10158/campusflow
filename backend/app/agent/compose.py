from datetime import datetime


def hm(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%a %d %b, %H:%M")


def free_rooms(result: dict) -> str:
    start, end = (hm(v) for v in result["window"])
    if result["free_count"] == 0:
        reasons = "; ".join(r["reason"] for r in result["why_not"][:3])
        return f"No room is free from {start} to {end}. Of {result['considered']} rooms checked, the first blockers were: {reasons}."
    lines = [f"{result['free_count']} of {result['considered']} rooms are free from {start} to {end}. Best matches:"]
    for hit in result["hits"][:3]:
        badge = " (freed by a cancelled or released class)" if hit["state"] == "FREE_RELEASED" else ""
        lines.append(f"- {hit['code']} seats {hit['capacity']}{badge}: {'; '.join(hit['reasons'][:2])}")
    return "\n".join(lines)


def proposal_sentence(plan: dict) -> str:
    if plan.get("ok"):
        parts = ", ".join(c["label"] or "component" for c in plan["components"])
        return f"I prepared a proposal for {plan['title']} ({parts}). It passes the policy checks and the independent validator. Nothing is booked until you submit it for approval."
    problems = []
    for component in plan["components"]:
        problems += [v["message"] + f" [{v['rule_id']}]" for v in component.get("violations", []) if v["severity"] == "hard"]
        problems += component.get("conflicts", [])[:1]
    problems += [v["message"] + f" [{v['rule_id']}]" for v in plan.get("bundle_violations", [])]
    text = f"I could not make {plan['title']} work as asked: " + "; ".join(problems[:4]) + "."
    if plan.get("alternatives"):
        text += f" I found {plan['alternatives']} ranked alternatives, listed on the proposal card."
    return text


def booking_outcome(plan: dict, extra: str = "") -> str:
    return (extra + " " + proposal_sentence(plan)).strip()


def cohort(result: dict, plan: dict | None) -> str:
    if not result["slots"]:
        return "No time is free for all of those sections in that window. Try a wider date range or a shorter duration."
    best = result["slots"][0]
    day = datetime.fromisoformat(best["start"])
    room = best["rooms"][0]["code"] if best["rooms"] else "no room"
    text = f"{len(result['slots'])} common slots found for {', '.join(result['section_labels'])} ({result['attendees']} students). Best: {day:%a %d %b %H:%M} in {room} - {'; '.join(best['reasons'][:2])}."
    return text + (" " + proposal_sentence(plan) if plan else "")


def guest_rooms(result: dict) -> str:
    if not result["rooms"]:
        return "No guest house room is free for those nights. You can join the waitlist or try other dates."
    room = result["rooms"][0]
    return f"{result['free_count']} rooms are free. Best fit: {room['code']} ({room['type']}), about Rs {room['estimate']} for the stay."


def parking(result: dict) -> str:
    if not result["ok"]:
        return f"Not enough parking: unmet {result['unmet']}."
    lots = ", ".join(f"{a['lot']} ({sum(a['vehicles'].values())} vehicles)" for a in result["allocations"])
    shuttle = " A shuttle note will be added." if any(a["shuttle"] for a in result["allocations"]) else ""
    return f"Parking can be placed in {lots}.{shuttle}"


def closure(result: dict) -> str:
    summary = result["summary"]
    return f"{summary['affected']} classes and bookings are affected; {summary['resolved']} have a conflict-free re-home proposal and {summary['unresolved']} need a manual decision. Review them in the Disruption Center."


def ghosts(result: dict) -> str:
    return f"{result['count']} ghost classes were flagged. Releasing them would free about {result['projected_uplift_hours_per_week']} bookable hours per week, after approval."


def utilisation(result: dict) -> str:
    return (
        f"Classroom time utilisation is {result['classroom_time_utilisation_pct']}% and seat utilisation {result['seat_utilisation_pct']}%. "
        f"{result['ghost_classes']} ghost classes are flagged ({result['ghost_bookable_hours_per_week']} bookable hours per week)."
    )


def lookup(result: dict) -> str:
    if result.get("error"):
        return result["message"]
    booking = result["booking"]
    return f"Booking #{booking['id']} is {booking['status']} ({booking['event_title']}, {hm(booking['start'])})."


def my_bookings(result: dict) -> str:
    if not result["bookings"]:
        return "You have no bookings yet."
    return "Your bookings: " + "; ".join(f"#{b['id']} {b['title']} ({b['status']})" for b in result["bookings"][:5])


def release(view: dict) -> str:
    return f"I prepared a release proposal for {view['course']} on {view['date']} in {view['venue']}; it would free {view['bookable_hours_freed']} bookable hour(s) after the head of department approves."
