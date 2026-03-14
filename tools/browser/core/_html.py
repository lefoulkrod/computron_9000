"""Shared HTML-to-markdown converter for browser tools."""

from __future__ import annotations

import html2text

_converter = html2text.HTML2Text()
_converter.ignore_images = True
_converter.ignore_emphasis = False
_converter.body_width = 0
_converter.protect_links = True
_converter.unicode_snob = True


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown."""
    return _converter.handle(html)


__all__ = ["html_to_markdown"]
