import hashlib

from app.services.chunking import chunk_readme, clean_markdown, split_sections

MD_URL = "https://github.com/acme/x/blob/main/README.md"
RST_URL = "https://github.com/acme/x/blob/main/README.rst"


def test_chunks_follow_headings_and_hash_content():
    md = "# Alpha\n\n" + "Alpha body text that is long enough to keep. " * 2 + "\n\n"
    md += "## Beta\n\n" + "Beta body text that is long enough to keep too. " * 2
    chunks = chunk_readme(md, MD_URL)
    assert [c.section_title for c in chunks] == ["Alpha", "Beta"]
    assert [c.position for c in chunks] == [0, 1]
    assert chunks[0].content_hash == hashlib.sha256(chunks[0].content.encode()).hexdigest()
    assert all(c.source_url == MD_URL and c.source_type == "readme" for c in chunks)


def test_hash_comments_inside_code_fences_are_not_headings():
    md = (
        "## Scheduling Jobs\n\nYou can schedule jobs to run later with the scheduler.\n\n"
        "```python\n# Schedule job to run at 9:15\nqueue.enqueue_at(dt, fn)\n```\n"
    )
    titles = {s.title for s in split_sections(md, "markdown")}
    assert titles == {"Scheduling Jobs"}


def test_line_before_code_fence_is_not_a_heading():
    md = (
        "# Installation\n\nThis project can be installed using pip:\n```bash\npip install x\n```\n"
        "\nbroker = Broker()\n~~~\ncode\n~~~\n"
    )
    assert [s.title for s in split_sections(clean_markdown(md), "markdown")] == ["Installation"]


def test_indented_fence_in_list_hides_comment_headings():
    md = (
        "## Retries\n\n1. Use it like this:\n\n"
        "    ```python\n    # Enqueue at the front\n    q()\n    ```\n"
    )
    assert [s.title for s in split_sections(clean_markdown(md), "markdown")] == ["Retries"]


def test_rst_underlined_titles_are_headings():
    rst = (
        "Celery\n======\n\nCelery is a simple task queue for distributed processing.\n\n"
        "What do I need?\n---------------\n\nPython 3.9 or newer is required to run it.\n"
    )
    chunks = chunk_readme(rst, RST_URL)
    assert [c.section_title for c in chunks] == ["Celery", "What do I need?"]


def test_rst_directives_and_substitutions_removed():
    rst = (
        ".. image:: https://x/banner.png\n    :alt: banner\n\n|build| |coverage|\n\n"
        "Title\n=====\n\nA real paragraph of text describing the project in detail.\n"
    )
    chunks = chunk_readme(rst, RST_URL)
    joined = " ".join(c.content for c in chunks)
    assert "banner.png" not in joined and "|build|" not in joined
    assert "A real paragraph" in joined


def test_long_section_split_with_overlap():
    para = "word " * 60  # ~300 chars per paragraph
    md = "# Big\n\n" + "\n\n".join(para.strip() + f" p{i}" for i in range(10))
    chunks = chunk_readme(md, MD_URL, max_chars=1200, overlap=150)
    assert len(chunks) >= 3
    assert all(len(c.content) <= 1200 for c in chunks)
    tail = chunks[0].content[-60:]
    assert tail.split()[-1] in chunks[1].content[:200]


def test_html_images_and_badges_removed():
    out = clean_markdown('<p align="center"><img src="x"></p>\n[![CI](b.svg)](ci)\nReal text')
    assert out.strip() == "Real text"


def test_links_keep_their_text():
    assert clean_markdown("See [the docs](https://x.dev) now").strip() == "See the docs now"


def test_max_chunks_enforced():
    md = "\n\n".join(f"## S{i}\n\nSection {i} body text long enough to be kept." for i in range(60))
    assert len(chunk_readme(md, MD_URL, max_chunks=40)) == 40


def test_tiny_chunks_dropped():
    assert chunk_readme("# T\n\nshort", MD_URL) == []


def test_empty_or_none_readme_gives_no_chunks():
    assert chunk_readme("", None) == []
    assert chunk_readme(None, None) == []
