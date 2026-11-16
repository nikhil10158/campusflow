import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, NextPageTemplate, CondPageBreak)
from reportlab.platypus.tableofcontents import TableOfContents

VIOLET = colors.HexColor("#5a35c8")
PLUM = colors.HexColor("#1f1633")
INK = colors.HexColor("#221a33")
MUTED = colors.HexColor("#5d5173")
TINT = colors.HexColor("#e8defb")
PAPER = colors.HexColor("#f7f4fc")
LINE = colors.HexColor("#d9cfec")
TEAL = colors.HexColor("#0e8b7c")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14.5, textColor=INK, spaceAfter=5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.8, leading=12, spaceAfter=0)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.8, leading=12, spaceAfter=0)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
HEAD_CELL = ParagraphStyle("headcell", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=PLUM, spaceBefore=14, spaceAfter=8, keepWithNext=1)
TITLE = ParagraphStyle("toctitle", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=PLUM, spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=VIOLET, spaceBefore=12, spaceAfter=4, keepWithNext=1)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=7, spaceAfter=2, keepWithNext=1)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=2.5)
LEAD = ParagraphStyle("lead", parent=BODY, fontSize=11.5, leading=17, textColor=MUTED)
CALLOUT = ParagraphStyle("callout", parent=BODY, fontSize=9.6, leading=14, textColor=PLUM, spaceAfter=0)


class Rule(Flowable):
    def __init__(self, width=CONTENT_W, color=LINE):
        super().__init__()
        self.width = width
        self.color = color

    def wrap(self, avail_w, avail_h):
        return self.width, 4

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(0.8)
        self.canv.line(0, 2, self.width, 2)


class Architecture(Flowable):
    def __init__(self):
        super().__init__()
        self.width = CONTENT_W
        self.height = 245

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def box(self, x, y, w, h, title, lines, fill, text_color=INK):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(LINE)
        c.roundRect(x, y, w, h, 5, fill=1, stroke=1)
        c.setFillColor(text_color)
        c.setFont("Helvetica-Bold", 8.6)
        c.drawString(x + 7, y + h - 13, title)
        c.setFont("Helvetica", 7.6)
        for index, line in enumerate(lines):
            c.drawString(x + 7, y + h - 25 - index * 9.5, line)

    def arrow(self, x1, y1, x2, y2):
        c = self.canv
        c.setStrokeColor(VIOLET)
        c.setFillColor(VIOLET)
        c.setLineWidth(1.3)
        c.line(x1, y1, x2, y2)
        if x1 == x2:
            direction = 1 if y2 > y1 else -1
            path = c.beginPath()
            path.moveTo(x2, y2)
            path.lineTo(x2 - 3.5, y2 - 6 * direction)
            path.lineTo(x2 + 3.5, y2 - 6 * direction)
            path.close()
        else:
            direction = 1 if x2 > x1 else -1
            path = c.beginPath()
            path.moveTo(x2, y2)
            path.lineTo(x2 - 6 * direction, y2 - 3.5)
            path.lineTo(x2 - 6 * direction, y2 + 3.5)
            path.close()
        c.drawPath(path, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        w = self.width
        self.box(0, 150, w * 0.30, 90, "Browser (Next.js 16)", ["React 19, TypeScript, Tailwind 4", "TanStack Query, zustand", "Role-based pages, live agent", "stream (SSE), light/dark theme"], TINT)
        self.box(w * 0.40, 150, w * 0.60, 90, "FastAPI backend (Python 3.13)", ["Login + roles, rate limits, request checks", "Services: bookings, bundles, approvals, passes,", "audit, notifications, exports, demo clock", "Same code answers the screens and the AI assistant"], PLUM, colors.white)
        self.arrow(w * 0.30, 195, w * 0.40, 195)
        self.arrow(w * 0.40, 183, w * 0.30, 183)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(w * 0.35, 200, "REST + SSE")
        cols = 4
        gap = 8
        bw = (w - gap * (cols - 1)) / cols
        names = [
            ("Availability engine", ["numpy grid: venue x day x", "layer x 96 slots. Plus an", "independent oracle (tests)."]),
            ("Rules + validator", ["rules.yaml policy checks, then", "a separate validator that", "re-checks every proposal."]),
            ("Optimiser + search", ["OR-Tools CP-SAT: guest rooms,", "batches, re-homing. Alternatives,", "cohort slots, ghost classes."]),
            ("AI agent", ["Gemini plans and calls tools; an", "offline parser works without a", "key. BM25 policy answers."]),
        ]
        for index, (title, lines) in enumerate(names):
            x = index * (bw + gap)
            self.box(x, 62, bw, 70, title, lines, PAPER)
            self.arrow(x + bw / 2, 150, x + bw / 2, 132)
        self.box(0, 0, w * 0.48, 44, "Database", ["SQLite (local, WAL) or PostgreSQL (deployed)", "Bookings, approvals, passes, timetables"], TINT)
        self.box(w * 0.52, 0, w * 0.48, 44, "Hash-chained audit log", ["Every action linked to the one before it;", "database triggers block edits and deletes"], TINT)
        self.arrow(w * 0.24, 62, w * 0.24, 44)
        self.arrow(w * 0.76, 62, w * 0.76, 44)


class Flow(Flowable):
    def __init__(self, steps):
        super().__init__()
        self.steps = steps
        self.width = CONTENT_W
        self.height = 52

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        count = len(self.steps)
        gap = 6
        bw = (self.width - gap * (count - 1)) / count
        for index, (label, fill, ink) in enumerate(self.steps):
            x = index * (bw + gap)
            c.setFillColor(fill)
            c.setStrokeColor(LINE)
            c.roundRect(x, 6, bw, 40, 5, fill=1, stroke=1)
            c.setFillColor(ink)
            c.setFont("Helvetica-Bold", 7.6)
            lines = label.split("\n")
            top = 26 + (len(lines) - 1) * 5
            for row, line in enumerate(lines):
                c.drawCentredString(x + bw / 2, top - row * 10, line)
            if index < count - 1:
                c.setFillColor(VIOLET)
                path = c.beginPath()
                path.moveTo(x + bw + gap - 1, 26)
                path.lineTo(x + bw + 1, 29.5)
                path.lineTo(x + bw + 1, 22.5)
                path.close()
                c.drawPath(path, fill=1, stroke=0)


class GuideDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=22 * mm, bottomMargin=18 * mm,
                         title="CampusFlow: How It Works and What Every Button Does", author="CampusFlow")
        body = Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - 40 * mm, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="cover", frames=[body], onPage=draw_cover), PageTemplate(id="inner", frames=[body], onPage=draw_inner)])

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            if style in ("h1", "h2"):
                text = flowable.getPlainText()
                key = f"h-{self.seq.nextf('heading')}"
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (0 if style == "h1" else 1, text, self.page, key))


def draw_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PLUM)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.07))
    canvas.setLineWidth(0.6)
    step = 14 * mm
    x = -PAGE_H
    while x < PAGE_W + PAGE_H:
        canvas.line(x, 0, x + PAGE_H, PAGE_H)
        x += step
    canvas.setFillColor(VIOLET)
    canvas.rect(0, 0, 14 * mm, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(14 * mm, PAGE_H - 70 * mm, 6 * mm, 40 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#cbb8ff"))
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(36 * mm, PAGE_H - 52 * mm, "PRODUCT AND SYSTEM GUIDE")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 44)
    canvas.drawString(36 * mm, PAGE_H - 78 * mm, "CampusFlow")
    canvas.setFont("Helvetica", 17)
    canvas.drawString(36 * mm, PAGE_H - 92 * mm, "How it works, how the pieces fit,")
    canvas.drawString(36 * mm, PAGE_H - 101 * mm, "and what every screen and button does")
    canvas.setFillColor(colors.HexColor("#b5a8d0"))
    canvas.setFont("Helvetica", 10.5)
    canvas.drawString(36 * mm, 46 * mm, "An agentic space planner for rooms, labs, guest rooms and parking")
    canvas.drawString(36 * mm, 39 * mm, "All data in the demo is synthetic. The assistant suggests; people approve.")
    canvas.restoreState()


def draw_inner(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PLUM)
    canvas.rect(0, PAGE_H - 11 * mm, PAGE_W, 11 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#cbb8ff"))
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, PAGE_H - 7.2 * mm, "CampusFlow")
    canvas.setFillColor(colors.HexColor("#b5a8d0"))
    canvas.setFont("Helvetica", 8.5)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 7.2 * mm, "How it works and what every button does")
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(MARGIN, 8.5 * mm, "Synthetic demo data")
    canvas.drawRightString(PAGE_W - MARGIN, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [Paragraph(item, BULLET, bulletText="•") for item in items]


def table(rows, widths, header=True, zebra=True, first_bold=False):
    data = []
    for r_index, row in enumerate(rows):
        cells = []
        for c_index, cell in enumerate(row):
            if r_index == 0 and header:
                cells.append(Paragraph(cell, HEAD_CELL))
            elif c_index == 0 and first_bold:
                cells.append(Paragraph(cell, CELL_B))
            else:
                cells.append(Paragraph(cell, CELL))
        data.append(cells)
    t = Table(data, colWidths=[w * CONTENT_W for w in widths], repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), VIOLET))
    if zebra:
        for row in range(1 if header else 0, len(rows)):
            if (row % 2) == 0:
                style.append(("BACKGROUND", (0, row), (-1, row), PAPER))
    t.setStyle(TableStyle(style))
    return t


def callout(text, fill=TINT):
    box = Table([[Paragraph(text, CALLOUT)]], colWidths=[CONTENT_W])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (0, 0), (0, -1), 3, VIOLET),
    ]))
    return box


def screen(title, purpose, rows):
    return [
        KeepTogether([p(title, H2), p(purpose), table([["Control", "What it does"]] + rows, [0.27, 0.73], first_bold=True)]),
        Spacer(1, 4),
    ]


def build(path):
    story = []
    story.append(NextPageTemplate("inner"))
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("toc0", fontName="Helvetica-Bold", fontSize=11, leading=17, textColor=PLUM, spaceBefore=5),
        ParagraphStyle("toc1", fontName="Helvetica", fontSize=9.5, leading=13.5, leftIndent=14, textColor=MUTED),
    ]
    story.append(p("Contents", TITLE))
    story.append(Rule())
    story.append(toc)
    story.append(PageBreak())

    story.append(CondPageBreak(75 * mm))
    story.append(p("1. What CampusFlow is", H1))
    story.append(Rule())
    story.append(p("On a campus, rooms get double-booked, nobody is sure which room is really free, and approvals chase people by email. "
                   "CampusFlow keeps one source of truth for every classroom, lab, seminar hall, amphitheatre, guest room and parking lot, "
                   "together with a written set of booking rules. When someone asks for something, the system works out what is free, "
                   "checks the rules twice, finds who must approve it, holds it, and tracks it until it is confirmed or released.", LEAD))
    story.append(callout("<b>The one rule that never changes:</b> the AI assistant only <i>prepares</i> requests. It cannot book, approve or change anything. "
                         "A person always presses Submit, and the right approvers always decide."))
    story.append(p("Design principles", H2))
    story += bullets([
        "<b>One truth, two readers.</b> The screens and the AI assistant call the same backend code, so they can never disagree.",
        "<b>Checked twice.</b> Rules are applied by a policy engine and then re-checked by an independently written validator. If they disagree, the proposal is marked as needing changes.",
        "<b>Explain everything.</b> Every answer says why: why a room fits, why another does not, which rule applied, and what the cheapest fix is.",
        "<b>Nothing silent.</b> Every login, search, tool call, approval, import, release and export is written to a tamper-evident audit log.",
        "<b>Safe to demo.</b> A controllable demo clock lets you jump ahead to show holds expiring and approvals escalating. All data is synthetic.",
    ])

    story.append(CondPageBreak(75 * mm))
    story.append(p("2. Architecture", H1))
    story.append(Rule())
    story.append(p("The browser talks to one FastAPI backend over ordinary requests, plus a live stream for the assistant. "
                   "The backend holds all the logic; the database stores the facts; the audit log records every change."))
    story.append(Architecture())
    story.append(Spacer(1, 6))
    story.append(p("What each backend part does", H2))
    story.append(table([
        ["Part", "Role"],
        ["Availability engine", "A numpy array covering every venue, every day, five layers (class timetable, confirmed bookings, holds, maintenance, released class slots) and 96 fifteen-minute slots. It answers 'is this free?' and 'why is it busy?' in microseconds."],
        ["Oracle", "A deliberately simple, slow second implementation of the same question. Tests compare it to the fast engine on thousands of random cases, so a bug in either shows up."],
        ["Policy engine", "Reads <b>rules.yaml</b>: lead time, maximum advance, longest booking, setup and teardown buffers, minimum fill ratio, approval chain per resource type. Returns hard violations and soft suggestions, each with a rule id."],
        ["Validator", "A separate re-implementation of the rules that re-checks every proposal. Mutation tests prove it catches deliberately broken inputs."],
        ["Alternatives", "When a request fails, generates ranked fixes (shift time, shift day, other room or building, substitute type, drop a feature, shorten, split) and scores each by a cost table."],
        ["Bundles", "Treats venue + guest rooms + parking as one request. It also suggests related items, e.g. parking when more than 50 attend."],
        ["Optimiser (OR-Tools CP-SAT)", "Solves allocation puzzles: fitting guests into guest rooms, scheduling a batch of competing requests (compared with first-come-first-served), and re-homing classes when a building closes."],
        ["Workflow services", "Create bookings, build approval chains, send mock notifications, hold slots, escalate overdue approvals, expire holds, release no-shows, issue and verify passes."],
        ["AI agent", "Gemini turns a sentence into a plan and tool calls, streamed live. Without a key, a deterministic parser handles the common phrasings. Both end in the same Proposal cards."],
        ["Policy Q&A (RAG)", "Searches the approved policy text (BM25) and answers with rule citations. If nothing matches, the answer is exactly: <i>Not covered in the approved policies.</i>"],
        ["Ingestion", "Reads timetables from CSV, Excel or PDF, asks clarifying questions, previews differences, and imports as a new version you can roll back."],
        ["Audit log", "Each entry stores a hash of the previous entry. Database triggers block edits and deletes. 'Verify chain' recomputes every hash."],
    ], [0.22, 0.78], first_bold=True))

    story.append(CondPageBreak(75 * mm))
    story.append(p("3. Tech stack", H1))
    story.append(Rule())
    story.append(table([
        ["Layer", "Technology", "Why"],
        ["Frontend", "Next.js 16 (App Router), React 19, TypeScript strict", "Fast pages, typed code, one codebase for all roles."],
        ["Styling", "Tailwind 4 with CSS-variable themes, Bricolage Grotesque + DM Sans", "Light and dark themes switch by changing variables."],
        ["Data fetching", "TanStack Query, zustand, fetch-based SSE client", "Caching and refresh for lists; small stores for login and toasts; live assistant stream."],
        ["UI helpers", "cmdk (Ctrl K search), Recharts, lucide-react icons, qrcode.react", "Command palette, charts, icons, parking-pass QR codes."],
        ["Backend", "Python 3.13, FastAPI, SQLModel", "Typed API; OpenAPI schema generates the frontend types."],
        ["Database", "SQLite in WAL mode locally; PostgreSQL when deployed", "Zero setup locally; real database on Render. Writes use BEGIN IMMEDIATE to avoid races."],
        ["Maths", "numpy, OR-Tools CP-SAT, rapidfuzz", "Fast grid, optimal allocation, fuzzy name matching."],
        ["AI", "google-genai (Gemini), rank_bm25, offline parser", "Plans and answers; works without a key; cited policy answers."],
        ["Documents", "reportlab (PDF), openpyxl (Excel), ICS feeds", "Reports, booking and pass PDFs, calendar subscriptions."],
        ["Testing", "pytest (123 tests), hypothesis, mutation tests, tsc, next build", "Oracle comparison, validator mutation, workflow, race, audit, ingest, agent and export tests."],
        ["Deploy", "Docker, docker-compose, Render blueprint, Vercel", "Config files included; not yet run on live services."],
    ], [0.16, 0.42, 0.42], first_bold=True))

    story.append(CondPageBreak(75 * mm))
    story.append(p("4. Who uses it", H1))
    story.append(Rule())
    story.append(p("Every demo account uses the password <b>Demo@1234</b> and an address of the form <b>name@jklu.demo</b>. "
                   "On the login page you can simply click a role card. Permissions are enforced by the backend, not only by hiding menus."))
    story.append(table([
        ["Role card", "Account", "Can do"],
        ["Administrator", "admin", "Everything: dashboard, imports, closures, reports, performance, audit, approvals, demo clock and reset."],
        ["Faculty", "faculty01", "Find and request rooms, labs and amphitheatres, guest rooms and parking; propose releasing a class slot; see own requests."],
        ["Student club lead", "student01", "Request rooms through a faculty sponsor (rule BP-1.2); see only own bookings."],
        ["Head of department", "hod.cse", "Approver for lab requests (second step) and class-slot release proposals."],
        ["Lab in-charge", "labincharge.cse", "First approver for lab bookings."],
        ["Dean", "dean", "Approves amphitheatre events with more than 100 attendees."],
        ["Estate office", "estate", "Approves amphitheatre bookings."],
        ["Guest house manager", "guesthouse.mgr", "Approves stays, manages the waitlist."],
        ["Parking officer", "parking.officer", "Approves parking and releases no-shows."],
        ["Security", "security01", "Sees only the Gate scan page and checks parking passes."],
    ], [0.22, 0.2, 0.58], first_bold=True))
    story.append(Spacer(1, 4))
    story.append(p("Non-admin users see limited detail about other people's bookings; busy slots appear simply as 'Busy'."))

    story.append(CondPageBreak(75 * mm))
    story.append(p("5. The main workflow, step by step", H1))
    story.append(Rule())
    story.append(Flow([
        ("1. Ask", TINT, INK), ("2. Plan", TINT, INK), ("3. Check\nfree", TINT, INK), ("4. Check\nrules", TINT, INK),
        ("5. Review", PAPER, INK), ("6. Hold", PAPER, INK), ("7. Approve", VIOLET, colors.white), ("8. Confirm", TEAL, colors.white),
    ]))
    story.append(Spacer(1, 8))
    story.append(table([
        ["Step", "What happens"],
        ["1. Ask", "A user types a request in the Assistant ('Host a 2-day workshop for 80 people, 2 speakers staying 2 nights, 12 cars'), or uses Find a free room, the timeline, or a venue page."],
        ["2. Plan", "The assistant declares a short plan and splits the request into parts: venue, guest rooms, parking. The plan appears as a checklist you can watch."],
        ["3. Check availability", "The engine reads the grid. Anything touched by a class, a confirmed booking, a hold or maintenance is blocked. A class that was cancelled shows as 'Free (class cancelled)'."],
        ["4. Check rules", "The policy engine applies lead time, longest booking, buffers, fill ratio and guest-stay limits for each part."],
        ["5. Check again, without AI", "The independent validator re-checks. If the policy engine and validator both pass, the proposal is 'valid'; otherwise it says 'needs changes' and lists the problems."],
        ["6. Alternatives", "If something fails, ranked alternatives are offered with their cost and the rule they come from. 'Use this' swaps one in; it is re-validated when you submit."],
        ["7. Review and submit", "A Proposal card shows every part with its dates, any violations, the two verification badges and the approval chain. Pressing Submit request places all parts on hold together."],
        ["8. Approvals", "Each part goes through its approver chain in order. Every approver's decision first re-checks availability and policy, so stale requests are caught."],
        ["9. Time passes", "A hold lasts 24 hours. After 12 hours without an answer it escalates to the administrator. If the hold runs out, it expires and the slots are freed."],
        ["10. Result", "All parts approved: Confirmed (and passes issued). A rejection with a reason: the bundle becomes Partly done or Cancelled, and the owner chooses what to do."],
        ["11. Day of the event", "Parking passes carry a QR code. Security checks them at the gate. If nobody arrives within 30 minutes of the start, the parking officer can release the slots."],
        ["12. Record", "Every step above is written to the audit log."],
    ], [0.2, 0.8], first_bold=True))

    story.append(p("Booking life cycle", H2))
    story.append(table([
        ["Status shown", "Meaning"],
        ["Free / Free (class cancelled)", "Nothing is scheduled; a released class slot is bookable."],
        ["Busy", "Something is scheduled there (class, booking, hold or maintenance)."],
        ["On hold / Waiting", "Reserved while approvals are pending. Expires after 24 hours."],
        ["Escalated", "Waited 12 hours without a decision, so it was passed to the administrator."],
        ["Confirmed", "All approvers said yes. Booked, and passes can be issued."],
        ["Partly done", "A bundle where some parts were approved and some failed. The owner may accept, replace a part, or cancel all."],
        ["Waitlisted", "No guest room was free; queued by priority (VIP, official, faculty guest, other)."],
        ["Rejected / Expired / Cancelled / No-show", "Ended. Everything it held is released. Rejections always carry a written reason."],
    ], [0.3, 0.7], first_bold=True))

    story.append(p("Bundles and the saga board", H2))
    story.append(p("A bundle groups several components that succeed or fail together in a controlled way. Its board shows each component's stage "
                   "(held, approvals, confirmed), the approvals timeline, and the owner's options when something fails: "
                   "<b>Accept partial</b> keeps only the approved parts; <b>Replace component</b> swaps a failed part for another; "
                   "<b>Cancel all</b> releases every hold."))

    story.append(CondPageBreak(75 * mm))
    story.append(p("6. The booking rules at a glance", H1))
    story.append(Rule())
    story.append(p("These come from <b>backend/app/config/rules.yaml</b> and the approved policy file. Times are India Standard Time. Bookable hours are 07:00 to 22:00; "
                   "the 13:00 to 14:00 lunch period is respected; class periods run on the hour."))
    story.append(table([
        ["Resource", "Notice needed", "Book ahead up to", "Longest", "Setup / teardown", "Approval chain"],
        ["Classroom", "24 h", "60 days", "3 h", "none", "Admin office"],
        ["Seminar hall", "24 h", "60 days", "4 h", "15 min each", "Admin office"],
        ["Lab", "48 h", "30 days", "3 h", "none", "Lab in-charge, then Head of department"],
        ["Amphitheatre", "72 h", "90 days", "8 h", "30 min each", "Estate office, plus Dean if over 100 people"],
        ["Guest room", "24 h", "120 days", "Up to 5 nights", "60 min turnover", "Guest house manager"],
        ["Parking", "12 h", "30 days", "n/a", "n/a", "Parking officer"],
    ], [0.17, 0.14, 0.15, 0.14, 0.16, 0.24], first_bold=True))
    story.append(Spacer(1, 6))
    story += bullets([
        "<b>Fill ratio:</b> a room must be at least 40% full (50% for labs and amphitheatres), so small groups are not given large rooms.",
        "<b>Hold time:</b> 24 hours. <b>Escalation:</b> after 12 hours. <b>No-show grace:</b> 30 minutes.",
        "<b>Walk-in reserve:</b> 10% of every parking lot is always left free.",
        "<b>Ghost classes:</b> a class is a 'ghost' when mean attendance is below 25% in at least 3 of its last 4 sessions.",
        "<b>Priority classes</b> for the waitlist: VIP, official, faculty guest, other.",
    ])

    story.append(CondPageBreak(75 * mm))
    story.append(p("7. How the engines work", H1))
    story.append(Rule())
    story.append(p("Availability, in detail", H2))
    story.append(p("The grid has one cell per venue, day, layer and 15-minute slot. A window is free only when every layer is empty for every slot in it. "
                   "The 'released' layer lets a cancelled or ghost class give its room back without deleting the timetable. "
                   "When a search asks why a room is not offered, the explain function names the exact layer and the blocking item."))
    story.append(p("Concurrency and the booking race", H2))
    story.append(p("If twenty people press Submit for the same room at the same moment, exactly one wins. Write requests open the database with an immediate lock, "
                   "re-check availability inside that lock, and only then create the hold. The Performance page has a <b>Run 20-way race</b> button that proves this live."))
    story.append(p("Alternatives and costs", H2))
    story.append(table([
        ["Change", "Cost"],
        ["Shift time", "2 per 15 minutes (max 180 minutes)"], ["Shift day", "10 per day (max 3 days)"], ["Other venue", "5"],
        ["Other building", "8"], ["Substitute room type", "12"], ["Drop a nice-to-have feature", "6"], ["Shorten the booking", "4 per 15 minutes"], ["Split across venues", "15"],
    ], [0.5, 0.5]))
    story.append(Spacer(1, 6))
    story.append(p("The cheapest valid change is listed first. Each alternative is itself validated before it is shown."))
    story.append(p("Guest house allocation", H2))
    story.append(p("The 16-room guest house is searched night by night with a 60-minute turnover. Group allocation uses CP-SAT to put everyone in as few rooms as possible, "
                   "honouring 'must share' and 'must not share' lists and accessibility needs. If nothing is free, the request joins the waitlist; "
                   "when a room opens, the manager can <b>Promote</b> it (still needing approval)."))
    story.append(p("Parking and passes", H2))
    story.append(p("Each lot has capacity per vehicle type (car, bus, EV) for every slot, with 10% kept for walk-ins. The planner picks the nearest lots with space to the chosen venue. "
                   "After confirmation, one signed pass is issued per plate. The token includes an HMAC signature, the lot and the time window, so it cannot be forged or reused in another lot. "
                   "The public pass page and the Gate scan tool report VALID, EXPIRED, NOT FOUND, WRONG LOT, REVOKED or NOT YET VALID."))
    story.append(p("Common free time (cohort slots)", H2))
    story.append(p("For a quiz or extra lecture, the system takes each chosen section's weekly timetable, combines them with an AND, and finds windows when every section is free. "
                   "Windows are ranked with a score and paired with rooms that fit the size of the cohort."))
    story.append(p("Ghost classes and reports", H2))
    story.append(p("Attendance history identifies classes nobody attends. Releasing them frees hours each week (the page shows the projected number). "
                   "Reports compute utilisation by hour and building in code; the written narrative may only use those numbers and every figure in it is checked."))
    story.append(p("Closures and re-homing", H2))
    story.append(p("When a building closes for some days, the impact assessment lists every affected class and booking and uses the optimiser to give each a conflict-free new place where one exists. "
                   "Nothing changes until an administrator approves the plan; then everyone affected is notified (mock messages)."))
    story.append(p("The AI assistant", H2))
    story.append(p("The orchestrator gives Gemini a list of tools allowed for the user's role (search free rooms, check policy, check guest house, check parking, find common slots, "
                   "recommend alternatives, plan a bundle, explain busy, search policies, and so on). Each tool call is logged with its arguments, result summary and time. "
                   "The assistant can only produce proposals; submitting is a separate user action. A rate limit, quota tracking and a circuit breaker protect the AI service; "
                   "when it is unavailable the offline parser answers instead and the header chip says <b>Offline mode</b>."))
    story.append(p("Timetable ingestion", H2))
    story.append(p("A file is uploaded, parsed (CSV or Excel directly; PDF with AI extraction flagged 'please review'), validated, and shown as a preview with questions, errors and a difference list. "
                   "Only after you answer every question and fix every error can you import it, creating a new version. Older versions can be rolled back."))
    story.append(p("The audit chain", H2))
    story.append(p("Each audit entry stores its time, actor, action, details, and a hash computed from the previous entry's hash. Changing any row breaks every hash after it. "
                   "<b>Verify chain</b> recomputes them all and reports the first broken row. A demo script edits a row to show this turning red."))

    story.append(CondPageBreak(75 * mm))
    story.append(p("8. Screen-by-screen guide", H1))
    story.append(Rule())
    story.append(p("Each section lists the controls on a page and what they do. Menu names are shown as they appear in the top bar."))

    story += screen("Login", "The first page. Choose a role to try the demo, or type an account.", [
        ["Role cards (10)", "Click one to sign in as that role with the demo password. You land on the right home page for that role."],
        ["Email / Password / Sign in", "Manual sign-in. Any account@jklu.demo with Demo@1234. Errors appear in a red box."],
        ["Sun / moon button (top right)", "Switches between the dark (Midnight, the default) and light theme. The choice is remembered."],
    ])
    story += screen("Top bar (every page)", "Navigation and status, always visible.", [
        ["Logo", "Goes to the Assistant."],
        ["Home", "Dashboard (admin), My day (faculty) or My requests (student)."],
        ["Assistant", "Plan with the AI assistant."],
        ["Rooms menu", "Opens on hover or click: Find a free room, Room timeline, Class timetables, Common free time, Laboratories, Amphitheatres. Each entry has a one-line description. Menu entries depend on your role."],
        ["Guests & parking menu", "Guest house, Parking, Gate scan."],
        ["Approvals", "Requests waiting for you. A coloured number shows how many are pending (refreshes every minute)."],
        ["Rules", "Booking rules question-and-answer page."],
        ["Admin menu", "Import timetable, Closures, Usage reports, Performance, Audit log (administrators)."],
        ["Demo time and AI status", "Shown at the top of the account menu on every screen size (and as small chips on very wide screens). The demo clock replaces the real time for all rules; the assistant shows AI on, AI limited or Offline mode."],
        ["Search (Ctrl K)", "A command palette to jump to any page you may open by typing part of its name."],
        ["Sun / moon switch", "Light or dark theme."],
        ["Account menu", "Shows your name and role, offers the theme switch and Sign out."],
        ["Menu button (small screens)", "Replaces the top menus with a tap-friendly list."],
        ["'Quick guide' strips", "Many pages have a three-step guide. Hide it once and it stays hidden for that page."],
    ])
    story += screen("Assistant (home for most users)", "Describe what you need in a sentence. The assistant plans, checks, and prepares a request for you to review.", [
        ["Request box", "Type your request. Press Enter or the arrow button to send. Press '/' anywhere on the page to jump here."],
        ["Microphone", "Speak the request (browsers that support speech). Otherwise a note asks you to type."],
        ["Example cards", "Plan a whole event, Find a free room, Find a time for a quiz, Book a lab, Ask about the rules, Handle a closure (admin). Clicking one runs it."],
        ["Start over", "Clears the conversation, steps and proposals."],
        ["Conversation card", "Your messages and the assistant's answer, streamed as it is written. If it needs more detail it asks a question with option chips you can click."],
        ["What the assistant is doing", "A checklist of its plan. Ticks appear as steps finish. Open a step to see what it checked, how long it took, and the technical call."],
        ["Checked twice, without AI", "Shows whether the rules engine and the independent validator both passed."],
        ["Proposal card", "Described in the next table. Appears under 'Your request is ready to review'."],
    ])
    story += screen("Proposal card (appears after the assistant or a page prepares a request)", "Shows exactly what would be booked and lets you submit it.", [
        ["Title and badge", "'valid' (green) or 'needs changes' (red)."],
        ["Component rows", "Venue, guest room or parking part with its time, a tick or cross, any rule violations with rule ids, any conflicts, and the approvals it will need."],
        ["Policy / Independent validator badges", "Both must pass for a clean proposal."],
        ["Suggested notes", "Helpful extras, for example adding parking for a large event."],
        ["Ranked alternatives and 'Use this'", "If something failed, choose a fix. It becomes 'Selected' and is re-validated on submit."],
        ["Submit request", "Places every part on hold and sends it for approval. Disabled until the proposal is valid or an alternative is chosen. After submitting, an Open link goes to the approvals or bundle page."],
        ["Discard", "Removes the proposal. Nothing was booked."],
    ])
    story += screen("Find a free room (Rooms)", "Search every classroom, seminar hall, lab and amphitheatre for a time you choose, with a campus map.", [
        ["Day buttons and date", "Today, Tomorrow, In 2 days, Next week, or pick any date."],
        ["Start / End time", "The window you need. Duration buttons set the end time from the start."],
        ["Attendees", "Size presets or a number. Rooms must meet the fill-ratio rule."],
        ["Room type buttons", "Classroom, Seminar hall, Lab, Amphitheatre. Select several."],
        ["More options", "Nice-to-have features, Close to building, Repeat weekly for (1, 2, 4 or 8 weeks), and Step-free access needed."],
        ["Find rooms", "Runs the search. It also runs once automatically when the page opens."],
        ["Campus map", "Shows how many matches each building has. Click a building to prefer it."],
        ["Best match card and results", "Each room shows status, capacity, features and reasons it fits. A released class slot is labelled."],
        ["Why not the others?", "Opens a side panel explaining why each rejected room is busy or unsuitable."],
        ["Name for the booking", "Required before proposing; used as the event title."],
        ["Propose this room", "Runs the rules and opens a Proposal card for you to review and submit."],
    ])
    story += screen("Room timeline (Rooms)", "A day or week view of every room from 07:00 to 22:00, with coloured layers.", [
        ["View, Date, previous and next arrows, Type, Room", "Choose day or week, the date, the room type, and (in week view) one room."],
        ["Colour key", "Class, Booked, Held, Maintenance and Released slots each have a colour."],
        ["Drag across a row", "Selects a time window and instantly tells you whether it is free or why it is busy."],
        ["Selected window card", "Shows the room, the verdict and a plain-English explanation."],
        ["Title / Attendees / Book this", "Name the event, set the size and press Book this to get a Proposal card."],
    ])
    story += screen("Class timetables (Rooms)", "Any section's weekly timetable, and how many classrooms are free in each period.", [
        ["Section picker", "Choose a department, semester and section to see its week, with lectures, tutorials and labs colour-coded."],
        ["Free-classroom heatmap", "Darker cells mean more free rooms. Click a cell to list those rooms for the next matching weekday."],
    ])
    story += screen("Common free time (Rooms; faculty and staff)", "Find a slot when several class sections are all free, for a quiz or extra lecture.", [
        ["Department, Semester, Sections", "Select who must attend."],
        ["From date and days, Duration, Kind", "The period to search and the type of event."],
        ["Find common slots", "Shows a strip of common free time and a ranked list of slots with free rooms."],
        ["Propose (quiz, lecture...)", "Checks the rules for that slot and opens a Proposal card."],
    ])
    story += screen("Laboratories and Amphitheatres (Rooms)", "Both use the same layout: rules, venue list, a week view and a request form.", [
        ["Approval chain strip", "Shows who must approve, e.g. Lab in-charge then Head of department, then 'Confirmed + pass'."],
        ["Rule list", "The relevant rules, such as lead time and safety requirements."],
        ["Venue list", "Select a venue to see its next 7 days."],
        ["Request form", "Title, date, from, to, people and room. 'Check and prepare proposal' opens a Proposal card."],
        ["Ask the Concierge instead", "Takes you to the Assistant."],
    ])
    story += screen("Guest house (Guests & parking)", "Sixteen rooms with a three-week occupancy calendar.", [
        ["Occupancy calendar", "Every room for the next three weeks."],
        ["Arrival, Nights, Guests, Category, Host or event", "Describe the stay. A host or event must be named."],
        ["Search", "Lists rooms free for all nights, with an estimated cost."],
        ["Propose (per room)", "Checks the rules and opens a Proposal card."],
        ["Group allocation: Add guest, Must share, Must not share, Allocate rooms", "Add each guest with category and accessibility. The optimiser places everyone in as few rooms as possible."],
        ["Waitlist and Promote", "Queued requests by priority; when a room is free, Promote proposes it for approval."],
    ])
    story += screen("Parking (Guests & parking)", "Plan parking for events and manage passes.", [
        ["Date, From, To, Cars, Buses, EVs, Close to venue", "Describe the vehicles and the venue they are visiting."],
        ["Plan parking", "Shows the nearest lots with free space (10% is kept for walk-ins)."],
        ["Propose", "Opens a Proposal card for that lot."],
        ["Lot capacity", "Capacity of each lot for the chosen date; pick the vehicle type from the small menu."],
        ["Passes", "Choose a confirmed parking booking and issue one pass per plate. Each pass has a QR code and a PDF."],
        ["No-show release proposals and 'Release slots'", "Bookings where nobody arrived. After confirmation, the slots are freed."],
    ])
    story += screen("Gate scan (security and admin)", "Checks parking passes at the gate.", [
        ["Pass token or link", "Paste the token, or the full pass link. The result is checked against its booking window and lot."],
        ["This gate belongs to lot", "Pick the lot so a pass for another lot shows WRONG LOT."],
        ["Check pass", "Verifies the signature, window and lot, marks it scanned, and shows the verdict in large colour."],
        ["Camera", "Scans a QR code with the camera if the browser supports it; otherwise paste the token."],
        ["Public pass page (/pass/...)", "Anyone with a pass link sees only VALID, EXPIRED or similar, plate and window. It never marks the pass scanned."],
    ])
    story += screen("Approvals", "Only steps that are yours to decide are listed.", [
        ["Request cards", "Show what is requested, by whom, which step is yours, and a fresh re-check. If something changed you see 'stale' with alternatives."],
        ["Comment box", "A short note. Required when rejecting."],
        ["Approve", "Records your decision and moves the booking to the next approver or to Confirmed. Disabled if the request is no longer valid."],
        ["Reject", "Requires a comment. The booking is ended with your reason."],
        ["Class-slot release proposals", "(Head of department or admin) Approve release frees a class room slot; Reject keeps it."],
    ])
    story += screen("Bundle board", "Follow one bundle (event) from submission to confirmation.", [
        ["Saga", "Each component and its stage: held, approvals, confirmed, with status badges."],
        ["Timeline", "A time-ordered list of what happened and when."],
        ["Accept partial", "Appears when the bundle is Partly done; keeps only approved parts."],
        ["Cancel all", "Asks 'Release every part of this bundle?'. Yes releases all holds."],
    ])
    story += screen("Booking rules (Rules)", "Ask a question about the rules and get a cited answer.", [
        ["All booking rules (shown by default)", "Every approved rule, grouped by section (General, Classrooms and seminar halls, Laboratories, Amphitheatres, Guest house, Visitor parking, Bundles, Approvals and escalation, Ranking). Each shows its rule id such as BP-1.2."],
        ["Filter box and section buttons", "Type a word such as 'lab' or '24 hours' to narrow the list, or press a section button to show only that section."],
        ["Question box and Ask", "Answers come only from the approved policy file, with rule citations such as 'Rule BP-1.2'."],
        ["'Not covered' answer", "If the policies do not cover the question, the answer is exactly: Not covered in the approved policies."],
    ])
    story += screen("My day (faculty) and My requests (student)", "Personal home pages.", [
        ["Today's classes", "Your classes for today."],
        ["Release next (faculty)", "Proposes releasing the next occurrence of a lecture you will not use; the head of department must approve."],
        ["My requests / My bookings", "Your requests and their statuses with links."],
        ["Club room request (student)", "Title, date, from, to, people, room, and a faculty sponsor (required). 'Check and prepare proposal' opens a Proposal card."],
        ["Quick tiles", "Shortcuts to the assistant, finder, timeline and cohort tools."],
    ])
    story += screen("Command Center (admin home)", "The administrator's overview.", [
        ["Quick tiles", "Ask the planner, Approvals (with waiting count), Import timetable, Ghost classes."],
        ["Number cards", "Classroom utilisation, Seat utilisation, Ghost classes, Guest house occupancy, Pending approvals (numbers count up)."],
        ["Demo clock: +12 h, +1 day, +3 days", "Moves the clock forward so you can show holds expiring and approvals escalating."],
        ["Custom time and Set", "Set the clock to an exact date and time."],
        ["Reset demo data", "Asks 'Restore the original demo data?'. Yes reloads the seed data."],
        ["Alerts", "Escalated approvals, stale requests, waitlist, ghost hours to recover, and whether the audit chain is verified or broken."],
        ["AI assistant quota", "Mode (live, degraded, offline), model name and how much of the quota is used."],
        ["Bookings", "Counts of confirmed, held, waitlisted and other bookings."],
    ])
    story += screen("Import timetable (admin)", "Bring in a new timetable safely.", [
        ["Drop zone / Choose a file", "Drop or pick a CSV, Excel grid or PDF. Nothing changes yet."],
        ["Preview", "Shows file name and type (an 'AI-extracted' badge on PDFs), then questions, errors and a list of differences."],
        ["Questions", "Answer each one (for example an unclear room name) before importing."],
        ["Approve import", "Asks 'Make this the active timetable?'. Disabled until there are no errors or open questions."],
        ["Discard", "Throws the preview away."],
        ["Sample files", "Download synthetic sample timetables to try."],
        ["Version history and Roll back", "Older versions are listed; Roll back asks 'Restore this version?' and makes it active again."],
    ])
    story += screen("Closures (admin)", "Handle a building closure and move everything affected.", [
        ["Kind, Building, First day, Last day, Description", "Describe what closed and for how long."],
        ["Assess impact", "Lists every class and booking affected and the proposed new place for each."],
        ["Impact map", "Highlights the affected buildings."],
        ["Approve and apply plan", "Asks 'Apply every re-home change?'. Yes applies the plan and sends mock notifications."],
    ])
    story += screen("Usage reports (admin)", "Utilisation and the classes nobody attends.", [
        ["PDF and Excel", "Download the monthly report."],
        ["Charts", "Utilisation by hour of the day and by building."],
        ["Narrative", "A short written summary where every number is checked against the computed figures."],
        ["Ghost classes list", "Shows each low-attendance class with a small trend line, its attendance and the weekly hours it would free."],
        ["Propose release", "Proposes releasing that class's slot (the head of department must approve). Shows 'Proposed' afterwards."],
    ])
    story += screen("Performance (admin)", "Proves the optimiser, the race handling and the search speed.", [
        ["Run optimiser and latency benchmark", "Runs a fest-week scenario: CP-SAT versus first-come-first-served, plus search latency over all venues."],
        ["Run 20-way race", "Twenty simultaneous attempts to book the same room; exactly one must succeed."],
    ])
    story += screen("Audit log (admin)", "Everything that happened, with proof it has not been altered.", [
        ["Tabs: Audit log, Outbox, Calendar feeds", "Switch between the three views."],
        ["Excel", "Downloads the audit log."],
        ["Verify chain", "Recomputes every hash and reports OK or the first broken row."],
        ["Outbox", "The mock email and WhatsApp messages. Nothing is really sent."],
        ["Calendar feeds", "Personal feed (token protected) and venue feeds (busy blocks only) for calendar apps."],
    ])

    story.append(CondPageBreak(75 * mm))
    story.append(p("9. Quick reference: status labels", H1))
    story.append(Rule())
    story.append(table([
        ["Label", "Plain meaning"],
        ["Free", "Nothing scheduled at that time."],
        ["Free (class cancelled)", "A timetabled class was released, so the room is open."],
        ["Busy", "Already scheduled."],
        ["On hold", "Reserved while approvals are pending."],
        ["Waiting", "Waiting for an approver."],
        ["Escalated", "Passed to the administrator after 12 hours."],
        ["Submitted", "Sent in; all parts on hold together."],
        ["Confirmed", "Approved and booked."],
        ["Partly done", "Some parts of a bundle failed."],
        ["Waitlisted", "No room free; queued by priority."],
        ["Expired", "The hold ran out."],
        ["Rejected", "An approver said no, with a reason."],
        ["Cancelled", "Cancelled; all holds released."],
        ["No-show", "Nobody arrived, so slots were released."],
        ["Proposed / Approved", "A release or plan waiting for, or given, approval."],
        ["In use / Older version", "The active timetable version, or one you can roll back to."],
        ["Rarely used", "A ghost-class candidate."],
        ["Valid / Wrong lot / Not found", "Parking pass check results."],
        ["Best possible / Good / No solution", "How well the optimiser solved a puzzle."],
    ], [0.3, 0.7], first_bold=True))

    story.append(CondPageBreak(75 * mm))
    story.append(p("10. Running, testing and limits", H1))
    story.append(Rule())
    story.append(p("Run it locally", H2))
    story += bullets([
        "Windows: open a terminal in the project folder and run <b>.\\run.ps1</b>. It creates the virtual environment, installs everything, seeds the database, starts the API on port 8000 and the web app on port 3000.",
        "Docker: <b>docker compose up --build</b> starts the API on 8000 and the web app on 3000.",
        "Open the web app, click a role card on the login page, and try the example cards in the Assistant.",
    ])
    story.append(p("Deploy", H2))
    story += bullets([
        "Backend on Render using the included <b>render.yaml</b> (Docker service plus a free PostgreSQL database). Set the optional GEMINI_API_KEY.",
        "Frontend on Vercel with root directory <b>frontend</b> and one variable, NEXT_PUBLIC_API_URL, set to the Render address.",
        "Add the Vercel address to FRONTEND_ORIGINS on Render, then check with <b>scripts/smoke_deployed.py</b>.",
        "Free Render services sleep after 15 idle minutes and the free database expires after 30 days.",
    ])
    story.append(p("Testing", H2))
    story += bullets([
        "123 backend tests: availability engine against the oracle, validator mutation tests, workflow and role checks, booking races, audit tamper checks, timetable ingestion, agent behaviour, policy grounding and exports.",
        "The frontend type-checks and builds all 26 routes.",
        "Demo scripts in <b>scripts/</b>: a full demo flow, the race demo, the tamper demo, a deployed-site smoke test and a Gemini key check.",
    ])
    story.append(p("What has not been verified", H2))
    story.append(callout("Docker builds, PostgreSQL, a live Gemini key and the Render and Vercel deployments were prepared but never run. Everything else was run and tested locally.", PAPER))

    GuideDoc(str(path)).multiBuild(story)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("CampusFlow_Guide.pdf")
    build(target)
    print(target)
