"""File processor for Study Buddy RAG application.

Extracts text from multiple document formats (.pdf, .docx, .epub, .rtf, .html,
code files, markdown, csv, json, xml, txt, log) and performs text chunking
with paragraph/sentence boundary preservation for vector storage and RAG.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import chardet
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Supported code extensions and their language names
CODE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
}

SUPPORTED_EXTENSIONS: set[str] = {
    ".txt",
    ".pdf",
    ".html",
    ".htm",
    ".json",
    ".md",
    ".markdown",
    ".csv",
    ".docx",
    ".rtf",
    ".epub",
    ".xml",
    ".log",
    *CODE_EXTENSIONS.keys(),
}


class FileProcessor:
    """Extracts text from documents and chunks content for RAG retrieval."""

    def __init__(self) -> None:
        """Initialize FileProcessor."""
        pass

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        """Return a sorted list of supported file extensions (with leading dot)."""
        return sorted(list(SUPPORTED_EXTENSIONS))

    def process_file(self, file_path: str | Path) -> str:
        """Extract text from the specified file path based on its extension.

        Args:
            file_path: Path to the target file.

        Returns:
            Extracted clean plain text string.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file type is unsupported or corrupted.
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        ext = path.suffix.lower()

        if ext == ".txt" or ext == ".log":
            return self._extract_plain_text(path)
        elif ext in (".md", ".markdown"):
            return self._extract_plain_text(path)
        elif ext == ".pdf":
            return self._extract_pdf(path)
        elif ext in (".html", ".htm"):
            return self._extract_html(path)
        elif ext == ".json":
            return self._extract_json(path)
        elif ext == ".csv":
            return self._extract_csv(path)
        elif ext == ".docx":
            return self._extract_docx(path)
        elif ext == ".rtf":
            return self._extract_rtf(path)
        elif ext == ".epub":
            return self._extract_epub(path)
        elif ext == ".xml":
            return self._extract_xml(path)
        elif ext in CODE_EXTENSIONS:
            return self._extract_code(path, ext)
        else:
            # Fallback attempt as plain text if text-like
            try:
                return self._extract_plain_text(path)
            except Exception as e:
                raise ValueError(
                    f"Unsupported or unreadable file extension: {ext} ({path.name}). Error: {e}"
                )

    def process_uploaded_file(
        self, file_storage: Any, save_dir: str | Path
    ) -> tuple[str, str]:
        """Save a Flask/Werkzeug uploaded file and extract its text content.

        Args:
            file_storage: Werkzeug FileStorage object from request.files.
            save_dir: Directory path where the file should be saved.

        Returns:
            A tuple of (saved_file_absolute_path, extracted_text).
        """
        save_path_dir = Path(save_dir).resolve()
        save_path_dir.mkdir(parents=True, exist_ok=True)

        original_filename = getattr(file_storage, "filename", "") or "uploaded_file"
        # Sanitize filename
        safe_filename = self._sanitize_filename(original_filename)

        # Ensure unique filename to prevent collision
        target_path = save_path_dir / safe_filename
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            unique_name = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
            target_path = save_path_dir / unique_name

        file_storage.save(str(target_path))
        logger.info(f"Saved uploaded file to {target_path}")

        extracted_text = self.process_file(target_path)
        return str(target_path), extracted_text

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize a filename for safe disk storage."""
        # Strip directory components
        base = os.path.basename(filename)
        # Remove characters that are problematic across OSes
        cleaned = re.sub(r'[\\/*?:"<>|]', "", base).strip()
        return cleaned or f"file_{uuid.uuid4().hex[:8]}"

    def _read_bytes_with_charset(self, path: Path) -> str:
        """Read text from binary file with automatic charset detection."""
        with open(path, "rb") as f:
            raw_bytes = f.read()

        if not raw_bytes:
            return ""

        # Charset detection
        detection = chardet.detect(raw_bytes)
        encoding = detection.get("encoding")

        candidates = [encoding, "utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
        for enc in candidates:
            if not enc:
                continue
            try:
                return raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

        return raw_bytes.decode("utf-8", errors="replace")

    def _extract_plain_text(self, path: Path) -> str:
        """Extract text from plain text and markdown files."""
        return self._read_bytes_with_charset(path).strip()

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from PDF using pdfplumber with PyPDF2 fallback."""
        extracted_pages: list[str] = []
        pdfplumber_error: Exception | None = None

        # Primary extractor: pdfplumber
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        extracted_pages.append(f"--- Page {idx} ---\n{page_text.strip()}")
            if extracted_pages:
                return "\n\n".join(extracted_pages)
        except Exception as e:
            pdfplumber_error = e
            logger.warning(
                f"pdfplumber failed for {path.name}: {e}. Attempting PyPDF2 fallback."
            )

        # Fallback extractor: PyPDF2 / pypdf
        try:
            try:
                import pypdf as pdf_module
            except ImportError:
                import PyPDF2 as pdf_module  # type: ignore

            reader = pdf_module.PdfReader(str(path))
            for idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    extracted_pages.append(f"--- Page {idx} ---\n{page_text.strip()}")
            if extracted_pages:
                return "\n\n".join(extracted_pages)
        except Exception as e_pypdf:
            logger.error(f"PyPDF2 fallback also failed for {path.name}: {e_pypdf}")
            if pdfplumber_error:
                raise RuntimeError(
                    f"Failed to extract PDF content with pdfplumber ({pdfplumber_error}) "
                    f"and PyPDF2 ({e_pypdf})"
                )
            raise

        return ""

    def _extract_html(self, path: Path) -> str:
        """Extract plain text from HTML files, stripping scripts and tags."""
        raw_html = self._read_bytes_with_charset(path)
        if not raw_html.strip():
            return ""

        soup = BeautifulSoup(raw_html, "html.parser")
        # Remove invisible and non-content elements
        for element in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive newlines
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _extract_json(self, path: Path) -> str:
        """Pretty-print JSON content as formatted text."""
        raw = self._read_bytes_with_charset(path)
        if not raw.strip():
            return ""
        try:
            data = json.loads(raw)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            return raw.strip()

    def _extract_csv(self, path: Path) -> str:
        """Read CSV file and format as readable tabular text."""
        raw = self._read_bytes_with_charset(path)
        if not raw.strip():
            return ""

        reader = csv.reader(io.StringIO(raw))
        lines: list[str] = []
        for row in reader:
            if any(cell.strip() for cell in row):
                lines.append(" | ".join(cell.strip() for cell in row))

        return "\n".join(lines).strip()

    def _extract_docx(self, path: Path) -> str:
        """Extract text from Word .docx file using python-docx."""
        import docx

        doc = docx.Document(str(path))
        sections: list[str] = []

        # Paragraph text
        for p in doc.paragraphs:
            if p.text.strip():
                sections.append(p.text.strip())

        # Table text
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    sections.append(" | ".join(cells))

        return "\n\n".join(sections).strip()

    def _extract_rtf(self, path: Path) -> str:
        """Extract plain text from RTF file using striprtf."""
        from striprtf.striprtf import rtf_to_text

        raw_rtf = self._read_bytes_with_charset(path)
        if not raw_rtf.strip():
            return ""
        return rtf_to_text(raw_rtf).strip()

    def _extract_epub(self, path: Path) -> str:
        """Extract text from EPUB book using ebooklib."""
        import ebooklib
        from ebooklib import epub

        book = epub.read_epub(str(path))
        sections: list[str] = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content()
                soup = BeautifulSoup(content, "html.parser")
                for element in soup(["script", "style"]):
                    element.decompose()
                text = soup.get_text(separator="\n", strip=True)
                if text:
                    sections.append(text)

        return "\n\n".join(sections).strip()

    def _extract_xml(self, path: Path) -> str:
        """Extract plain text content from XML using BeautifulSoup."""
        raw = self._read_bytes_with_charset(path)
        if not raw.strip():
            return ""

        try:
            soup = BeautifulSoup(raw, "xml")
        except Exception:
            soup = BeautifulSoup(raw, "html.parser")

        text = soup.get_text(separator="\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _extract_code(self, path: Path, ext: str) -> str:
        """Format code file with language annotation."""
        raw_code = self._read_bytes_with_charset(path)
        lang = CODE_EXTENSIONS.get(ext, ext.lstrip("."))
        return f"# File: {path.name} (Language: {lang})\n```{lang}\n{raw_code}\n```"

    def chunk_text(
        self, text: str, chunk_size: int = 1000, overlap: int = 200
    ) -> list[str]:
        """Split text into overlapping chunks for RAG.

        Splits along paragraph, newline, and sentence boundaries where possible
        while respecting chunk_size and overlap constraints.

        Args:
            text: Input text string.
            chunk_size: Target maximum chunk size in characters (default: 1000).
            overlap: Target overlapping characters between consecutive chunks
                (default: 200).

        Returns:
            List of text chunk strings.
        """
        if not text or not text.strip():
            return []

        clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(clean_text) <= chunk_size:
            return [clean_text]

        # Enforce valid overlap
        if overlap >= chunk_size:
            overlap = max(0, chunk_size // 4)

        # Break text down into atomic building blocks:
        # 1. Paragraphs (\n\n+)
        # 2. Lines (\n)
        # 3. Sentences ([.?!]\s+)
        # 4. Words
        segments = self._split_into_atomic_segments(clean_text, max_atomic_len=chunk_size // 2)

        chunks: list[str] = []
        current_chunk_segments: list[str] = []
        current_length = 0

        for seg in segments:
            seg_len = len(seg)
            # If adding this segment exceeds chunk_size and we already have content
            if current_length + seg_len > chunk_size and current_chunk_segments:
                chunk_str = "".join(current_chunk_segments).strip()
                if chunk_str:
                    chunks.append(chunk_str)

                # Find overlap segments from the end of current_chunk_segments
                overlap_segments: list[str] = []
                overlap_len = 0
                for prev_seg in reversed(current_chunk_segments):
                    if overlap_len + len(prev_seg) <= overlap or not overlap_segments:
                        overlap_segments.insert(0, prev_seg)
                        overlap_len += len(prev_seg)
                    else:
                        break

                current_chunk_segments = list(overlap_segments)
                current_length = sum(len(s) for s in current_chunk_segments)

            # If a single segment is itself larger than chunk_size, hard-split it
            if seg_len > chunk_size:
                start = 0
                step = chunk_size - overlap
                while start < seg_len:
                    part = seg[start : start + chunk_size].strip()
                    if part:
                        chunks.append(part)
                    start += step
                current_chunk_segments = []
                current_length = 0
            else:
                current_chunk_segments.append(seg)
                current_length += seg_len

        # Append remaining segments
        if current_chunk_segments:
            final_chunk = "".join(current_chunk_segments).strip()
            if final_chunk and (not chunks or final_chunk != chunks[-1]):
                chunks.append(final_chunk)

        return chunks

    def _split_into_atomic_segments(self, text: str, max_atomic_len: int) -> list[str]:
        """Split text hierarchically into segments preserving spaces/newlines."""
        # Split on paragraph boundaries first
        raw_paras = re.split(r"(\n\n+)", text)
        segments: list[str] = []

        for p in raw_paras:
            if not p:
                continue
            if len(p) <= max_atomic_len or "\n\n" in p:
                segments.append(p)
            else:
                # Split paragraph by sentence boundaries
                sentence_parts = re.split(r"((?<=[.?!])\s+)", p)
                for sp in sentence_parts:
                    if not sp:
                        continue
                    if len(sp) <= max_atomic_len:
                        segments.append(sp)
                    else:
                        # Split by whitespace/words
                        words = re.split(r"(\s+)", sp)
                        for w in words:
                            if w:
                                segments.append(w)

        return segments


# Global default instance
file_processor = FileProcessor()
