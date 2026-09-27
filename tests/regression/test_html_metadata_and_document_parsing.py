"""Real HTML parsing enforces metadata safety and visible document extraction."""

from html.parser import HTMLParser

import pytest

from kailash.nodes.data.readers import DocumentProcessorNode
from kailash.trust.security import TrustSecurityValidator


@pytest.mark.parametrize(
    "unsafe",
    [
        "<script>alert(1)</script>",
        "<script>alert(1)</script >",
        "<ScRiPt>alert(1)</ScRiPt\t\n>",
        "<script src='https://example.invalid/active.js'>",
        "<script/>alert(1)</script>",
        "<script src=x/>alert(1)</script>",
        "<style>body{display:none}</style >",
        "<style>unclosed content",
        "<script>unclosed content",
        "<scr<script>removed</script>ipt>alert(1)</script>",
        "<scr<script>removed</script >ipt>alert(1)</script >",
    ],
)
def test_metadata_drops_script_content_in_keys_and_nested_values(unsafe):
    output = TrustSecurityValidator().sanitize_metadata(
        {unsafe: {"nested": [unsafe, {"deep": unsafe}], "number": 7}}
    )
    assert output == {"": {"nested": ["", {"deep": ""}], "number": 7}}


@pytest.mark.parametrize(
    "unsafe",
    [
        '<img src="x" onerror="alert(1)">',
        '<a href="javascript:alert(1)">link</a>',
        '<a href="jav&#x61;script:alert(1)">link</a>',
        '<a href="javajavascript:script:alert(1)">link</a>',
        '<a href="data:text/html,<script>alert(1)</script>">link</a>',
        '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
        '<svg><a xlink:href="javascript:alert(1)">link</a></svg>',
    ],
)
def test_metadata_removes_active_attributes_and_elements(unsafe):
    output = TrustSecurityValidator().sanitize_metadata({"value": unsafe})["value"]

    class Inspect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag not in {"script", "iframe", "svg"}
            for name, value in attrs:
                assert not name.startswith("on")
                assert name != "srcdoc"
                if name in {"href", "src", "xlink:href"}:
                    assert not value.lower().startswith(("javascript:", "data:"))

    Inspect(convert_charrefs=True).feed(output)
    assert "javascript:" not in output


def test_metadata_preserves_benign_markup_text_and_container_types():
    source = {
        "<b>name</b>": ["<p>Hello <em>world</em></p>", 2, None, {"ok": True}],
        "ordinary": "Normal description",
    }
    assert TrustSecurityValidator().sanitize_metadata(source) == source


def test_metadata_escapes_literal_entity_text_without_reactivating_markup():
    source = "&lt;script&gt;literal&lt;/script&gt; & text"
    output = TrustSecurityValidator().sanitize_metadata({"text": source})["text"]
    assert output == "&lt;script&gt;literal&lt;/script&gt; &amp; text"
    assert "<script>" not in output


def test_metadata_retains_legacy_literal_token_removal():
    output = TrustSecurityValidator().sanitize_metadata(
        {"text": "javascript:plain onclick=plain data:text/html"}
    )["text"]
    assert output == "plain plain "
    assert len(TrustSecurityValidator.UNSAFE_PATTERNS) == 4


@pytest.mark.parametrize("tag", ["script", "style"])
@pytest.mark.parametrize("closing", [">", " >", "\t\n>"])
def test_document_drops_hidden_text_with_valid_close_spacing(tmp_path, tag, closing):
    source = f"before<{tag}>hidden-canary</{tag}{closing}after"
    path = tmp_path / "visible.html"
    path.write_text(source)
    output = DocumentProcessorNode().execute(file_path=str(path))
    assert output["content"] == "beforeafter"
    assert output["metadata"]["original_html_length"] == len(source)
    assert "hidden-canary" not in str(output["sections"])


@pytest.mark.parametrize(
    "opening", ["<script>", "<script/>", "<script src=x>", "<style>"]
)
def test_document_unclosed_hidden_elements_do_not_escape_into_text(tmp_path, opening):
    path = tmp_path / "unclosed.html"
    path.write_text("visible" + opening + "hidden-canary<h1>fake heading</h1>")
    output = DocumentProcessorNode().execute(file_path=str(path))
    assert output["content"] == "visible"
    assert output["sections"] == []


@pytest.mark.parametrize("preserve_structure", [True, False])
def test_document_preserves_visible_text_and_heading_positions(
    tmp_path, preserve_structure
):
    source = "<title>Title</title>\n<p>Intro</p>\u2028<h2>Safe <b>heading</b></h2><p>A &amp; B</p>"
    path = tmp_path / "headings.html"
    path.write_text(source)
    output = DocumentProcessorNode().execute(
        file_path=str(path), preserve_structure=preserve_structure
    )
    assert output["content"] == "Title Intro Safe headingA & B"
    assert output["metadata"]["character_count"] == len(output["content"])
    assert output["metadata"]["word_count"] == len(output["content"].split())
    if preserve_structure:
        assert output["sections"][0]["content"] == "Title"
        heading = output["sections"][1]
        assert heading["level"] == 2
        assert heading["content"] == heading["title"] == "Safe heading"
        assert (
            source[heading["start_position"] : heading["end_position"]]
            == "<h2>Safe <b>heading</b></h2>"
        )
    else:
        assert output["sections"] == []


@pytest.mark.parametrize(
    "text",
    [
        "Normal description",
        "<b>safe</b>",
        '<a href="https://example.invalid/">safe</a>',
        "&lt;script&gt;literal&lt;/script&gt;",
        "javajavascript:script:plain",
        "java&#x73;cript:plain",
        "<scr<script>removed</script>ipt>alert(1)</script>",
        "<style>hidden</style >safe",
    ],
)
def test_metadata_repeated_sanitization_is_stable(text):
    validator = TrustSecurityValidator()
    first = validator.sanitize_metadata({"value": text})
    assert validator.sanitize_metadata(first) == first
    if "java" in text:
        assert first == {"value": "plain"}


@pytest.mark.parametrize("placement", ["key", "value", "nested"])
def test_metadata_rejects_nonconverging_cleanup_with_bounded_full_passes(
    monkeypatch, placement
):
    import nh3

    from kailash.trust.security import ValidationError

    original = nh3.clean
    calls = []

    def counted(text):
        calls.append(len(text))
        return original(text)

    monkeypatch.setattr(nh3, "clean", counted)
    hostile = "java" * 350 + "script:" * 350
    metadata = {hostile: 1} if placement == "key" else {"key": hostile}
    if placement == "nested":
        metadata = {"outer": [{"inner": hostile}]}
    with pytest.raises(
        ValidationError, match="did not stabilize within 16 passes"
    ) as error:
        TrustSecurityValidator().sanitize_metadata(metadata)
    # Ordinary surrounding keys add one pass each; hostile nesting cannot
    # increase the full sanitizer budget for the attacked string itself.
    assert sum(length > 1000 for length in calls) == 16
    assert hostile not in str(error.value)


@pytest.mark.parametrize("depth", [1, 2, 5, 14])
def test_metadata_normal_nested_token_cleanup_remains_stable(depth):
    validator = TrustSecurityValidator()
    metadata = {"text": "<b>safe</b>" + "java" * depth + "script:" * depth}
    assert validator.sanitize_metadata(metadata) == {"text": "<b>safe</b>"}
    assert validator.sanitize_metadata({"text": "<b>safe</b>"}) == {
        "text": "<b>safe</b>"
    }


@pytest.mark.parametrize(
    "hostile", ["<script" * 4000, "on" * 5000, "java" * 2000 + "script:" * 2000]
)
@pytest.mark.parametrize("placement", ["key", "value", "nested"])
def test_metadata_size_limit_precedes_regex_and_html_parsing(
    monkeypatch, hostile, placement
):
    import nh3

    from kailash.trust.security import ValidationError

    scanned = []
    originals = TrustSecurityValidator.UNSAFE_PATTERNS
    original_clean = nh3.clean

    class Track:
        def __init__(self, pattern):
            self.pattern = pattern

        def sub(self, replacement, text):
            scanned.append(len(text))
            return self.pattern.sub(replacement, text)

    def clean(text):
        scanned.append(len(text))
        return original_clean(text)

    monkeypatch.setattr(
        TrustSecurityValidator, "UNSAFE_PATTERNS", [Track(p) for p in originals]
    )
    monkeypatch.setattr(nh3, "clean", clean)
    metadata = {hostile: 1} if placement == "key" else {"key": hostile}
    if placement == "nested":
        metadata = {"outer": [{"inner": hostile}]}
    with pytest.raises(ValidationError, match="exceeds 8192 characters") as error:
        TrustSecurityValidator().sanitize_metadata(metadata)
    assert all(length <= 8192 for length in scanned)
    assert hostile not in str(error.value)


def test_metadata_accepts_documented_maximum_string_length():
    safe = "x" * 8192
    assert TrustSecurityValidator().sanitize_metadata({"text": safe}) == {"text": safe}
