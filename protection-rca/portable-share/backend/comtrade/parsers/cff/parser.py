"""CFF (single-file COMTRADE) unpacker and parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from comtrade._io import FilePath, read_bytes, sniff_text


_SECTION_RE = re.compile(
    r"^---\s*file\s*type:\s*(.+?)\s*---\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class CffSections:
    """Logical sections extracted from a CFF file."""

    cfg_text: str = ""
    dat_text: Optional[str] = None
    dat_binary: Optional[bytes] = None
    dat_format_hint: str = "ASCII"  # from section header
    hdr_text: str = ""
    inf_text: str = ""
    warnings: list[str] = field(default_factory=list)


class CffUnpacker:
    """Unpack a CFF into logical CFG / DAT / HDR / INF sections.

    Binary DAT sections are returned as raw bytes (content after the section
    header until the next section or EOF). ASCII DAT is returned as text.
    """

    def unpack_text(self, text: str, raw: Optional[bytes] = None) -> CffSections:
        sections = CffSections()
        matches = list(_SECTION_RE.finditer(text))
        if not matches:
            sections.warnings.append("no CFF section markers found")
            # Treat entire file as CFG if it looks like one
            sections.cfg_text = text
            return sections

        for i, match in enumerate(matches):
            label = match.group(1).strip().upper()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].lstrip("\r\n")

            if label.startswith("CFG"):
                sections.cfg_text = body.strip()
            elif label.startswith("HDR"):
                sections.hdr_text = body.strip()
            elif label.startswith("INF"):
                sections.inf_text = body.strip()
            elif label.startswith("DAT"):
                # Determine format from label
                if "BINARY32" in label:
                    sections.dat_format_hint = "BINARY32"
                elif "FLOAT32" in label:
                    sections.dat_format_hint = "FLOAT32"
                elif "BINARY" in label:
                    sections.dat_format_hint = "BINARY"
                else:
                    sections.dat_format_hint = "ASCII"

                if sections.dat_format_hint == "ASCII":
                    sections.dat_text = body
                else:
                    # Prefer slicing original bytes after the header line
                    if raw is not None:
                        # Find header in bytes (ASCII markers)
                        header_bytes = match.group(0).encode("ascii", errors="ignore")
                        # Re-search in raw for robustness
                        raw_upper = raw.upper()
                        key = b"--- FILE TYPE:"
                        # Use text offsets only if file is fully textual; for mixed
                        # binary CFF, locate section by scanning markers in bytes.
                        bin_body = self._extract_binary_section(raw, label)
                        if bin_body is not None:
                            sections.dat_binary = bin_body
                        else:
                            sections.warnings.append(
                                "binary DAT section could not be byte-aligned; "
                                "falling back to latin-1 re-encode (lossy)"
                            )
                            sections.dat_binary = body.encode("latin-1", errors="replace")
                    else:
                        sections.dat_binary = body.encode("latin-1", errors="replace")
            else:
                sections.warnings.append(f"unrecognized CFF section: {label}")

        if not sections.cfg_text:
            sections.warnings.append("CFF missing CFG section")
        if sections.dat_text is None and sections.dat_binary is None:
            sections.warnings.append("CFF missing DAT section")
        return sections

    def unpack_file(self, path: FilePath) -> CffSections:
        raw = read_bytes(path)
        text = sniff_text(raw)
        return self.unpack_text(text, raw=raw)

    @staticmethod
    def _extract_binary_section(raw: bytes, label: str) -> Optional[bytes]:
        """Locate DAT binary payload between section markers in raw bytes."""
        # Markers are ASCII
        pattern = re.compile(br"---\s*file\s*type:\s*(.+?)\s*---\s*", re.I)
        matches = list(pattern.finditer(raw))
        for i, m in enumerate(matches):
            lab = m.group(1).decode("ascii", errors="ignore").strip().upper()
            if not lab.startswith("DAT"):
                continue
            start = m.end()
            # Skip one optional CR/LF
            while start < len(raw) and raw[start] in (10, 13):
                start += 1
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            return raw[start:end]
        return None


class CffParser:
    """High-level CFF → sections adapter used by the registry pipeline."""

    def __init__(self) -> None:
        self.unpacker = CffUnpacker()

    def unpack(self, path: FilePath) -> CffSections:
        return self.unpacker.unpack_file(path)
