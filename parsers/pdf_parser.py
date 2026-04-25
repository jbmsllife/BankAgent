import re
from pathlib import Path
from datetime import datetime

DATE_RE   = re.compile(r"\b(\d{2}[/.\-]\d{2}[/.\-]\d{2,4})\b")
AMOUNT_RE = re.compile(r"([+-]?\s*\d[\d\s]*[,\.]\d{2})\s*(?:€|EUR)?")

DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y"]


def _parse_date(s: str) -> str | None:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_amount(s: str) -> float | None:
    s = re.sub(r"[\s\xa0]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class PDFParser:
    def parse(self, filepath: Path) -> list[dict]:
        try:
            import pdfplumber
        except ImportError:
            print("pdfplumber non installé. Lancez : pip install pdfplumber")
            return []

        transactions = []
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    transactions.extend(self._extract_from_text(text))
        except Exception as e:
            print(f"Erreur lecture PDF : {e}")

        # Deduplicate within the same file
        seen = set()
        result = []
        for t in transactions:
            key = (t["date"], t["description"], t["amount"])
            if key not in seen:
                seen.add(key)
                result.append(t)
        return result

    def _extract_from_text(self, text: str) -> list[dict]:
        transactions = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            date_match = DATE_RE.search(line)
            if not date_match:
                continue
            date = _parse_date(date_match.group(1))
            if not date:
                continue
            amounts = AMOUNT_RE.findall(line)
            if not amounts:
                continue
            amount = _parse_amount(amounts[-1])
            if amount is None:
                continue

            # Description = line minus dates and amounts
            desc = DATE_RE.sub("", line)
            desc = AMOUNT_RE.sub("", desc)
            desc = re.sub(r"\s+", " ", desc).strip(" .-,")
            if not desc or len(desc) < 3:
                continue

            transactions.append({"date": date, "description": desc, "amount": amount})
        return transactions
