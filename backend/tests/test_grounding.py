import pytest

from app.agent import rag

IN_SCOPE = [
    ("What is the lead time for booking an amphitheatre?", "BP-1.4"),
    ("How many nights can a guest stay at the guest house?", "BP-5.3"),
    ("What time is guest house check-in?", "BP-5.2"),
    ("Who approves guest house bookings?", "BP-5.9"),
    ("Do students need a faculty sponsor?", "BP-1.2"),
    ("How long can a classroom booking last?", "BP-2.1"),
    ("Which events need Dean approval in the amphitheatre?", "BP-4.2"),
    ("What is the walk-in reserve for parking?", "BP-6.4"),
    ("What happens to a parking no-show?", "BP-6.6"),
    ("When does an approval step get escalated?", "BP-8.3"),
    ("What is a ghost class and how is it flagged?", "BP-2.7"),
    ("Can guest nights be booked without an event or host?", "BP-7.1"),
    ("How many vehicles can be parked compared with attendees?", "BP-7.3"),
    ("What are the booking hours for venues?", "BP-1.3"),
    ("How is the guest house waitlist ordered?", "BP-5.7"),
]

OUT_OF_SCOPE = [
    "What is the exam seating arrangement?",
    "How much is the hostel fee?",
    "What is on the mess menu today?",
    "What is the library fine for late books?",
    "When are the semester exam results published?",
    "How do I apply for a scholarship?",
    "What is the dress code on campus?",
    "Who is the vice chancellor?",
]


@pytest.mark.parametrize("question,rule", IN_SCOPE)
def test_in_scope_questions_cite_the_right_rule(question: str, rule: str) -> None:
    answer = rag.ask_policy(question, use_llm=False)
    assert not answer["refused"], question
    assert rule in answer["citations"], (question, answer["citations"])


@pytest.mark.parametrize("question", OUT_OF_SCOPE)
def test_out_of_scope_questions_are_refused_verbatim(question: str) -> None:
    answer = rag.ask_policy(question, use_llm=False)
    assert answer["refused"] and answer["answer"] == "Not covered in the approved policies."


def test_grounding_check_rejects_invented_numbers_and_rules() -> None:
    found = rag.retrieve("lead time amphitheatre")
    assert not rag.grounded("Amphitheatres need 99 hours [BP-1.4]", found)
    assert not rag.grounded("Use rule [BP-9.9]", found)
    assert not rag.grounded("No citation at all", found)
    assert rag.grounded("Amphitheatres need 72 hours of lead time [BP-1.4]", found)
