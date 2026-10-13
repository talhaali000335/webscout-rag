"""Split page sections into overlapping, heading-aware chunks."""


def _hard_split(line: str, size: int):
    return [line[i:i + size] for i in range(0, len(line), size)]


def chunk_sections(sections, size: int = 1000, overlap: int = 150):
    chunks = []
    for heading, text in sections:
        lines = []
        for ln in text.split("\n"):
            lines.extend(_hard_split(ln, size) if len(ln) > size else [ln])

        buf, length = [], 0
        for ln in lines:
            if length + len(ln) + 1 > size and buf:
                chunks.append((heading, "\n".join(buf)))
                # carry the tail of the previous chunk for context
                tail, tl = [], 0
                for prev in reversed(buf):
                    if tl + len(prev) > overlap:
                        break
                    tail.insert(0, prev)
                    tl += len(prev) + 1
                buf, length = tail, tl
            buf.append(ln)
            length += len(ln) + 1
        if buf:
            chunks.append((heading, "\n".join(buf)))

    out = []
    for i, (heading, body) in enumerate(chunks):
        out.append({"idx": i, "heading": heading, "text": f"[Section: {heading}]\n{body}"})
    return out
