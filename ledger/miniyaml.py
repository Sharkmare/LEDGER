from __future__ import annotations

import re
from typing import Any

INT_PATTERN = re.compile(r"^[-+]?\d+$")
FLOAT_PATTERN = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
NULL_WORDS = {"", "~", "null", "Null", "NULL"}
TRUE_WORDS = {"true", "True", "TRUE"}
FALSE_WORDS = {"false", "False", "FALSE"}
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", " ": " "}
UNSUPPORTED_STARTS = ("&", "*", "!", "@", "`", "%")


class YamlError(ValueError):
    pass


def _fail(line_number: int, message: str) -> YamlError:
    return YamlError(f"YAML line {line_number}: {message}")


def _strip_comment(text: str) -> str:
    quote = ""
    for index, character in enumerate(text):
        if quote:
            if character == quote and not (quote == '"' and text[index - 1] == "\\"):
                quote = ""
        elif character in "\"'" and (index == 0 or text[index - 1] in " [{,:"):
            quote = character
        elif character == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
    return text.rstrip()


def _plain_scalar(text: str) -> Any:
    if text in NULL_WORDS:
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    if INT_PATTERN.match(text):
        return int(text)
    if text.lower().startswith(("0x", "-0x")) and re.match(r"^-?0x[0-9a-fA-F]+$", text):
        return int(text, 16)
    if FLOAT_PATTERN.match(text):
        return float(text)
    return text


def _read_double_quoted(text: str, start: int, line_number: int) -> tuple[str, int]:
    out, index = [], start + 1
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 1
            if index >= len(text):
                break
            code = text[index]
            if code == "u":
                out.append(chr(int(text[index + 1:index + 5], 16)))
                index += 4
            elif code in ESCAPES:
                out.append(ESCAPES[code])
            else:
                raise _fail(line_number, f"unknown escape \\{code}")
        elif character == '"':
            return "".join(out), index + 1
        else:
            out.append(character)
        index += 1
    raise _fail(line_number, "a double-quoted string is not closed on the same line")


def _read_single_quoted(text: str, start: int, line_number: int) -> tuple[str, int]:
    out, index = [], start + 1
    while index < len(text):
        if text[index] == "'":
            if text[index + 1:index + 2] == "'":
                out.append("'")
                index += 2
                continue
            return "".join(out), index + 1
        out.append(text[index])
        index += 1
    raise _fail(line_number, "a single-quoted string is not closed on the same line")


def _read_flow(text: str, index: int, line_number: int, stop: str) -> tuple[Any, int]:
    while index < len(text) and text[index] == " ":
        index += 1
    if index >= len(text):
        raise _fail(line_number, "a flow collection is not closed on the same line")
    character = text[index]
    if character == "[":
        items, index = [], index + 1
        while True:
            while index < len(text) and text[index] == " ":
                index += 1
            if index >= len(text):
                raise _fail(line_number, "a flow list is not closed on the same line")
            if text[index] == "]":
                return items, index + 1
            value, index = _read_flow(text, index, line_number, ",]")
            items.append(value)
            while index < len(text) and text[index] == " ":
                index += 1
            if index < len(text) and text[index] == ",":
                index += 1
    if character == "{":
        mapping, index = {}, index + 1
        while True:
            while index < len(text) and text[index] == " ":
                index += 1
            if index >= len(text):
                raise _fail(line_number, "a flow map is not closed on the same line")
            if text[index] == "}":
                return mapping, index + 1
            key, index = _read_flow(text, index, line_number, ":,}")
            while index < len(text) and text[index] == " ":
                index += 1
            value = None
            if index < len(text) and text[index] == ":":
                value, index = _read_flow(text, index + 1, line_number, ",}")
            mapping[str(key)] = value
            while index < len(text) and text[index] == " ":
                index += 1
            if index < len(text) and text[index] == ",":
                index += 1
    if character == '"':
        return _read_double_quoted(text, index, line_number)
    if character == "'":
        return _read_single_quoted(text, index, line_number)
    if character in UNSUPPORTED_STARTS:
        raise _fail(line_number, f"{character!r} (anchors, aliases and tags) is not supported; convert the file to JSON")
    end = index
    while end < len(text) and text[end] not in stop:
        end += 1
    return _plain_scalar(text[index:end].strip()), end


def _inline_value(text: str, line_number: int) -> Any:
    text = _strip_comment(text.strip())
    if not text:
        return None
    if text[0] in "[{":
        value, end = _read_flow(text, 0, line_number, "")
        if text[end:].strip():
            raise _fail(line_number, "unexpected text after a flow collection")
        return value
    if text[0] == '"':
        value, end = _read_double_quoted(text, 0, line_number)
        if text[end:].strip():
            raise _fail(line_number, "unexpected text after a quoted string")
        return value
    if text[0] == "'":
        value, end = _read_single_quoted(text, 0, line_number)
        if text[end:].strip():
            raise _fail(line_number, "unexpected text after a quoted string")
        return value
    if text[0] in UNSUPPORTED_STARTS:
        raise _fail(line_number, f"{text[0]!r} (anchors, aliases and tags) is not supported; convert the file to JSON")
    return _plain_scalar(text)


def _split_key(content: str, line_number: int) -> tuple[str, str] | None:
    if content[0] in "\"'":
        reader = _read_double_quoted if content[0] == '"' else _read_single_quoted
        key, end = reader(content, 0, line_number)
        rest = content[end:].lstrip()
        return (key, rest[1:].strip()) if rest.startswith(":") else None
    if content[0] in "[{":
        return None
    match = re.match(r"^(.*?):(?:\s+(.*))?$", content)
    if not match or content.startswith("- "):
        return None
    key = match.group(1)
    if " #" in key:
        return None
    return key.strip(), (match.group(2) or "").strip()


class _Parser:
    def __init__(self, text: str):
        if "\t" in "".join(line[:len(line) - len(line.lstrip())] for line in text.splitlines()):
            raise YamlError("YAML indents with spaces, not tabs")
        self.lines = text.replace("\r\n", "\n").split("\n")
        self.index = 0

    def peek(self) -> tuple[int, str, int] | None:
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            stripped = raw.strip()
            if stripped and not stripped.startswith("#"):
                if stripped in ("---", "...") and self.index > 0:
                    if stripped == "---":
                        raise _fail(self.index + 1, "more than one YAML document is not supported")
                    self.index = len(self.lines)
                    return None
                return len(raw) - len(raw.lstrip()), stripped, self.index + 1
            self.index += 1
        return None

    def parse_node(self, indent: int) -> Any:
        line = self.peek()
        if line is None or line[0] < indent:
            return None
        level, content, number = line
        if content.startswith("- ") or content == "-":
            return self.parse_sequence(level)
        if _split_key(content, number) is not None:
            return self.parse_mapping(level)
        self.index += 1
        return self.finish_plain(content, level - 1, number)

    def finish_plain(self, first: str, parent_indent: int, number: int) -> Any:
        value = _inline_value(first, number)
        if not isinstance(value, str) or first.strip()[:1] in "\"'":
            return value
        parts = [first.strip()]
        while True:
            following = self.peek()
            if following is None or following[0] <= parent_indent or following[1].startswith("- ") or _split_key(following[1], following[2]):
                break
            parts.append(_strip_comment(following[1]))
            self.index += 1
        return _plain_scalar(" ".join(parts)) if len(parts) > 1 else value

    def parse_sequence(self, indent: int) -> list:
        items = []
        while True:
            line = self.peek()
            if line is None or line[0] != indent or not (line[1].startswith("- ") or line[1] == "-"):
                return items
            _, content, number = line
            rest = content[1:].strip()
            if not rest or rest.startswith("#"):
                self.index += 1
                following = self.peek()
                items.append(self.parse_node(following[0]) if following and following[0] > indent else None)
                continue
            offset = indent + len(content) - len(content[1:].lstrip())
            if rest[0] in "|>" and re.match(r"^[|>][-+]?\d*$", _strip_comment(rest)):
                self.index += 1
                items.append(self.block_scalar(_strip_comment(rest), indent, number))
            elif rest.startswith("- ") or _split_key(rest, number) is not None:
                self.lines[self.index] = " " * offset + rest
                items.append(self.parse_node(offset))
            else:
                self.index += 1
                items.append(self.finish_plain(rest, indent, number))

    def parse_mapping(self, indent: int) -> dict:
        mapping: dict[str, Any] = {}
        while True:
            line = self.peek()
            if line is None or line[0] != indent or line[1].startswith("- ") or line[1] == "-":
                return mapping
            _, content, number = line
            split = _split_key(content, number)
            if split is None:
                raise _fail(number, "expected key: value")
            key, rest = split
            if key == "<<":
                raise _fail(number, "merge keys are not supported; convert the file to JSON")
            if key in mapping:
                raise _fail(number, f"the key {key!r} appears twice")
            self.index += 1
            rest = _strip_comment(rest) if rest[:1] not in "\"'" else rest
            if rest == "":
                following = self.peek()
                if following and following[0] > indent:
                    mapping[key] = self.parse_node(following[0])
                elif following and following[0] == indent and (following[1].startswith("- ") or following[1] == "-"):
                    mapping[key] = self.parse_sequence(indent)
                else:
                    mapping[key] = None
            elif re.match(r"^[|>][-+]?\d*$", rest):
                mapping[key] = self.block_scalar(rest, indent, number)
            else:
                mapping[key] = self.finish_plain(rest, indent, number)

    def block_scalar(self, header: str, parent_indent: int, number: int) -> str:
        style, chomp = header[0], ("-" if "-" in header else "+" if "+" in header else "")
        collected: list[str] = []
        block_indent = None
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            if raw.strip() == "":
                collected.append("")
                self.index += 1
                continue
            level = len(raw) - len(raw.lstrip())
            if level <= parent_indent:
                break
            block_indent = level if block_indent is None else block_indent
            if level < block_indent:
                break
            collected.append(raw[block_indent:])
            self.index += 1
        trailing = 0
        while collected and collected[-1] == "":
            collected.pop()
            trailing += 1
        if style == "|":
            text = "\n".join(collected)
        else:
            text, previous_blank = "", False
            for position, line in enumerate(collected):
                if position == 0:
                    text = line
                elif line == "":
                    text += "\n"
                    previous_blank = True
                else:
                    text += ("" if previous_blank else " ") + line
                    previous_blank = False
        if not collected:
            return ""
        if chomp == "-":
            return text
        if chomp == "+":
            return text + "\n" * (trailing + 1)
        return text + "\n"


def loads(text: str) -> Any:
    parser = _Parser(text)
    first = parser.peek()
    if first and first[1] == "---":
        parser.index += 1
    elif first and first[1].startswith("---"):
        raise _fail(first[2], "put the first value on its own line after ---")
    if parser.peek() is None:
        return None
    value = parser.parse_node(0)
    leftover = parser.peek()
    if leftover is not None:
        raise _fail(leftover[2], "unexpected content; check the indentation")
    return value
