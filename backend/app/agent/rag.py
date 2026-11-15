import re
from dataclasses import dataclass
from functools import lru_cache

from rank_bm25 import BM25Okapi

from app.agent.llm import LLMUnavailable, get_llm
from app.config import DATA_DIR

POLICY_PATH = DATA_DIR / "booking_policies.md"
REFUSAL = "Not covered in the approved policies."
RULE_LINE = re.compile(r"^(BP-\d+\.\d+)\s+(.*)$")
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "be", "to", "of", "for", "in", "on", "at", "and", "or", "what", "which", "who", "how", "when", "where", "can", "do",
    "does", "i", "we", "you", "my", "our", "it", "that", "this", "with", "by", "from", "there", "any", "much", "many", "should", "will", "if", "about", "me", "tell",
    "please", "need", "want", "get", "have", "has", "than", "then", "as", "so", "not", "no", "may", "must", "rule", "rules", "policy", "policies",
}
MIN_BM25 = 1.5
MIN_OVERLAP = 0.5
MAX_CHUNKS = 2
NUMBER = re.compile(r"\d+(?:[.:]\d+)?")


@dataclass(frozen=True)
class Chunk:
    rule_id: str
    text: str
    section: str


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


@lru_cache
def load_chunks() -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    section = ""
    for line in POLICY_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        match = RULE_LINE.match(line.strip())
        if match:
            chunks.append(Chunk(match.group(1), match.group(2), section))
    return tuple(chunks)


@lru_cache
def load_index() -> BM25Okapi:
    return BM25Okapi([tokens(f"{c.section} {c.text}") for c in load_chunks()])


def retrieve(question: str, limit: int = MAX_CHUNKS) -> list[tuple[Chunk, float]]:
    query = tokens(question)
    if not query:
        return []
    chunks = load_chunks()
    scores = load_index().get_scores(query)
    ranked = sorted(zip(chunks, scores), key=lambda pair: -pair[1])
    found: list[tuple[Chunk, float]] = []
    for chunk, score in ranked[:limit]:
        overlap = len(set(query) & set(tokens(f"{chunk.section} {chunk.text}"))) / len(set(query))
        if score >= MIN_BM25 and overlap >= MIN_OVERLAP:
            found.append((chunk, float(score)))
    if found and found[0][1] * 0.5 > found[-1][1]:
        found = found[:1]
    return found


def extractive_answer(found: list[tuple[Chunk, float]]) -> dict:
    return {
        "answer": " ".join(f"[{c.rule_id}] {c.text}" for c, _ in found), "citations": [c.rule_id for c, _ in found], "refused": False, "grounded": True, "mode": "extractive",
    }


def numbers_in(text: str) -> set[str]:
    return set(NUMBER.findall(text))


def grounded(answer: str, found: list[tuple[Chunk, float]]) -> bool:
    allowed_ids = {c.rule_id for c, _ in found}
    cited = set(re.findall(r"BP-\d+\.\d+", answer))
    if not cited or not cited <= allowed_ids:
        return False
    source_numbers: set[str] = set()
    for chunk, _ in found:
        if chunk.rule_id in cited:
            source_numbers |= numbers_in(chunk.text) | numbers_in(chunk.rule_id)
    return numbers_in(answer) - numbers_in(" ".join(cited)) <= source_numbers


def ask_policy(question: str, use_llm: bool = True) -> dict:
    found = retrieve(question)
    if not found:
        return {"answer": REFUSAL, "citations": [], "refused": True, "grounded": True, "mode": "refusal"}
    fallback = extractive_answer(found)
    llm = get_llm()
    if not use_llm or not llm.usable():
        return fallback
    context = "\n".join(f"[{c.rule_id}] {c.text}" for c, _ in found)
    prompt = (
        "Answer the question using ONLY the rules below. Cite every rule you use as [BP-x.y]. Do not add facts, numbers or advice that are not in the rules. "
        f"If the rules do not answer the question, reply exactly: {REFUSAL}\n\nRules:\n{context}\n\nQuestion: {question}"
    )
    try:
        text = llm.generate(prompt, cache=True).text.strip()
    except LLMUnavailable:
        return fallback
    if text == REFUSAL:
        return {"answer": REFUSAL, "citations": [], "refused": True, "grounded": True, "mode": "refusal"}
    if grounded(text, found):
        return {"answer": text, "citations": sorted(set(re.findall(r"BP-\d+\.\d+", text))), "refused": False, "grounded": True, "mode": "llm"}
    return fallback
