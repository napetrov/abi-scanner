"""ABICC backend: wraps abi-compliance-checker for type-level ABI analysis."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

logger = logging.getLogger(__name__)


@dataclass
class AbiccResult:
    binary_compat: float = 100.0      # 0.0–100.0
    source_compat: float = 100.0      # 0.0–100.0
    binary_problems: int = 0
    source_problems: int = 0
    added_symbols: int = 0
    removed_symbols: int = 0
    removed_symbol_names: list[str] = field(default_factory=list)
    type_changes: list[str] = field(default_factory=list)
    html_report_path: Optional[Path] = None
    error: Optional[str] = None


def _parse_html_report(html_path: Path) -> AbiccResult:
    """Parse ABICC HTML report and return AbiccResult."""
    result = AbiccResult()
    result.html_report_path = html_path

    if not html_path.exists():
        result.error = f"HTML report not found: {html_path}"
        return result

    html = html_path.read_text(encoding="utf-8", errors="replace")

    # Fast regex extraction of key metrics from the summary table
    bin_pct = re.search(r'[Bb]inary\s+[Cc]ompatibility[^<]*?(\d[\d.]*)\s*%', html)
    src_pct = re.search(r'[Ss]ource\s+[Cc]ompatibility[^<]*?(\d[\d.]*)\s*%', html)
    if bin_pct:
        result.binary_compat = float(bin_pct.group(1))
    if src_pct:
        result.source_compat = float(src_pct.group(1))

    # Problem counts
    bin_prob = re.search(r'[Bb]inary\s+[Pp]roblems[^<]*?(\d+)', html)
    src_prob = re.search(r'[Ss]ource\s+[Pp]roblems[^<]*?(\d+)', html)
    if bin_prob:
        result.binary_problems = int(bin_prob.group(1))
    if src_prob:
        result.source_problems = int(src_prob.group(1))

    # Symbol counts
    added_m = re.search(r'Added\s+Symbols[^<]*?(\d+)', html)
    removed_m = re.search(r'Removed\s+Symbols[^<]*?(\d+)', html)
    if added_m:
        result.added_symbols = int(added_m.group(1))
    if removed_m:
        result.removed_symbols = int(removed_m.group(1))

    # Find removed symbol names using ABICC's actual span class
    iname_matches = re.findall(r'<span[^>]*class=["\']iname["\'][^>]*>(.*?)</span>', html, re.DOTALL)
    for m in iname_matches[:100]:
        # Strip HTML tags
        sym = re.sub(r'<[^>]+>', '', m).strip()
        if sym and len(sym) > 3:
            result.removed_symbol_names.append(sym)

    # Extract type changes from Source_Changed section
    src_changed_match = re.search(
        r'<a\s+name=["\']?Source_Changed["\']?[^>]*>.*?(<table[^>]*>.*?</table>)',
        html, re.DOTALL | re.IGNORECASE
    )
    if src_changed_match:
        table_html = src_changed_match.group(1)
        changes = re.findall(r'<td[^>]*>\s*([a-zA-Z_][a-zA-Z0-9_:<>*, &~()[\]]+(?:\s+changed)?[a-zA-Z0-9_:<>*, &~()[\]]*)\s*</td>', table_html)
        for ch in changes[:50]:
            ch = ch.strip()
            if ch and len(ch) > 5 and ch not in result.type_changes:
                result.type_changes.append(ch)

    return result


def _write_xml_descriptor(
    path: Path,
    version: str,
    lib_path: Path,
    headers_path: Path,
    skip_headers: list[str],
) -> None:
    skip_str = "\n".join(skip_headers) if skip_headers else ""
    skip_xml = f"  <skip_headers>\n{skip_str}\n  </skip_headers>\n" if skip_str else ""
    xml = (
        f"<version>{_xml_escape(version)}</version>\n"
        f"<headers>{_xml_escape(str(headers_path))}</headers>\n"
        f"{skip_xml}"
        f"<libs>{_xml_escape(str(lib_path))}</libs>\n"
    )
    path.write_text(xml, encoding="utf-8")


class AbiccBackend:
    """Run abi-compliance-checker and return parsed results."""

    def run(
        self,
        old_version: str,
        old_lib_path: Path,
        old_headers_path: Path,
        new_version: str,
        new_lib_path: Path,
        new_headers_path: Path,
        library_name: str,
        skip_headers: list[str],
        work_dir: Path,
    ) -> AbiccResult:
        """Run abi-compliance-checker and return parsed result."""
        abicc_bin = shutil.which("abi-compliance-checker")
        if not abicc_bin:
            return AbiccResult(error="abi-compliance-checker not found in PATH")

        work_dir.mkdir(parents=True, exist_ok=True)

        old_xml = work_dir / f"old_{old_version}.xml"
        new_xml = work_dir / f"new_{new_version}.xml"
        report_path = work_dir / f"report_{old_version}_vs_{new_version}.html"

        # Cache: skip if report already exists (headers haven't changed)
        if report_path.exists():
            logger.info(f"[abicc] using cached report: {report_path}")
            return _parse_html_report(report_path)

        # Validate paths before running
        if not old_headers_path.exists():
            return AbiccResult(error=f"Headers path does not exist: {old_headers_path}")
        if not new_headers_path.exists():
            return AbiccResult(error=f"Headers path does not exist: {new_headers_path}")
        if not old_lib_path.exists():
            return AbiccResult(error=f"Library not found: {old_lib_path}")
        if not new_lib_path.exists():
            return AbiccResult(error=f"Library not found: {new_lib_path}")

        try:
            _write_xml_descriptor(old_xml, old_version, old_lib_path, old_headers_path, skip_headers)
            _write_xml_descriptor(new_xml, new_version, new_lib_path, new_headers_path, skip_headers)
        except Exception as exc:
            return AbiccResult(error=f"Failed to write XML descriptors: {exc}")

        cmd = [
            abicc_bin,
            "-lib", library_name,
            "-old", str(old_xml),
            "-new", str(new_xml),
            "-report-path", str(report_path),
        ]

        logger.debug("Running: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return AbiccResult(error="abi-compliance-checker timed out after 300s")
        except Exception as exc:
            return AbiccResult(error=f"abi-compliance-checker execution failed: {exc}")

        # ABICC returns non-zero when incompatible — that's OK
        # Code 6 = header compile errors but report may still be generated
        if proc.returncode not in (0, 1, 6):
            stderr_snippet = (proc.stderr or "")[-500:]
            return AbiccResult(
                error=f"abi-compliance-checker exited with code {proc.returncode}: {stderr_snippet}"
            )

        if not report_path.exists():
            return AbiccResult(error=f"abi-compliance-checker did not produce report at {report_path}")

        result = _parse_html_report(report_path)
        return result
