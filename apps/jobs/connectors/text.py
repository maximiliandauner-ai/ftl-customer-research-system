from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Literal

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
DROP_TAGS = {"button", "canvas", "form", "iframe", "noscript", "script", "style", "svg"}


def normalize_text(value: str) -> str:
    lines: list[str] = []
    for line in value.replace("\r", "\n").split("\n"):
        clean = re.sub(r"[\t\f\v ]+", " ", line).strip()
        if clean and (not lines or lines[-1] != clean):
            lines.append(clean)
    return "\n".join(lines).strip()


class PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_TAGS:
            self.drop_depth += 1
        elif self.drop_depth == 0 and tag in BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_TAGS and self.drop_depth:
            self.drop_depth -= 1
        elif self.drop_depth == 0 and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.drop_depth == 0:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = PlainTextParser()
    parser.feed(value)
    parser.close()
    return normalize_text("".join(parser.parts))


def classify_section(
    heading: str,
) -> Literal["description", "responsibilities", "requirements", "benefits", "other"]:
    normalized = heading.casefold()
    if any(word in normalized for word in ("responsib", "what you", "your role", "tasks")):
        return "responsibilities"
    if any(word in normalized for word in ("require", "qualif", "experience", "profile")):
        return "requirements"
    if any(word in normalized for word in ("benefit", "offer", "perks", "why join")):
        return "benefits"
    if any(word in normalized for word in ("description", "about", "overview")):
        return "description"
    return "other"
