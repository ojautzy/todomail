"""eml_parser.py — Parse un fichier EML et extrait les métadonnées + corps texte.

Module du skill fetch-imap. Porté depuis archiva-dev/scripts/convert-eml.py en
conservant le même schéma de sortie (consommé par sort-mails).

Expose :
- parse_eml(filepath, max_body_length=None) -> dict
- write_json_alongside(eml_path, max_body_length=None) -> Path

Pas de CLI standalone (utilisez imap_fetch.py ou importez directement).
"""

import email
import email.policy
import email.utils
import json
import re
from email.header import decode_header
from html.parser import HTMLParser
from pathlib import Path


class _HTMLTextExtractor(HTMLParser):
    """Extracteur simple HTML → texte brut."""

    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):  # type: ignore[override]
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):  # type: ignore[override]
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.result.append("\n")

    def handle_data(self, data):  # type: ignore[override]
        if not self._skip:
            self.result.append(data)

    def get_text(self) -> str:
        text = "".join(self.result)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _decode_header_value(value: str | None) -> str:
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    out: list[str] = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


def _extract_text_from_html(html_content: str) -> str:
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_content)
        return extractor.get_text()
    except Exception:
        clean = re.sub(r"<[^>]+>", " ", html_content)
        return re.sub(r"\s+", " ", clean).strip()


def parse_eml(filepath: Path, max_body_length: int | None = None) -> dict:
    """Parse un fichier EML et retourne un dict métadonnées + corps texte.

    Args:
        filepath: chemin vers le fichier .eml
        max_body_length: longueur max du corps texte (None = illimité)

    Returns:
        Dict avec les clés : file, filename, from, to, cc, date, date_iso,
        subject, body_text, body_length, body_truncated, attachments,
        parse_status ("OK"|"NOK-ERREUR"), parse_error.
    """
    filepath = Path(filepath)
    result: dict = {
        "file": str(filepath),
        "filename": filepath.name,
        "from": "",
        "to": "",
        "cc": "",
        "date": "",
        "date_iso": "",
        "subject": "",
        "body_text": "",
        "body_length": 0,
        "body_truncated": False,
        "attachments": [],
        "parse_status": "OK",
        "parse_error": None,
    }

    try:
        with open(filepath, "rb") as f:
            msg = email.message_from_bytes(f.read(), policy=email.policy.default)
    except Exception as e:
        result["parse_status"] = "NOK-ERREUR"
        result["parse_error"] = str(e)
        return result

    result["from"] = _decode_header_value(msg.get("From", ""))
    result["to"] = _decode_header_value(msg.get("To", ""))
    result["cc"] = _decode_header_value(msg.get("Cc", ""))
    result["subject"] = _decode_header_value(msg.get("Subject", ""))

    date_str = msg.get("Date", "")
    result["date"] = date_str
    try:
        parsed_date = email.utils.parsedate_to_datetime(date_str)
        result["date_iso"] = parsed_date.isoformat()
    except Exception:
        result["date_iso"] = ""

    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    filename = _decode_header_value(filename)
                    size = len(part.get_payload(decode=True) or b"")
                    result["attachments"].append({
                        "filename": filename,
                        "size_bytes": size,
                        "content_type": content_type,
                    })
                continue

            if content_type == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")

            elif content_type == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_html = payload.decode(charset, errors="replace")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                body_html = decoded
            else:
                body_text = decoded

    if body_text:
        full_body = body_text
    elif body_html:
        full_body = _extract_text_from_html(body_html)
    else:
        full_body = ""

    result["body_length"] = len(full_body)

    if max_body_length is not None and len(full_body) > max_body_length:
        result["body_text"] = full_body[:max_body_length] + "\n[... tronqué]"
        result["body_truncated"] = True
    else:
        result["body_text"] = full_body

    return result


def write_json_alongside(eml_path: Path, max_body_length: int | None = None) -> Path:
    """Parse `eml_path` et écrit le résultat JSON à côté (même nom, suffixe .json).

    Ne lève jamais : en cas d'erreur parse, le dict écrit contient
    `parse_status: "NOK-ERREUR"` avec `parse_error`.

    Returns:
        Chemin du fichier JSON écrit.
    """
    eml_path = Path(eml_path)
    data = parse_eml(eml_path, max_body_length)
    json_path = eml_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_path
