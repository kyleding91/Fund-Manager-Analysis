"""Phase 2a — Parse a 13F full-submission text file into structured data.

A 13F submission .txt is SGML that wraps one or more <DOCUMENT> blocks. We care about:
  * the cover page (TYPE 13F-HR / 13F-HR/A) -> manager name, period, totals
  * the information table (TYPE INFORMATION TABLE) -> the individual holdings

Filings vary: some use XML namespace prefixes (<ns1:infoTable>), some don't.
We parse namespace-agnostically using each element's local name.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree

# Extract the XML payload embedded inside an SGML <XML> ... </XML> wrapper.
_XML_BLOCK = re.compile(r"<XML>\s*(.*?)\s*</XML>", re.S | re.I)
# Split the submission into its component documents.
_DOC_BLOCK = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S | re.I)
_TYPE_TAG = re.compile(r"<TYPE>\s*([^\r\n<]+)", re.I)


@dataclass
class Holding:
    name_of_issuer: str
    title_of_class: str
    cusip: str
    value: float            # in the filing's reported units (normalized later)
    shares: float
    shares_type: str        # "SH" (shares) or "PRN" (principal amount)
    put_call: str = ""      # "Put"/"Call"/"" for options

    @property
    def issuer_cusip(self) -> str:
        """First 6 CUSIP chars identify the issuer (company)."""
        return (self.cusip or "")[:6].upper()


@dataclass
class ParsedFiling:
    cik: str
    manager_name: str
    form_type: str
    period_of_report: str          # YYYY-MM-DD
    date_filed: str                # YYYY-MM-DD
    accession: str
    reported_value_total: float    # from cover page (filing units)
    reported_entry_total: int      # from cover page (row count)
    amendment_type: str = ""       # cover-page <amendmentType>: "NEW HOLDINGS",
                                   # "RESTATEMENT", or "" (absent / not an amendment)
    is_confidential: bool = False  # holdings omitted via confidential treatment
    holdings: list[Holding] = field(default_factory=list)

    @property
    def quarter_label(self) -> str:
        """e.g. '2025-Q1' derived from the period-of-report month."""
        d = datetime.strptime(self.period_of_report, "%Y-%m-%d")
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


# --- helpers -------------------------------------------------------------
def _localname(tag) -> str:
    if isinstance(tag, str):
        return tag.rsplit("}", 1)[-1]
    return ""


def _find_text(el, name: str) -> str | None:
    """First descendant whose local-name matches `name`, returns its text."""
    for child in el.iter():
        if _localname(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _to_float(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return 0.0


def _parse_period(raw: str | None) -> str:
    """Cover-page period is 'MM-DD-YYYY'; normalize to 'YYYY-MM-DD'."""
    if not raw:
        return ""
    raw = raw.strip()
    for fmt in ("%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _xml_roots(submission_text: str):
    """Yield (doc_type, parsed_xml_root) for each XML document in the submission."""
    for doc in _DOC_BLOCK.findall(submission_text):
        tmatch = _TYPE_TAG.search(doc)
        doc_type = tmatch.group(1).strip().upper() if tmatch else ""
        xmatch = _XML_BLOCK.search(doc)
        if not xmatch:
            continue
        payload = xmatch.group(1).strip()
        try:
            root = etree.fromstring(payload.encode("utf-8", "replace"))
        except etree.XMLSyntaxError:
            try:  # be lenient with malformed XML
                root = etree.fromstring(
                    payload.encode("utf-8", "replace"),
                    parser=etree.XMLParser(recover=True),
                )
            except etree.XMLSyntaxError:
                continue
        yield doc_type, root


# --- public API ----------------------------------------------------------
def parse_submission(submission_text: str, *, cik: str, form_type: str,
                     date_filed: str, accession: str) -> ParsedFiling | None:
    """Parse a full 13F submission into a ParsedFiling, or None if unparseable."""
    manager_name = ""
    period = ""
    value_total = 0.0
    entry_total = 0
    amendment_type = ""
    is_confidential = False
    holdings: list[Holding] = []

    for doc_type, root in _xml_roots(submission_text):
        local = _localname(root.tag)
        is_info_table = doc_type == "INFORMATION TABLE" or any(
            _localname(e.tag) == "infoTable" for e in root.iter()
        )
        if is_info_table:
            for entry in root.iter():
                if _localname(entry.tag) != "infoTable":
                    continue
                holdings.append(
                    Holding(
                        # Some filings double-escape text ("S&amp;amp;P" survives the
                        # XML parse as "S&amp;P"); unescape once more so the DB
                        # stores plain text ("S&P"), never HTML entities.
                        name_of_issuer=html.unescape(_find_text(entry, "nameOfIssuer") or ""),
                        title_of_class=html.unescape(_find_text(entry, "titleOfClass") or ""),
                        cusip=(_find_text(entry, "cusip") or "").upper(),
                        value=_to_float(_find_text(entry, "value")),
                        shares=_to_float(_find_text(entry, "sshPrnamt")),
                        shares_type=_find_text(entry, "sshPrnamtType") or "",
                        put_call=_find_text(entry, "putCall") or "",
                    )
                )
        else:
            # cover page (primary_doc): pull manager name + period + totals
            if not manager_name:
                manager_name = html.unescape(_find_text(root, "name") or "")
            if not period:
                period = _parse_period(_find_text(root, "periodOfReport"))
            if not amendment_type:
                # 13F-HR/A cover pages carry <amendmentInfo><amendmentType>:
                # "NEW HOLDINGS" (partial add-on) or "RESTATEMENT" (full book).
                amendment_type = (_find_text(root, "amendmentType") or "").strip().upper()
            vt = _find_text(root, "tableValueTotal")
            if vt:
                value_total = _to_float(vt)
            et = _find_text(root, "tableEntryTotal")
            if et:
                entry_total = int(_to_float(et))
            conf = _find_text(root, "isConfidentialOmitted")
            if conf and conf.strip().lower() == "true":
                is_confidential = True

    if not holdings and not manager_name:
        return None

    return ParsedFiling(
        cik=cik,
        manager_name=manager_name or "(unknown)",
        form_type=form_type,
        period_of_report=period,
        date_filed=date_filed,
        accession=accession,
        reported_value_total=value_total,
        reported_entry_total=entry_total,
        amendment_type=amendment_type,
        is_confidential=is_confidential,
        holdings=holdings,
    )
