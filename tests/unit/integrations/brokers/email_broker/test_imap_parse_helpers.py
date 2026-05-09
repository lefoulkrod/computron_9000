"""Unit tests for the pure parse helpers in ``email_broker._imap_client``.

These cover the message-byte-blob → typed-domain-object boundary: the FETCH
preamble splitter, the RFC 2047 header decoder, the Date-header normalizer,
and the multipart-body-to-text rendering. Everything here is offline and
doesn't touch IMAP — building inputs from `email.message.EmailMessage` keeps
each assertion focused on one parser concern at a time.
"""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from integrations.brokers.email_broker._imap_client import (
    _collect_fetch_pairs,
    _decode_header,
    _decode_part_payload,
    _extract_body_text,
    _find_part,
    _html_to_markdown,
    _normalize_date,
    _parse_header_hit,
)


# ── _collect_fetch_pairs ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_collect_fetch_pairs_extracts_uid_and_payload_for_each_hit() -> None:
    """A typical multi-message FETCH response yields one pair per message.

    imaplib emits each hit as a 2-tuple ``(preamble_with_UID, raw_bytes)``.
    The helper pulls the UID out of the preamble bytes and pairs it with the
    payload — the ``b")"`` closer between hits is ignored.
    """
    data = [
        (b"1 (UID 100 BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {12}", b"From: a@b\n"),
        b")",
        (b"2 (UID 101 BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {12}", b"From: c@d\n"),
        b")",
    ]
    assert _collect_fetch_pairs(data) == [
        ("100", b"From: a@b\n"),
        ("101", b"From: c@d\n"),
    ]


@pytest.mark.unit
def test_collect_fetch_pairs_skips_items_without_uid() -> None:
    """Preambles missing the UID token are dropped silently — those happen on
    odd server responses (e.g. NOOP-style untagged updates) and we don't want
    to pretend we have a real message there.
    """
    data = [
        (b"1 (FLAGS (\\Seen))", b"<no UID here>"),
        (b"2 (UID 42 BODY[...] {3}", b"hi\n"),
    ]
    assert _collect_fetch_pairs(data) == [("42", b"hi\n")]


@pytest.mark.unit
def test_collect_fetch_pairs_skips_non_tuple_entries() -> None:
    """Closing parens (``b")"``), ints, and stray strings shouldn't crash —
    they just aren't message hits.
    """
    data = [b")", "stray-str", 7, (b"1 (UID 1 BODY[...] {1}", b"x")]
    assert _collect_fetch_pairs(data) == [("1", b"x")]


@pytest.mark.unit
def test_collect_fetch_pairs_returns_empty_for_empty_input() -> None:
    """No hits → empty list (not None)."""
    assert _collect_fetch_pairs([]) == []


# ── _decode_header ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_decode_header_returns_empty_for_empty_input() -> None:
    """No header value → empty string, no exception."""
    assert _decode_header("") == ""


@pytest.mark.unit
def test_decode_header_passes_plain_ascii_unchanged() -> None:
    """ASCII headers don't carry RFC 2047 encoded-words, so they're returned
    verbatim modulo whitespace trimming.
    """
    assert _decode_header("Hello world") == "Hello world"


@pytest.mark.unit
def test_decode_header_decodes_rfc2047_base64_utf8() -> None:
    """``=?UTF-8?B?...?=`` is the wire form for non-ASCII subjects/from-names.

    The helper has to round-trip the base64 + utf-8 charset back into a unicode
    string, otherwise the agent would see garbled bytes for any non-English
    header.
    """
    # "Héllo" base64-encoded as UTF-8.
    encoded = "=?UTF-8?B?SMOpbGxv?="
    assert _decode_header(encoded) == "Héllo"


@pytest.mark.unit
def test_decode_header_decodes_rfc2047_quoted_printable() -> None:
    """Quoted-printable is the other RFC 2047 encoding the decoder must
    handle (used by some clients for short non-ASCII strings).
    """
    encoded = "=?UTF-8?Q?caf=C3=A9?="
    assert _decode_header(encoded) == "café"


@pytest.mark.unit
def test_decode_header_concatenates_mixed_segments() -> None:
    """Real-world subjects often mix plain ASCII and encoded-words. The
    decoder must concatenate them without losing the unencoded segments.
    """
    encoded = '"=?UTF-8?B?SsO8cmdlbg==?=" <jurgen@example.com>'
    out = _decode_header(encoded)
    assert "Jürgen" in out
    assert "<jurgen@example.com>" in out


@pytest.mark.unit
def test_decode_header_falls_back_to_utf8_for_unknown_charset() -> None:
    """A bogus charset label shouldn't throw — the helper falls back to
    utf-8 with ``errors="replace"`` so the caller always gets a string.
    """
    # Charset "x-bogus" doesn't exist; the bytes themselves are valid UTF-8.
    encoded = "=?x-bogus?B?aGVsbG8=?="
    assert _decode_header(encoded) == "hello"


# ── _normalize_date ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_normalize_date_returns_empty_for_empty_input() -> None:
    """No Date header → empty string."""
    assert _normalize_date("") == ""


@pytest.mark.unit
def test_normalize_date_converts_rfc2822_to_iso8601() -> None:
    """RFC 2822 ``Tue, 1 Apr 2026 09:30:00 -0400`` → ``2026-04-01T09:30:00-04:00``.

    Normalizing to ISO 8601 makes the value consistent across providers and
    sortable lexicographically, which is what the agent and frontend both want.
    """
    iso = _normalize_date("Tue, 1 Apr 2026 09:30:00 -0400")
    assert iso.startswith("2026-04-01T09:30:00")
    assert iso.endswith("-04:00")


@pytest.mark.unit
def test_normalize_date_returns_input_unchanged_when_unparseable() -> None:
    """Non-RFC dates (rare, but seen in spam) are returned as-is rather than
    discarded — better to show *something* than blank out the field.
    """
    weird = "definitely not a date"
    assert _normalize_date(weird) == weird


# ── _html_to_markdown ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_html_to_markdown_preserves_link_text_and_url() -> None:
    """Links must round-trip as ``[text](url)`` — for confirmation /
    unsubscribe / invoice links, losing the URL would defeat the point of
    showing the email to the agent.
    """
    html = '<p>Click <a href="https://example.com/confirm">here</a> to confirm.</p>'
    out = _html_to_markdown(html)
    # ``protect_links=True`` wraps the URL in angle brackets — valid GFM,
    # keeps URLs from getting split if anything downstream rewraps lines.
    assert "[here](<https://example.com/confirm>)" in out


@pytest.mark.unit
def test_html_to_markdown_drops_style_and_script_content() -> None:
    """``<style>`` and ``<script>`` bodies are CSS / JS noise — the agent
    should see neither the tags nor what's between them.
    """
    html = (
        "<html><head><style>.x { color: red; }</style></head>"
        "<body><script>alert('hi')</script><p>Real body.</p></body></html>"
    )
    out = _html_to_markdown(html)
    assert "Real body." in out
    assert "color: red" not in out
    assert "alert" not in out


@pytest.mark.unit
def test_html_to_markdown_decodes_html_entities() -> None:
    """Entities like ``&amp;`` / ``&nbsp;`` / ``&#8212;`` must come out as
    real characters rather than literal entity strings, otherwise the agent
    sees ``Q&amp;A`` instead of ``Q&A``.
    """
    html = "<p>Q&amp;A &mdash; tips &nbsp;and tricks</p>"
    out = _html_to_markdown(html)
    assert "Q&A" in out
    assert "&amp;" not in out
    assert "&mdash;" not in out


@pytest.mark.unit
def test_html_to_markdown_renders_lists_as_markdown() -> None:
    """Bullet lists should survive as ``* item`` lines — preserves structure
    so the agent can summarize per-item rather than treating the email as
    one wall of text.
    """
    html = "<ul><li>first</li><li>second</li><li>third</li></ul>"
    out = _html_to_markdown(html)
    assert "first" in out
    assert "second" in out
    assert "third" in out
    # html2text emits ``  * `` for unordered list items.
    assert "* first" in out


@pytest.mark.unit
def test_html_to_markdown_returns_empty_for_empty_input() -> None:
    """Empty in → empty out (after the trailing-whitespace strip)."""
    assert _html_to_markdown("") == ""


# ── _decode_part_payload ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_decode_part_payload_decodes_utf8_text_part() -> None:
    """A UTF-8 ``text/plain`` part must round-trip its content untouched."""
    msg = EmailMessage()
    msg.set_content("héllo world", charset="utf-8")
    assert _decode_part_payload(msg) == "héllo world\n"


@pytest.mark.unit
def test_decode_part_payload_falls_back_to_utf8_for_unknown_charset() -> None:
    """If a part declares a bogus charset, the helper falls back to utf-8
    with ``errors="replace"`` rather than raising — the agent gets best-effort
    text instead of a hard failure on weird mail.
    """
    msg = EmailMessage()
    msg.set_content("plain ascii")
    # Force a charset that Python doesn't know about.
    msg.replace_header("Content-Type", 'text/plain; charset="x-bogus"')
    out = _decode_part_payload(msg)
    assert "plain ascii" in out


# ── _find_part ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_find_part_returns_matching_leaf() -> None:
    """``walk()`` visits both the multipart container and its leaves;
    ``_find_part`` should skip the container and return only a leaf with
    the matching content-type.
    """
    msg = EmailMessage()
    msg.set_content("plain version")
    msg.add_alternative("<p>html version</p>", subtype="html")

    plain = _find_part(msg, "text/plain")
    html = _find_part(msg, "text/html")
    assert plain is not None and "plain version" in plain.get_content()
    assert html is not None and "html version" in html.get_content()


@pytest.mark.unit
def test_find_part_returns_none_when_missing() -> None:
    """Looking for a content-type the message doesn't contain returns None,
    not an exception — caller decides what to do (fall back to HTML, etc.).
    """
    msg = EmailMessage()
    msg.set_content("plain only")
    assert _find_part(msg, "text/html") is None


# ── _extract_body_text ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_extract_body_text_prefers_text_plain_in_multipart() -> None:
    """When both plaintext and HTML alternatives exist, return the plaintext.

    Plain is what the sender wrote; HTML often duplicates it with markup the
    agent doesn't need.
    """
    msg = EmailMessage()
    msg.set_content("plain version")
    msg.add_alternative("<p>html version</p>", subtype="html")
    out = _extract_body_text(msg)
    assert "plain version" in out
    assert "html version" not in out


@pytest.mark.unit
def test_extract_body_text_falls_back_to_html_as_markdown() -> None:
    """HTML-only messages get rendered to Markdown rather than returning
    empty. Tags become structure (``**bold**``); URLs survive intact.
    """
    msg = EmailMessage()
    msg.set_content(
        '<p>Hello <b>world</b> — see <a href="https://example.com">site</a>.</p>',
        subtype="html",
    )
    out = _extract_body_text(msg)
    assert "Hello" in out
    assert "**world**" in out  # html2text marks bold as Markdown emphasis
    assert "[site](<https://example.com>)" in out


@pytest.mark.unit
def test_extract_body_text_returns_plaintext_for_single_part_text() -> None:
    """Non-multipart text/plain → its content unchanged (modulo trailing
    newline that ``EmailMessage`` adds).
    """
    msg = EmailMessage()
    msg.set_content("just some words")
    assert "just some words" in _extract_body_text(msg)


@pytest.mark.unit
def test_extract_body_text_renders_single_part_html_as_markdown() -> None:
    """Non-multipart text/html → Markdown via html2text — no raw tags leak."""
    msg = EmailMessage()
    msg.set_content("<div>tagged <i>content</i></div>", subtype="html")
    out = _extract_body_text(msg)
    assert "<" not in out
    assert "tagged" in out and "content" in out
    # Italic survives as Markdown emphasis.
    assert "_content_" in out or "*content*" in out


@pytest.mark.unit
def test_extract_body_text_returns_empty_for_multipart_with_no_text_parts() -> None:
    """A multipart message that's nothing but attachments shouldn't crash;
    we return empty text so the caller can render headers + ``(no text body)``.
    """
    msg = EmailMessage()
    msg.set_content("placeholder")  # gets replaced by add_attachment below
    # Replace single-part with a multipart that has only an attachment.
    msg = EmailMessage()
    msg.make_mixed()
    msg.add_attachment(b"\x00\x01\x02", maintype="application", subtype="octet-stream", filename="blob.bin")
    assert _extract_body_text(msg) == ""


# ── _parse_header_hit ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parse_header_hit_populates_envelope_fields() -> None:
    """End-to-end: raw header bytes from a FETCH response → ``MessageHeader``
    with from / to / subject / date filled, plus the uid + folder the caller
    passed in.
    """
    raw = (
        b"From: alice@example.com\r\n"
        b"To: bob@example.com\r\n"
        b"Subject: Hello\r\n"
        b"Date: Tue, 1 Apr 2026 09:30:00 -0400\r\n"
        b"\r\n"
    )
    header = _parse_header_hit(uid="42", raw=raw, folder="INBOX")
    assert header.uid == "42"
    assert header.folder == "INBOX"
    assert header.from_ == "alice@example.com"
    assert header.to == "bob@example.com"
    assert header.subject == "Hello"
    assert header.date.startswith("2026-04-01T09:30:00")


@pytest.mark.unit
def test_parse_header_hit_handles_missing_fields_gracefully() -> None:
    """Servers can return partial header sets; absent fields become empty
    strings rather than raising.
    """
    raw = b"Subject: only-subject\r\n\r\n"
    header = _parse_header_hit(uid="1", raw=raw, folder="Drafts")
    assert header.subject == "only-subject"
    assert header.from_ == ""
    assert header.to == ""
    assert header.date == ""


@pytest.mark.unit
def test_parse_header_hit_decodes_encoded_word_subject() -> None:
    """Subjects often arrive RFC 2047-encoded; ``_parse_header_hit`` must run
    them through ``_decode_header`` before populating the model.
    """
    raw = (
        b"Subject: =?UTF-8?B?SMOpbGxv?=\r\n"
        b"\r\n"
    )
    header = _parse_header_hit(uid="9", raw=raw, folder="INBOX")
    assert header.subject == "Héllo"
