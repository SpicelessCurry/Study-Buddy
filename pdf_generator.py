"""PDF Generator module for Study Buddy RAG application.

Generates professional academic PDF documents:
1. Study Material PDFs (with cover page, table of contents, structured headings, code blocks, callouts)
2. Question Paper PDFs (with cover page, numbered questions, and dedicated answer key section)

Built using fpdf2 with resilient Unicode handling, pagination, and styling.
"""

from __future__ import annotations

import html
import logging
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Primary brand colors
COLOR_PRIMARY_DARK = (26, 35, 126)    # #1a237e - Deep Navy Blue (Headers, accents)
COLOR_PRIMARY_MID = (40, 53, 147)     # #283593 - Medium Blue (H2)
COLOR_PRIMARY_LIGHT = (57, 73, 171)   # #3949ab - Slate Blue (H3)
COLOR_ACCENT = (92, 107, 192)         # #5c6bc0 - Light Indigo (Borders, metadata)
COLOR_TEXT_MAIN = (33, 33, 33)        # #212121 - Dark Gray / Off-black for body
COLOR_TEXT_MUTED = (117, 117, 117)    # #757575 - Muted gray for captions/subtitles
COLOR_CODE_BG = (245, 246, 248)       # #f5f6f8 - Light gray code background
COLOR_CODE_BORDER = (220, 223, 230)   # #dcdfe6 - Code block border
COLOR_QUOTE_BG = (240, 244, 255)      # #f0f4ff - Callout box light blue fill
COLOR_RULE = (215, 220, 230)          # #d7dce6 - Section dividing rules


class StudyBuddyPDF(FPDF):
    """Custom FPDF subclass supporting running headers, footers, and page tracking."""

    def __init__(
        self,
        doc_title: str = "",
        doc_subtitle: str = "",
        is_question_paper: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the Study Buddy PDF document.

        Args:
            doc_title: Document title shown in header.
            doc_subtitle: Subtitle indicating document type.
            is_question_paper: True if document is a question paper.
            *args: Variable positional arguments forwarded to FPDF.
            **kwargs: Variable keyword arguments forwarded to FPDF.
        """
        super().__init__(*args, **kwargs)
        self.doc_title: str = doc_title
        self.doc_subtitle: str = doc_subtitle
        self.is_question_paper: bool = is_question_paper
        self.enable_header_footer: bool = False
        self.alias_nb_pages()

    def header(self) -> None:
        """Render running header on content pages."""
        if not getattr(self, "enable_header_footer", False):
            return

        self.set_y(8)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(110, 110, 120)

        # Truncate title if long
        clean_title = getattr(self, "doc_title", "")
        if len(clean_title) > 65:
            clean_title = clean_title[:62] + "..."

        self.cell(0, 6, clean_title, align="L")

        badge = "Question Paper" if getattr(self, "is_question_paper", False) else "Study Material"
        self.set_x(self.w - self.r_margin - 35)
        self.cell(35, 6, badge, align="R")

        # Subtle divider rule below header
        self.set_draw_color(*COLOR_RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, 15, self.w - self.r_margin, 15)
        self.ln(9)

    def footer(self) -> None:
        """Render running footer on content pages."""
        if not getattr(self, "enable_header_footer", False):
            return

        self.set_y(-15)
        # Divider line above footer
        self.set_draw_color(*COLOR_RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())

        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*COLOR_TEXT_MUTED)

        # Branding left
        self.cell(0, 10, "Study Buddy  *  AI Academic Learning Platform", align="L")

        # Page number right
        self.set_x(self.w - self.r_margin - 35)
        self.cell(35, 10, f"Page {self.page_no()}/{{nb}}", align="R")


class PDFGenerator:
    """Generates professional academic PDF documents from structured content."""

    def __init__(self) -> None:
        """Initialize PDFGenerator."""
        pass

    def _sanitize_text(self, text: str) -> str:
        """Sanitizes text by replacing unrenderable Unicode characters with safe equivalents.

        Ensures safe encoding for built-in PDF fonts (Helvetica/Courier) without raising
        FPDFUnicodeEncodingException.

        Args:
            text: Raw input string.

        Returns:
            Sanitized string safe for latin-1 encoding.
        """
        if not text:
            return ""

        # Common Unicode typography, math symbols, and bullets mapping
        replacements: dict[str, str] = {
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2014": " -- ",
            "\u2013": " - ",
            "\u2015": " -- ",
            "\u2026": "...",
            "\u2022": "*",
            "\u25aa": "*",
            "\u25ab": "*",
            "\u25cf": "*",
            "\u25cb": "*",
            "\u25b6": ">",
            "\u2713": "[v]",
            "\u2714": "[v]",
            "\u2717": "[x]",
            "\u2718": "[x]",
            "\u2192": "->",
            "\u2190": "<-",
            "\u2194": "<->",
            "\u21d2": "=>",
            "\u21d4": "<=>",
            "\u2264": "<=",
            "\u2265": ">=",
            "\u2260": "!=",
            "\u00b1": "+/-",
            "\u00d7": "x",
            "\u00f7": "/",
            "\u2248": "~",
            "\u00b0": " deg",
            "\u00a0": " ",
            "\u200b": "",
            "\ufeff": "",
            "\u00bd": "1/2",
            "\u00bc": "1/4",
            "\u00be": "3/4",
            "\u221e": "inf",
            "\u2211": "sum",
            "\u221a": "sqrt",
            "\u03c0": "pi",
        }
        for orig, repl in replacements.items():
            text = text.replace(orig, repl)

        # Check latin-1 compatibility
        try:
            text.encode("latin-1")
            return text
        except UnicodeEncodeError:
            import unicodedata

            normalized = unicodedata.normalize("NFKD", text)
            clean_chars: list[str] = []
            for ch in normalized:
                try:
                    ch.encode("latin-1")
                    clean_chars.append(ch)
                except UnicodeEncodeError:
                    clean_chars.append("?")
            return "".join(clean_chars)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitizes a string for use as a file name.

        Args:
            name: Original title or string.

        Returns:
            Sanitized filename safe for Windows and Unix filesystems.
        """
        if not name:
            return "document"
        # Strip forbidden characters: < > : " / \ | ? * and ASCII control characters
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        # Collapse whitespace and repeated underscores
        clean = re.sub(r'[\s_]+', '_', clean.strip())
        clean = clean.strip("._")
        return clean[:100] if clean else "document"

    def _resolve_output_path(self, output_path: str, default_title: str) -> str:
        """Resolves output path and ensures parent directory exists.

        Args:
            output_path: Path to target file or directory.
            default_title: Fallback title used if output_path is a directory.

        Returns:
            Absolute resolved file path ending in .pdf.

        Raises:
            OSError: If output directory cannot be created.
        """
        abs_path = os.path.abspath(output_path)

        # Check if output_path points to an existing directory or ends with a slash
        if os.path.isdir(abs_path) or output_path.endswith(("\\", "/")):
            safe_name = self._sanitize_filename(default_title)
            abs_path = os.path.join(abs_path, f"{safe_name}.pdf")
        elif not abs_path.lower().endswith(".pdf"):
            abs_path = f"{abs_path}.pdf"

        parent_dir = os.path.dirname(abs_path)
        if parent_dir:
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except OSError as e:
                logger.error("Failed to create directory '%s': %s", parent_dir, e)
                raise OSError(f"Failed to create directory '{parent_dir}': {e}") from e

        return abs_path

    def _parse_inline_spans(self, text: str) -> list[dict[str, Any]]:
        """Parses inline formatting into spans with bold, italic, and code flags.

        Args:
            text: Paragraph or item string.

        Returns:
            List of dictionaries describing each span.
        """
        pattern = re.compile(
            r'(\*\*\*(.*?)\*\*\*|'  # bold-italic
            r'\*\*(.*?)\*\*|'       # bold **
            r'__(.*?)__|'           # bold __
            r'\*(.*?)\*|'           # italic *
            r'_(.*?)_|'             # italic _
            r'`(.*?)`)'             # code `
        )
        spans: list[dict[str, Any]] = []
        last_pos = 0

        for match in pattern.finditer(text):
            start, end = match.span()
            if start > last_pos:
                spans.append({
                    "text": text[last_pos:start],
                    "bold": False,
                    "italic": False,
                    "code": False,
                })
            full = match.group(0)
            if full.startswith("***"):
                spans.append({"text": match.group(2), "bold": True, "italic": True, "code": False})
            elif full.startswith("**"):
                spans.append({"text": match.group(3), "bold": True, "italic": False, "code": False})
            elif full.startswith("__"):
                spans.append({"text": match.group(4), "bold": True, "italic": False, "code": False})
            elif full.startswith("*"):
                spans.append({"text": match.group(5), "bold": False, "italic": True, "code": False})
            elif full.startswith("_"):
                spans.append({"text": match.group(6), "bold": False, "italic": True, "code": False})
            elif full.startswith("`"):
                spans.append({"text": match.group(7), "bold": False, "italic": False, "code": True})
            last_pos = end

        if last_pos < len(text):
            spans.append({
                "text": text[last_pos:],
                "bold": False,
                "italic": False,
                "code": False,
            })

        return spans

    def _strip_markdown_inline(self, text: str) -> str:
        """Strips inline markdown formatting tags, leaving clean text.

        Args:
            text: Formatted markdown string.

        Returns:
            Plain text without delimiters.
        """
        text = re.sub(r'\*\*\*(.*?)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'__(.*?)__', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'_(.*?)_', r'\1', text)
        text = re.sub(r'`(.*?)`', r'\1', text)
        return text

    def _markdown_to_html_inline(self, text: str) -> str:
        """Converts inline markdown syntax to basic HTML tags.

        Args:
            text: Markdown text with inline formatting.

        Returns:
            HTML string safe for write_html.
        """
        escaped = html.escape(text, quote=False)
        escaped = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', escaped)
        escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
        escaped = re.sub(r'__(.*?)__', r'<b>\1</b>', escaped)
        escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
        escaped = re.sub(r'_(.*?)_', r'<i>\1</i>', escaped)
        escaped = re.sub(r'`(.*?)`', r'<font face="Courier">\1</font>', escaped)
        return escaped

    def _parse_table(self, lines: list[str]) -> dict[str, Any] | None:
        """Parses markdown table lines into headers and rows.

        Args:
            lines: Consecutive lines formatted as a markdown table.

        Returns:
            Table dictionary with headers and rows, or None if invalid.
        """
        if len(lines) < 2:
            return None

        def split_row(row_str: str) -> list[str]:
            parts = row_str.strip().strip("|").split("|")
            return [p.strip() for p in parts]

        headers = split_row(lines[0])
        divider = lines[1].strip()
        if not re.search(r':?-+:?', divider):
            return None

        rows: list[list[str]] = []
        for line in lines[2:]:
            row = split_row(line)
            if len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            rows.append(row[:len(headers)])

        return {
            "type": "table",
            "headers": headers,
            "rows": rows,
            "text": "\n".join(lines),
        }

    def _parse_markdown(self, text: str) -> list[dict[str, Any]]:
        """Parses markdown text into structured blocks.

        Recognizes headings (H1-H4), code blocks, bullet lists, numbered lists,
        lettered option lists (A-D), blockquotes, horizontal dividers, tables,
        and paragraphs with inline formatting.

        Args:
            text: Full markdown-formatted text string.

        Returns:
            List of structured block dictionaries.
        """
        if not text:
            return []

        blocks: list[dict[str, Any]] = []
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 1. Blank line
            if not stripped:
                i += 1
                continue

            # 2. Fenced code block (```lang ... ```)
            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                code_lines: list[str] = []
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < n and lines[i].strip().startswith("```"):
                    i += 1  # Skip closing fence
                code_content = "\n".join(code_lines)
                blocks.append({
                    "type": "code",
                    "language": lang,
                    "content": code_content,
                    "text": code_content,
                })
                continue

            # 3. Headings (# H1 ... #### H4)
            heading_match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
            if heading_match:
                hashes, heading_text = heading_match.groups()
                level = min(len(hashes), 4)
                blocks.append({
                    "type": "heading",
                    "level": level,
                    "text": heading_text.strip(),
                    "raw": stripped,
                })
                i += 1
                continue

            # 4. Horizontal dividers (---, ***, ___)
            if re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', stripped):
                blocks.append({
                    "type": "divider",
                    "text": "---",
                })
                i += 1
                continue

            # 5. Blockquote (> ...)
            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while i < n and lines[i].strip().startswith(">"):
                    cleaned_q = re.sub(r'^>\s?', '', lines[i].strip())
                    quote_lines.append(cleaned_q)
                    i += 1
                blocks.append({
                    "type": "blockquote",
                    "text": " ".join(quote_lines),
                })
                continue

            # 6. Table (| col1 | col2 |)
            if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
                table_lines: list[str] = []
                while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                parsed_table = self._parse_table(table_lines)
                if parsed_table:
                    blocks.append(parsed_table)
                    continue

            # 7. Bullet list (* item, - item, + item)
            bullet_match = re.match(r'^[-*+]\s+(.*)$', stripped)
            if bullet_match:
                bullet_items: list[str] = []
                while i < n:
                    curr_str = lines[i].strip()
                    b_match = re.match(r'^[-*+]\s+(.*)$', curr_str)
                    if b_match:
                        bullet_items.append(b_match.group(1).strip())
                        i += 1
                    elif (
                        curr_str
                        and not curr_str.startswith(("#", "```", ">", "|", "---", "***"))
                        and not re.match(r'^\d+[\.\)]\s+', curr_str)
                        and not re.match(r'^\(?[A-Da-d]\)[\.\)]?\s+', curr_str)
                    ):
                        if bullet_items:
                            bullet_items[-1] += " " + curr_str
                        else:
                            bullet_items.append(curr_str)
                        i += 1
                    else:
                        break
                blocks.append({
                    "type": "bullet_list",
                    "items": bullet_items,
                })
                continue

            # 8. Numbered list (1. item, 2. item)
            num_match = re.match(r'^(\d+)[\.\)]\s+(.*)$', stripped)
            if num_match:
                numbered_items: list[tuple[str, str]] = []
                while i < n:
                    curr_str = lines[i].strip()
                    n_match = re.match(r'^(\d+)[\.\)]\s+(.*)$', curr_str)
                    if n_match:
                        num_str, item_text = n_match.groups()
                        numbered_items.append((num_str, item_text.strip()))
                        i += 1
                    elif (
                        curr_str
                        and not curr_str.startswith(("#", "```", ">", "|", "---", "***"))
                        and not re.match(r'^[-*+]\s+', curr_str)
                        and not re.match(r'^\(?[A-Da-d]\)[\.\)]?\s+', curr_str)
                    ):
                        if numbered_items:
                            prev_num, prev_text = numbered_items[-1]
                            numbered_items[-1] = (prev_num, prev_text + " " + curr_str)
                        else:
                            numbered_items.append(("1", curr_str))
                        i += 1
                    else:
                        break
                blocks.append({
                    "type": "numbered_list",
                    "items": numbered_items,
                })
                continue

            # 9. Lettered option list for question papers (A. / B. / (A) / (B))
            letter_match = re.match(r'^(\(?[A-Da-d]\)[\.\)]?|[A-Da-d]\.)\s+(.*)$', stripped)
            if letter_match:
                letter_items: list[tuple[str, str]] = []
                while i < n:
                    curr_str = lines[i].strip()
                    l_match = re.match(r'^(\(?[A-Da-d]\)[\.\)]?|[A-Da-d]\.)\s+(.*)$', curr_str)
                    if l_match:
                        lbl, item_text = l_match.groups()
                        clean_lbl = lbl.strip("().")
                        letter_items.append((clean_lbl.upper(), item_text.strip()))
                        i += 1
                    elif (
                        curr_str
                        and not curr_str.startswith(("#", "```", ">", "|", "---", "***"))
                        and not re.match(r'^[-*+]\s+', curr_str)
                        and not re.match(r'^\d+[\.\)]\s+', curr_str)
                    ):
                        if letter_items:
                            p_lbl, p_txt = letter_items[-1]
                            letter_items[-1] = (p_lbl, p_txt + " " + curr_str)
                        else:
                            letter_items.append(("A", curr_str))
                        i += 1
                    else:
                        break
                blocks.append({
                    "type": "lettered_list",
                    "items": letter_items,
                })
                continue

            # 10. Paragraph
            para_lines: list[str] = []
            while i < n:
                curr = lines[i]
                curr_s = curr.strip()
                if not curr_s:
                    break
                if curr_s.startswith(("#", "```", ">", "|", "---", "***", "___")):
                    break
                if re.match(r'^[-*+]\s+', curr_s) or re.match(r'^\d+[\.\)]\s+', curr_s) or re.match(r'^\(?[A-Da-d]\)[\.\)]?\s+', curr_s):
                    break
                para_lines.append(curr_s)
                i += 1

            if para_lines:
                para_text = " ".join(para_lines)
                blocks.append({
                    "type": "paragraph",
                    "text": para_text,
                    "html": self._markdown_to_html_inline(para_text),
                    "spans": self._parse_inline_spans(para_text),
                })

        return blocks

    def _add_cover_page(self, pdf: FPDF, title: str, subtitle: str) -> None:
        """Adds a professional academic cover page to the document.

        Args:
            pdf: FPDF document instance.
            title: Title of the document.
            subtitle: Subtitle (e.g., 'Study Material' or 'Question Paper').
        """
        # Disable running header & footer on cover page
        if hasattr(pdf, "enable_header_footer"):
            pdf.enable_header_footer = False

        pdf.add_page()

        clean_title = self._sanitize_text(title)
        clean_subtitle = self._sanitize_text(subtitle)

        # Top decorative banner (Navy Blue #1a237e with Indigo accent)
        pdf.set_fill_color(*COLOR_PRIMARY_DARK)
        pdf.rect(0, 0, pdf.w, 12, "F")
        pdf.set_fill_color(*COLOR_PRIMARY_LIGHT)
        pdf.rect(0, 12, pdf.w, 2.5, "F")

        # Application branding / header
        pdf.set_y(38)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*COLOR_PRIMARY_DARK)
        pdf.cell(0, 7, "STUDY BUDDY", align="C", ln=True)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT_MUTED)
        pdf.cell(0, 5, "AI-Powered Academic Learning System", align="C", ln=True)

        # Center accent divider
        pdf.ln(12)
        pdf.set_draw_color(*COLOR_PRIMARY_DARK)
        pdf.set_line_width(0.8)
        center_x = pdf.w / 2
        pdf.line(center_x - 25, pdf.get_y(), center_x + 25, pdf.get_y())
        pdf.ln(22)

        # Document Title
        pdf.set_font("Helvetica", "B", 24)
        pdf.set_text_color(*COLOR_PRIMARY_DARK)
        pdf.multi_cell(0, 11, clean_title, align="C")
        pdf.ln(8)

        # Subtitle
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*COLOR_PRIMARY_MID)
        pdf.cell(0, 8, clean_subtitle.upper(), align="C", ln=True)
        pdf.ln(15)

        # Metadata box near bottom
        box_y = 195.0
        box_w = pdf.w - 2 * pdf.l_margin
        box_h = 50.0

        pdf.set_y(box_y)
        pdf.set_fill_color(248, 249, 252)
        pdf.set_draw_color(215, 220, 235)
        pdf.set_line_width(0.4)
        pdf.rect(pdf.l_margin, box_y, box_w, box_h, "FD")

        # Colored accent stripe on left border of metadata box
        pdf.set_fill_color(*COLOR_PRIMARY_DARK)
        pdf.rect(pdf.l_margin, box_y, 4, box_h, "F")

        # Metadata items inside box
        now_date = datetime.now().strftime("%B %d, %Y")
        meta_x = pdf.l_margin + 10
        curr_y = box_y + 8

        metadata_rows = [
            ("Document Type", clean_subtitle),
            ("Subject / Topic", clean_title[:45] + ("..." if len(clean_title) > 45 else "")),
            ("Generation Date", now_date),
            ("Platform", "Study Buddy Academic Engine"),
        ]

        for label, val in metadata_rows:
            pdf.set_xy(meta_x, curr_y)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(80, 80, 90)
            pdf.cell(32, 6, f"{label}:", align="L")

            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*COLOR_TEXT_MAIN)
            pdf.cell(0, 6, val, align="L")
            curr_y += 8.5

        # Bottom accent footer
        pdf.set_fill_color(*COLOR_PRIMARY_DARK)
        pdf.rect(0, pdf.h - 5, pdf.w, 5, "F")

    def _add_header_footer(self, pdf: FPDF, title: str) -> None:
        """Configures running header and footer for the PDF document.

        Args:
            pdf: FPDF document instance.
            title: Title to display in page header.
        """
        pdf.doc_title = self._sanitize_text(title)
        pdf.enable_header_footer = True
        try:
            pdf.alias_nb_pages()
        except Exception:
            pass

        # If pdf is a standard FPDF instance (not StudyBuddyPDF), dynamically bind methods
        if not isinstance(pdf, StudyBuddyPDF):
            import types

            def dynamic_header(p_self: Any) -> None:
                if not getattr(p_self, "enable_header_footer", False):
                    return
                p_self.set_y(8)
                p_self.set_font("Helvetica", "I", 8)
                p_self.set_text_color(110, 110, 120)
                clean_t = getattr(p_self, "doc_title", "")
                if len(clean_t) > 65:
                    clean_t = clean_t[:62] + "..."
                p_self.cell(0, 6, clean_t, align="L")
                p_self.set_draw_color(*COLOR_RULE)
                p_self.set_line_width(0.3)
                p_self.line(p_self.l_margin, 15, p_self.w - p_self.r_margin, 15)
                p_self.ln(9)

            def dynamic_footer(p_self: Any) -> None:
                if not getattr(p_self, "enable_header_footer", False):
                    return
                p_self.set_y(-15)
                p_self.set_draw_color(*COLOR_RULE)
                p_self.set_line_width(0.3)
                p_self.line(p_self.l_margin, p_self.get_y(), p_self.w - p_self.r_margin, p_self.get_y())
                p_self.set_font("Helvetica", "I", 8)
                p_self.set_text_color(*COLOR_TEXT_MUTED)
                p_self.cell(0, 10, "Study Buddy  *  AI Academic Learning Platform", align="L")
                p_self.set_x(p_self.w - p_self.r_margin - 35)
                p_self.cell(35, 10, f"Page {p_self.page_no()}/{{nb}}", align="R")

            pdf.header = types.MethodType(dynamic_header, pdf)
            pdf.footer = types.MethodType(dynamic_footer, pdf)

    def _add_table_of_contents(self, pdf: FPDF, sections: list[dict[str, Any]]) -> None:
        """Adds a clean Table of Contents page.

        Args:
            pdf: FPDF document instance.
            sections: List of heading block dictionaries.
        """
        pdf.add_page()
        pdf.set_y(22)

        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*COLOR_PRIMARY_DARK)
        pdf.cell(0, 9, "Table of Contents", ln=True)

        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*COLOR_TEXT_MUTED)
        pdf.cell(0, 5, "Structured overview of topics and sections in this document", ln=True)
        pdf.ln(3)

        # Divider line
        pdf.set_draw_color(*COLOR_PRIMARY_DARK)
        pdf.set_line_width(0.6)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(8)

        h1_index = 1
        for sec in sections:
            level = sec.get("level", 1)
            raw_text = sec.get("text", "")
            clean_sec = self._sanitize_text(raw_text)

            if level == 1:
                pdf.set_font("Helvetica", "B", 10.5)
                pdf.set_text_color(*COLOR_PRIMARY_DARK)
                prefix = f"{h1_index}.  "
                h1_index += 1
                indent = 0.0
                line_h = 7.0
            elif level == 2:
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(50, 50, 50)
                prefix = "    -  "
                indent = 5.0
                line_h = 6.0
            else:
                pdf.set_font("Helvetica", "I", 8.5)
                pdf.set_text_color(90, 90, 90)
                prefix = "        *  "
                indent = 10.0
                line_h = 5.5

            if pdf.get_y() > pdf.h - pdf.b_margin - 15:
                pdf.add_page()

            pdf.set_x(pdf.l_margin + indent)
            pdf.cell(0, line_h, f"{prefix}{clean_sec}", ln=True)

        pdf.ln(8)

    def _render_styled_text(
        self,
        pdf: FPDF,
        text: str,
        width: float,
        line_height: float = 5.5,
    ) -> None:
        """Renders text supporting inline bold, italic, and monospace code.

        Falls back gracefully to plain text if HTML rendering encounters issues.

        Args:
            pdf: FPDF document instance.
            text: Text to render with possible inline markdown tokens.
            width: Maximum cell width.
            line_height: Height of text lines.
        """
        clean_text = self._sanitize_text(text)
        has_bold = "**" in clean_text or "__" in clean_text
        has_italic = "*" in clean_text or "_" in clean_text
        has_code = "`" in clean_text

        # If no inline styling is present, render directly with multi_cell
        if not (has_bold or has_italic or has_code):
            pdf.multi_cell(width, line_height, clean_text)
            return

        # Attempt HTML rendering for bold/italic/code
        try:
            html_text = self._markdown_to_html_inline(clean_text)
            pdf.write_html(html_text)
            pdf.ln(line_height * 0.4)
        except Exception:
            # Fallback: strip markdown syntax and print clean text
            stripped = self._strip_markdown_inline(clean_text)
            pdf.multi_cell(width, line_height, stripped)

    def _is_answer_section_heading(self, block: dict[str, Any]) -> bool:
        """Checks if a block represents the start of the Answer Key section.

        Args:
            block: Markdown block dictionary.

        Returns:
            True if block is an answers/solutions heading.
        """
        if block.get("type") == "heading":
            raw_text = block.get("text", "").upper().strip()
            keywords = ["ANSWER", "ANSWERS", "ANSWER KEY", "SOLUTIONS", "SOLUTION", "ANSWERS AND EXPLANATIONS"]
            for kw in keywords:
                if kw in raw_text:
                    return True
        return False

    def _render_heading(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders heading block with proper styling and spacing.

        Args:
            pdf: FPDF document instance.
            block: Heading block dictionary.
        """
        level = block.get("level", 1)
        text = self._sanitize_text(block.get("text", ""))

        if level == 1:
            # Prevent orphan heading
            if pdf.get_y() > pdf.h - pdf.b_margin - 30:
                pdf.add_page()
            else:
                pdf.ln(6)

            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(*COLOR_PRIMARY_DARK)
            pdf.multi_cell(0, 8, text)

            # Accent underline
            y = pdf.get_y() + 1
            pdf.set_draw_color(*COLOR_PRIMARY_DARK)
            pdf.set_line_width(0.7)
            pdf.line(pdf.l_margin, y, pdf.l_margin + 40, y)
            pdf.set_draw_color(*COLOR_RULE)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin + 40, y, pdf.w - pdf.r_margin, y)
            pdf.ln(5)

        elif level == 2:
            if pdf.get_y() > pdf.h - pdf.b_margin - 24:
                pdf.add_page()
            else:
                pdf.ln(5)

            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*COLOR_PRIMARY_MID)
            pdf.multi_cell(0, 7, text)
            pdf.ln(3)

        elif level == 3:
            if pdf.get_y() > pdf.h - pdf.b_margin - 18:
                pdf.add_page()
            else:
                pdf.ln(4)

            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*COLOR_PRIMARY_LIGHT)
            pdf.multi_cell(0, 6, text)
            pdf.ln(2)

        else:
            if pdf.get_y() > pdf.h - pdf.b_margin - 15:
                pdf.add_page()
            else:
                pdf.ln(3)

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*COLOR_PRIMARY_DARK)
            pdf.multi_cell(0, 5.5, text)
            pdf.ln(2)

    def _render_code_block(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders monospace code block with shaded background.

        Args:
            pdf: FPDF document instance.
            block: Code block dictionary.
        """
        code_content = block.get("content", "")
        lang = block.get("language", "").strip().upper()
        lines = code_content.split("\n")
        line_height = 4.8
        content_width = pdf.w - pdf.l_margin - pdf.r_margin

        # Check if block fits or requires page break
        approx_height = len(lines) * line_height + 10
        if pdf.get_y() + approx_height > pdf.h - pdf.b_margin and approx_height < 140:
            pdf.add_page()
        else:
            pdf.ln(2)

        # Code header badge if language is specified
        if lang:
            pdf.set_fill_color(230, 233, 240)
            pdf.set_font("Helvetica", "B", 7.5)
            pdf.set_text_color(*COLOR_PRIMARY_DARK)
            pdf.cell(content_width, 5.0, f"  CODE [{lang}]", fill=True, border=1, ln=True)

        pdf.set_font("Courier", "", 8.5)
        pdf.set_fill_color(*COLOR_CODE_BG)
        pdf.set_text_color(40, 44, 52)
        pdf.set_draw_color(*COLOR_CODE_BORDER)

        for line in lines:
            clean_l = self._sanitize_text(line)
            # Wrap long code lines so they never exceed margins
            sub_lines = textwrap.wrap(clean_l, width=80) if len(clean_l) > 82 else [clean_l]
            for sub_idx, sub_l in enumerate(sub_lines):
                if pdf.get_y() > pdf.h - pdf.b_margin - 8:
                    pdf.add_page()
                    pdf.set_font("Courier", "", 8.5)
                    pdf.set_fill_color(*COLOR_CODE_BG)
                    pdf.set_text_color(40, 44, 52)
                prefix = "  " if sub_idx == 0 else "    > "
                pdf.cell(content_width, line_height, f"{prefix}{sub_l}", fill=True, border="LR", ln=True)

        # Bottom border line
        pdf.cell(content_width, 1.5, "", fill=True, border="LRB", ln=True)
        pdf.ln(3)

    def _render_blockquote(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders styled callout blockquote with vertical accent bar.

        Args:
            pdf: FPDF document instance.
            block: Blockquote dictionary.
        """
        quote_text = self._sanitize_text(block.get("text", ""))
        indent = 5.0

        if pdf.get_y() > pdf.h - pdf.b_margin - 18:
            pdf.add_page()
        else:
            pdf.ln(2)

        start_x = pdf.l_margin
        start_y = pdf.get_y()

        old_margin = pdf.l_margin
        pdf.set_left_margin(old_margin + indent)
        pdf.set_xy(old_margin + indent, start_y)

        pdf.set_font("Helvetica", "I", 9.5)
        pdf.set_text_color(45, 55, 72)
        pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin, 5.5, quote_text, fill=False)
        end_y = pdf.get_y()
        pdf.set_left_margin(old_margin)

        # Vertical accent line on left edge
        pdf.set_draw_color(*COLOR_PRIMARY_DARK)
        pdf.set_line_width(0.8)
        pdf.line(start_x, start_y, start_x, end_y)
        pdf.set_line_width(0.2)
        pdf.ln(3)

    def _render_bullet_list(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders bullet list with indented hanging items.

        Args:
            pdf: FPDF document instance.
            block: Bullet list dictionary.
        """
        indent = 6.0
        old_margin = pdf.l_margin

        for item in block.get("items", []):
            if pdf.get_y() > pdf.h - pdf.b_margin - 12:
                pdf.add_page()

            y = pdf.get_y()
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*COLOR_PRIMARY_DARK)
            pdf.set_xy(old_margin, y)
            pdf.cell(indent, 5.5, "-", align="L")

            pdf.set_left_margin(old_margin + indent)
            pdf.set_xy(old_margin + indent, y)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*COLOR_TEXT_MAIN)
            self._render_styled_text(pdf, item, pdf.w - pdf.l_margin - pdf.r_margin, line_height=5.5)
            pdf.set_left_margin(old_margin)
            pdf.ln(1.5)

        pdf.ln(2.0)

    def _render_numbered_list(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders numbered list with proper hanging indentation.

        Args:
            pdf: FPDF document instance.
            block: Numbered list dictionary.
        """
        indent = 8.0
        old_margin = pdf.l_margin

        for num_label, item in block.get("items", []):
            if pdf.get_y() > pdf.h - pdf.b_margin - 12:
                pdf.add_page()

            y = pdf.get_y()
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*COLOR_PRIMARY_DARK)
            pdf.set_xy(old_margin, y)
            pdf.cell(indent, 5.5, f"{num_label}.", align="L")

            pdf.set_left_margin(old_margin + indent)
            pdf.set_xy(old_margin + indent, y)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*COLOR_TEXT_MAIN)
            self._render_styled_text(pdf, item, pdf.w - pdf.l_margin - pdf.r_margin, line_height=5.5)
            pdf.set_left_margin(old_margin)
            pdf.ln(1.5)

        pdf.ln(2.0)

    def _render_lettered_list(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders lettered option list (A, B, C, D) for question papers.

        Args:
            pdf: FPDF document instance.
            block: Lettered list dictionary.
        """
        indent = 7.0
        old_margin = pdf.l_margin

        for letter_lbl, item in block.get("items", []):
            if pdf.get_y() > pdf.h - pdf.b_margin - 10:
                pdf.add_page()

            y = pdf.get_y()
            pdf.set_font("Helvetica", "B", 9.0)
            pdf.set_text_color(*COLOR_PRIMARY_MID)
            pdf.set_xy(old_margin + 3.0, y)
            pdf.cell(indent, 5.0, f"({letter_lbl})", align="L")

            pdf.set_left_margin(old_margin + 3.0 + indent)
            pdf.set_xy(old_margin + 3.0 + indent, y)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(*COLOR_TEXT_MAIN)
            self._render_styled_text(pdf, item, pdf.w - pdf.l_margin - pdf.r_margin, line_height=5.0)
            pdf.set_left_margin(old_margin)
            pdf.ln(1.2)

        pdf.ln(1.8)

    def _render_table(self, pdf: FPDF, block: dict[str, Any]) -> None:
        """Renders structured table with styled headers and alternating row colors.

        Args:
            pdf: FPDF document instance.
            block: Table dictionary with headers and rows.
        """
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        if not headers:
            return

        content_width = pdf.w - pdf.l_margin - pdf.r_margin
        col_width = content_width / len(headers)

        if pdf.get_y() > pdf.h - pdf.b_margin - 20:
            pdf.add_page()
        else:
            pdf.ln(2)

        # Header Row
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(*COLOR_PRIMARY_DARK)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(*COLOR_RULE)

        for h in headers:
            clean_h = self._sanitize_text(h)
            pdf.cell(col_width, 7.0, f" {clean_h}", border=1, fill=True, align="L")
        pdf.ln()

        # Data Rows
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*COLOR_TEXT_MAIN)

        for r_idx, row in enumerate(rows):
            if pdf.get_y() > pdf.h - pdf.b_margin - 12:
                pdf.add_page()
                # Repeat header on new page
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_fill_color(*COLOR_PRIMARY_DARK)
                pdf.set_text_color(255, 255, 255)
                for h in headers:
                    clean_h = self._sanitize_text(h)
                    pdf.cell(col_width, 7.0, f" {clean_h}", border=1, fill=True, align="L")
                pdf.ln()
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(*COLOR_TEXT_MAIN)

            # Alternating row fill
            if r_idx % 2 == 0:
                pdf.set_fill_color(255, 255, 255)
            else:
                pdf.set_fill_color(248, 249, 251)

            for cell_val in row:
                clean_val = self._sanitize_text(cell_val)
                pdf.cell(col_width, 6.0, f" {clean_val}", border=1, fill=True, align="L")
            pdf.ln()

        pdf.ln(3)

    def _render_content(
        self,
        pdf: FPDF,
        blocks: list[dict[str, Any]],
        is_question_paper: bool = False,
    ) -> None:
        """Renders structured markdown blocks onto content pages.

        Args:
            pdf: FPDF document instance.
            blocks: List of structured block dictionaries.
            is_question_paper: True if document is a question paper.
        """
        content_width = pdf.w - pdf.l_margin - pdf.r_margin
        answer_key_started = False

        for block in blocks:
            b_type = block.get("type")

            # Check for Answer Key transition in question paper
            if is_question_paper and not answer_key_started and self._is_answer_section_heading(block):
                pdf.add_page()
                answer_key_started = True

                # Highlighted Answer Key Section Header
                pdf.set_fill_color(240, 244, 255)
                pdf.set_draw_color(*COLOR_PRIMARY_DARK)
                pdf.set_line_width(0.6)
                pdf.rect(pdf.l_margin, pdf.get_y(), content_width, 10, "FD")
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(*COLOR_PRIMARY_DARK)
                pdf.set_xy(pdf.l_margin + 4, pdf.get_y() + 1.5)
                pdf.cell(0, 7, "ANSWER KEY & DETAILED EXPLANATIONS", ln=True)
                pdf.ln(5)
                continue

            if b_type == "heading":
                self._render_heading(pdf, block)
            elif b_type == "code":
                self._render_code_block(pdf, block)
            elif b_type == "blockquote":
                self._render_blockquote(pdf, block)
            elif b_type == "bullet_list":
                self._render_bullet_list(pdf, block)
            elif b_type == "numbered_list":
                self._render_numbered_list(pdf, block)
            elif b_type == "lettered_list":
                self._render_lettered_list(pdf, block)
            elif b_type == "table":
                self._render_table(pdf, block)
            elif b_type == "divider":
                pdf.ln(2)
                pdf.set_draw_color(*COLOR_RULE)
                pdf.set_line_width(0.3)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(4)
            elif b_type == "paragraph":
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*COLOR_TEXT_MAIN)
                self._render_styled_text(pdf, block.get("text", ""), content_width, line_height=5.5)
                pdf.ln(3)

    def generate_study_material(
        self,
        content: str,
        title: str,
        output_path: str,
    ) -> str:
        """Generates a professional study material PDF from LLM-generated content.

        Document structure:
        - Cover page with title, 'Study Material' subtitle, generation date
        - Table of contents (if multiple sections detected)
        - Content pages with formatted headings, code blocks, lists, and callouts
        - Running headers and page numbers in footer

        Args:
            content: Markdown-formatted text content.
            title: Document title.
            output_path: Target PDF file path or directory.

        Returns:
            Absolute path to the generated PDF document.

        Raises:
            PermissionError: If write permission is denied.
            OSError: If output directory or file cannot be written.
        """
        resolved_path = self._resolve_output_path(output_path, title or "Study_Material")

        # Initialize PDF instance
        pdf = StudyBuddyPDF(
            doc_title=title,
            doc_subtitle="Study Material",
            is_question_paper=False,
            orientation="P",
            unit="mm",
            format="A4",
        )
        pdf.set_margins(left=18, top=20, right=18)
        pdf.set_auto_page_break(auto=True, margin=20)

        # 1. Cover Page
        self._add_cover_page(pdf, title=title, subtitle="Study Material")

        # 2. Configure running header and footer for content pages
        self._add_header_footer(pdf, title=title)

        # 3. Parse Markdown
        blocks = self._parse_markdown(content)

        # 4. Table of Contents if multiple sections (h1 or h2) detected
        sections = [b for b in blocks if b.get("type") == "heading" and b.get("level", 1) in (1, 2)]
        if len(sections) >= 2:
            self._add_table_of_contents(pdf, sections)

        # 5. Content starts on fresh page
        pdf.add_page()

        # 6. Render Main Content
        self._render_content(pdf, blocks, is_question_paper=False)

        # 7. Save to Disk
        try:
            pdf.output(resolved_path)
            logger.info("Successfully generated Study Material PDF at: %s", resolved_path)
        except PermissionError as e:
            logger.error("Permission denied writing PDF to '%s': %s", resolved_path, e)
            raise PermissionError(f"Permission denied when writing PDF to '{resolved_path}': {e}") from e
        except OSError as e:
            logger.error("OS error writing PDF to '%s': %s", resolved_path, e)
            raise OSError(f"Failed to write PDF to '{resolved_path}': {e}") from e

        return resolved_path

    def generate_question_paper(
        self,
        content: str,
        title: str,
        output_path: str,
    ) -> str:
        """Generates a question paper PDF from LLM-generated content.

        Document structure:
        - Cover page with title, 'Question Paper' subtitle, generation date
        - Questions section with numbered questions
        - Answer key section (placed cleanly on a new page)
        - Running headers and page numbers in footer

        Args:
            content: Markdown-formatted text content with questions and answers.
            title: Document title.
            output_path: Target PDF file path or directory.

        Returns:
            Absolute path to the generated PDF document.

        Raises:
            PermissionError: If write permission is denied.
            OSError: If output directory or file cannot be written.
        """
        resolved_path = self._resolve_output_path(output_path, title or "Question_Paper")

        # Initialize PDF instance
        pdf = StudyBuddyPDF(
            doc_title=title,
            doc_subtitle="Question Paper",
            is_question_paper=True,
            orientation="P",
            unit="mm",
            format="A4",
        )
        pdf.set_margins(left=18, top=20, right=18)
        pdf.set_auto_page_break(auto=True, margin=20)

        # 1. Cover Page
        self._add_cover_page(pdf, title=title, subtitle="Question Paper")

        # 2. Configure running header and footer for content pages
        self._add_header_footer(pdf, title=title)

        # 3. Parse Markdown
        blocks = self._parse_markdown(content)

        # 4. Content starts on fresh page
        pdf.add_page()

        # 5. Render Questions and Answer Key
        self._render_content(pdf, blocks, is_question_paper=True)

        # 6. Save to Disk
        try:
            pdf.output(resolved_path)
            logger.info("Successfully generated Question Paper PDF at: %s", resolved_path)
        except PermissionError as e:
            logger.error("Permission denied writing PDF to '%s': %s", resolved_path, e)
            raise PermissionError(f"Permission denied when writing PDF to '{resolved_path}': {e}") from e
        except OSError as e:
            logger.error("OS error writing PDF to '%s': %s", resolved_path, e)
            raise OSError(f"Failed to write PDF to '{resolved_path}': {e}") from e

        return resolved_path


def get_study_material_prompt(user_input: str = None) -> str:
    """Returns the system prompt for study material generation."""
    base = "You are a wise academician on the given source field and you want to teach the contents of the source to students through a PDF which contains the contents of the source. You summarize the theories behind those topics and build intuition on them and also give example real world scenarios and question-answers."
    if user_input:
        return base + f" Focus specifically on: {user_input}. Format your response in well-structured markdown with clear headings, subheadings, bullet points, and sections."
    return base + " Cover all major topics comprehensively. Format your response in well-structured markdown with clear headings, subheadings, bullet points, and sections."


def get_question_paper_prompt(user_input: str = None) -> str:
    """Returns the system prompt for question paper generation."""
    base = "You are a wise academician on the given source field and you want to assess students by creating a question paper with 10 important questions from each topic. You will also provide properly structured answers to the given questions."
    if user_input:
        return base + f" Focus specifically on: {user_input}. Format with clear 'QUESTIONS' and 'ANSWERS' sections. Number all questions."
    return base + " Cover all major topics. Format with clear 'QUESTIONS' and 'ANSWERS' sections. Number all questions."
