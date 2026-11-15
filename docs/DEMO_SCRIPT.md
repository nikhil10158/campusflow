# Demo script (about 7 minutes)

Before starting: `make reset-demo` (or Command Center -> Reset demo data). Demo clock is Monday 16 Nov 2026 10:00. All accounts use `Demo@1234`; the login page has one-click chips.

1. **Timetable import (admin, 1 min)** - Timetable Import. Drop `cse5a_grid.pdf`: parsed preview, no errors, diff "all unchanged". Drop `planted_errors.csv`: four anomaly types, import blocked. Drop `ambiguous_headers.csv`: pick "Place" for the room column and a room from the chips. Approve the clean file, then roll the version back.
2. **Free rooms (faculty01, 1 min)** - Free Rooms: tomorrow 14:00-16:00, 60 people. Show FREE and FREE RELEASED badges, the map and "Why not the other rooms?" with the first blocker for each room. Venue Timeline: drag a free window, read the verdict, press "Book this".
3. **Cohort quiz slot (30 s)** - Cohort Slots: CSE Sem 5 A and B, 60 minutes, next week. Heat strips, ranked slots, "Propose quiz".
4. **Concierge bundle (1 min)** - Concierge: "Host a 2-day AI workshop on 3-4 Dec for 80 people, 2 external speakers staying 2 nights, 12 cars". Watch the plan tick, tool cards, the policy and validator ticks; open the proposal; press **Submit request**.
5. **Approvals and confirmation (1 min)** - Sign in as `estate`, `guesthouse.mgr`, `parking.officer` in turn and approve inside the Approvals inbox. The bundle page shows HELD -> approvals -> CONFIRMED; open the parking page for the QR passes.
6. **Gate scan (30 s)** - Admin: set the demo clock to the parking window start. Security -> paste a token: VALID; choose another lot: WRONG LOT. Advance the clock 30 minutes past a booking with no scan: Parking -> no-show release proposal.
7. **Disruption (45 s)** - Disruption Center: Lab Complex 1, Wed-Thu. Impact list, conflict-free re-home proposals, apply.
8. **Ghost classes (30 s)** - Utilisation: six planted ghosts with sparklines, "+N bookable hours per week". Propose a release, approve it as the HoD (Approvals -> release proposals), search again: the room is now FREE RELEASED.
9. **Race and audit (45 s)** - Benchmark: run the 20-way race (1 winner, validator 0). Audit: Verify chain (green). Terminal: `python scripts/tamper_demo.py` turns it red at the edited row.
10. **Report (15 s)** - Utilisation: the number-verified narrative and PDF / Excel export.

Escalation and expiry on demand: Command Center -> "+12 h" escalates idle steps, "+1 day" expires holds.

Screenshots are in `docs/screenshots/`.
