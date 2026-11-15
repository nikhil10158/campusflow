# SYNTHETIC POLICIES FOR DEMO — replace with institutional rules

These rules belong to the synthetic JKLU-like demo campus. Every rule has an ID. The assistant answers policy questions only from this file.

## BP-1 General

BP-1.1 Faculty, staff and approved student clubs may request bookings of classrooms, laboratories, amphitheatres, guest house rooms and visitor parking.
BP-1.2 A student request is valid only when a faculty sponsor is named on the request.
BP-1.3 Venues may be booked only between 07:00 and 22:00.
BP-1.4 Minimum lead time before the start of a booking: 24 hours for classrooms, seminar halls and guest house rooms, 48 hours for laboratories, 72 hours for amphitheatres, and 12 hours for parking.
BP-1.5 Maximum advance booking: 60 days for classrooms and seminar halls, 30 days for laboratories and parking, 90 days for amphitheatres, and 120 days for guest house rooms.
BP-1.6 A submitted request creates a tentative hold of 24 hours that blocks other requests; a hold that is not fully approved within 24 hours expires.
BP-1.7 Every rejection must carry a written reason.
BP-1.8 The campus calendar works in 15-minute slots, and the timetable periods are 09:00-09:55, 10:00-10:55, 11:00-11:55, 12:00-12:55, 14:00-14:55, 15:00-15:55 and 16:00-16:55 with lunch from 13:00 to 14:00.

## BP-2 Classrooms and seminar halls

BP-2.1 Extra lectures and quizzes may use a classroom that is free of timetable classes and other bookings; a classroom booking lasts at most 180 minutes.
BP-2.2 A seminar hall booking lasts at most 240 minutes and needs 15 minutes of setup and 15 minutes of teardown around it.
BP-2.3 Classrooms need no setup or teardown buffer, which is 0 minutes.
BP-2.4 A classroom or seminar hall should be filled to at least 0.4 of its capacity; below that the system recommends a smaller room.
BP-2.5 A faculty member may propose release of a class slot that will not be held; the slot becomes bookable only after approval.
BP-2.6 A class slot that is cancelled or released by an approved exception is shown as FREE_RELEASED and may be booked.
BP-2.7 Ghost class review: a timetabled class is flagged when mean headcount is below 0.25 of the section size in at least 3 of its last 4 occurrences; release of a flagged slot needs HoD or admin approval.
BP-2.8 A new timetable is imported only by an administrator after previewing and approving the differences.
BP-2.9 Classroom and seminar hall bookings are approved by the admin office.

## BP-3 Laboratories

BP-3.1 A laboratory may be booked only by departments listed as eligible for that laboratory.
BP-3.2 A laboratory that needs a supervisor may be booked only by a faculty member or with a faculty sponsor.
BP-3.3 Laboratory bookings need approval from the lab-in-charge first and then from the head of the requesting department.
BP-3.4 A laboratory booking lasts at most 180 minutes and should fill at least 0.5 of the laboratory capacity.
BP-3.5 Chemistry and mechanical laboratories always need a supervisor present for safety.

## BP-4 Amphitheatres

BP-4.1 Occupancy of any venue must never exceed 100 percent of its capacity for fire safety.
BP-4.2 Amphitheatre events with more than 100 attendees need Dean approval after estate approval; smaller events need estate approval only.
BP-4.3 An amphitheatre needs 30 minutes of setup and 30 minutes of teardown for audio-visual work around every event.
BP-4.4 An amphitheatre should be filled to at least 0.5 of its capacity; below that the system recommends a smaller venue.
BP-4.5 An amphitheatre booking lasts at most 480 minutes.
BP-4.6 Events that need recording must tell the estate office so audio-visual setup time is kept.

## BP-5 MDC guest house

BP-5.1 Guest house priority classes are: 1 for VIP guests, 2 for official visitors, 3 for faculty guests, and 4 for parents, vendors and others.
BP-5.2 Check-in is from 14:00 and check-out is by 11:00.
BP-5.3 A stay may last at most 5 nights.
BP-5.4 A turnover buffer of 60 minutes is kept between a check-out and the next check-in in the same room.
BP-5.5 Suites are offered first to priority classes 1 and 2.
BP-5.6 Guests share a room only when the room capacity allows it and no must-not-share condition applies.
BP-5.7 When no room is free the request is placed on the waitlist ordered by priority class and then by request time.
BP-5.8 When a booking is cancelled the first waitlisted request is proposed for promotion and the guest house manager must confirm it.
BP-5.9 Guest house bookings are approved by the guest house manager.
BP-5.10 A cancelled booking releases its rooms immediately.

## BP-6 Visitor parking

BP-6.1 Visitor parking is allowed only in lots marked as visitor lots; the VIP lot is only for VIP vehicles.
BP-6.2 Buses may use only lots that have bus bays, and the overflow lot is used when the visitor lot is full.
BP-6.3 Electric vehicles use the EV bays.
BP-6.4 A walk-in reserve of 10 percent of every lot is never reserved in advance.
BP-6.5 A parking pass is valid only for its booking window and its lot, and one pass is issued for each vehicle plate.
BP-6.6 When no pass is scanned within 30 minutes after the start of the window the parking officer may release the slots as a no-show.
BP-6.7 Parking bookings are approved by the parking officer.
BP-6.8 A request may be split across lots when one lot is too small, with a shuttle note on the pass.

## BP-7 Bundles

BP-7.1 Guest house nights must be linked to a host or to an event in the same bundle.
BP-7.2 All components of a bundle must sit inside the event window: guest nights cover the event and parking covers arrival and departure.
BP-7.3 The number of parked vehicles may not exceed the number of attendees.
BP-7.4 A bundle is confirmed atomically: every component is confirmed together or none is; if a component fails the bundle becomes PARTIAL.
BP-7.5 For a PARTIAL bundle the requester may accept the partial result, replace a component, or cancel the whole bundle.
BP-7.6 External speakers suggest guest house rooms, events with more than 50 attendees suggest parking, events ending after 18:00 suggest a security notice, and recording suggests audio-visual buffer time.

## BP-8 Approvals and escalation

BP-8.1 An approver may act only on steps within the approver's own scope.
BP-8.2 Approval steps are taken in order, and a step is available only after the earlier steps are approved.
BP-8.3 A step that stays pending for 12 hours is escalated to the administrator.
BP-8.4 Availability and policy are checked again at approval time; a stale request must be re-planned with alternatives.
BP-8.5 Every state change needs an explicit human action; the assistant only proposes.
BP-8.6 Every login, search, proposal, approval, rejection, import, release and pass is written to a tamper-evident audit log.

## BP-9 Ranking of suggestions

BP-9.1 Free rooms are ranked with weight 40 for capacity fit, 20 for matching features, 20 for walking distance, 10 for policy warnings and a penalty of 5 for slots freed by release.
BP-9.2 The ideal seat fill is between 0.7 and 0.95 of capacity.
BP-9.3 Alternatives are costed as follows: 2 per 15 minutes of time shift, 10 per day of day shift, 5 for another venue, 8 for another building, 12 for a substitute venue type, 6 for dropping an optional feature, 4 per 15 minutes of shortening and 15 for splitting across two venues.
BP-9.4 Alternatives may shift time by at most 180 minutes and the day by at most 3 days.
BP-9.5 Extra slots for several sections are ranked with a penalty of 30 for overlapping lunch, 20 for late slots, 10 per hour of gap and 1 per minute of walking.
