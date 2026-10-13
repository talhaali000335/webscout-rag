"""Anti-hallucination helpers (pure functions, easy to test)."""
import re

NOT_FOUND = "I couldn't find that on this page."
_CITE = re.compile(r"\[(\d+)\]")


def clean_citations(answer: str, n_passages: int):
    """Remove citations pointing to passages that don't exist.
    Returns (clean_answer, sorted list of valid cited numbers)."""
    valid = set()

    def fix(m):
        n = int(m.group(1))
        if 1 <= n <= n_passages:
            valid.add(n)
            return m.group(0)
        return ""

    cleaned = _CITE.sub(fix, answer).strip()
    return cleaned, sorted(valid)


def is_grounded(answer: str, cited: list) -> bool:
    """An answer is 'grounded' if it cites at least one real passage,
    or if it honestly says it could not find the information."""
    return bool(cited) or answer.strip().startswith("I couldn't find")
