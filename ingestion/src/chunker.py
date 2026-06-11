import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_MIN_CHUNK_CHARS = 50


def chunk_text(text: str, max_chars: int = 1500, overlap_chars: int = 150) -> list[str]:
    """Split text into overlapping chunks, preserving sentence boundaries where possible."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in _SENTENCE_BOUNDARY.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_len + len(sentence) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            overlap_sentences: list[str] = []
            overlap_len = 0
            for prior_sentence in reversed(current):
                if overlap_len + len(prior_sentence) + 1 <= overlap_chars:
                    overlap_sentences.insert(0, prior_sentence)
                    overlap_len += len(prior_sentence) + 1
                else:
                    break
            current = overlap_sentences
            current_len = overlap_len

        current.append(sentence)
        current_len += len(sentence) + 1

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if len(c.strip()) > _MIN_CHUNK_CHARS]
