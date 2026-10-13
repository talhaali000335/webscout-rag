import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.chunking import chunk_sections  # noqa: E402
from app.citations import NOT_FOUND, clean_citations, is_grounded  # noqa: E402
from app.scraper import ScrapeError, assert_public_url, extract, normalize_url  # noqa: E402

HTML = """
<html><head><title>Cool Shoe</title>
<meta name="description" content="A very cool shoe">
<script type="application/ld+json">
{"@type":"Product","name":"Cool Shoe","offers":{"@type":"Offer","price":"49.99","priceCurrency":"USD"},
 "aggregateRating":{"ratingValue":"4.6","reviewCount":"123"}}
</script></head>
<body><nav>MENU HOME</nav>
<main>
<h1>Cool Shoe</h1><p>%s</p>
<h2>Shipping</h2><p>Ships in 3 days. Free returns.</p>
<script>alert(1)</script>
</main><footer>copyright</footer></body></html>
""" % ("Great comfortable running shoe. " * 30)


def test_extract_structured_and_sections():
    page = extract(HTML, "https://x.com/p")
    text = "\n".join(t for _, t in page.sections)
    assert "price: 49.99" in text
    assert "ratingValue: 4.6" in text
    assert "MENU HOME" not in text and "alert(1)" not in text and "copyright" not in text
    assert "Shipping" in [h for h, _ in page.sections]


def test_chunking_overlap_and_prefix():
    sections = [("Intro", "\n".join(f"line number {i} " * 5 for i in range(60)))]
    chunks = chunk_sections(sections, size=400, overlap=100)
    assert len(chunks) > 3
    assert all(c["text"].startswith("[Section: Intro]") for c in chunks)
    assert [c["idx"] for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("url", [
    "http://localhost:8000", "http://127.0.0.1", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5", "ftp://example.com", "file:///etc/passwd"])
def test_ssrf_blocked(url):
    with pytest.raises(ScrapeError):
        assert_public_url(url)


def test_normalize_url():
    assert normalize_url("example.com/a") == "https://example.com/a"
    with pytest.raises(ScrapeError):
        normalize_url("notaurl")


def test_citations():
    ans, cited = clean_citations("Price is $5 [1][3]. Also [9].", 3)
    assert cited == [1, 3] and "[9]" not in ans
    assert is_grounded(ans, cited)
    assert not is_grounded("Totally made up", [])
    assert is_grounded(NOT_FOUND, [])


# ---------------------------------------------------------------- new in v2
def test_vectorstore_roundtrip(tmp_path, monkeypatch):
    import numpy as np
    from app import vectorstore
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    embs = np.eye(4, 8, dtype=np.float32)
    meta = [{"text": f"t{i}", "heading": "h", "idx": i, "url": "u", "title": "t"} for i in range(4)]
    vectorstore.save("abc", embs, meta)
    q = np.zeros(8, dtype=np.float32)
    q[2] = 1
    hits = vectorstore.search("abc", q, 2)
    assert hits[0][0]["text"] == "t2" and hits[0][1] > 0.99
    assert len(hits) == 2


def test_detect_wall_login_and_captcha():
    from app.scraper import detect_wall, extract
    login = "<html><title>Sign in</title><body><form><input type='password'></form></body></html>"
    assert detect_wall(login, "https://x.com/a", extract(login, "https://x.com/a"))
    cap = "<html><title>Robot Check</title><body><p>Enter the characters you see below</p></body></html>"
    assert detect_wall(cap, "https://x.com/a", extract(cap, "https://x.com/a"))
    redirect = "<html><title>x</title><body><p>hi</p></body></html>"
    assert detect_wall(redirect, "https://x.com/ap/signin", extract(redirect, "https://x.com/ap/signin"))
    assert detect_wall(HTML, "https://x.com/p", extract(HTML, "https://x.com/p")) is None


def test_session_files_are_per_user(tmp_path, monkeypatch):
    from app import scraper
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    a = scraper.session_file("alice", "https://www.shop.com/x")
    b = scraper.session_file("bob", "https://shop.com/y")
    assert a != b and scraper.session_file("alice", "https://shop.com/z") == a
    assert scraper.session_file("", "https://shop.com") is None
    a.write_text("{}")
    assert scraper.forget_sessions("alice") == 1 and not a.exists()
