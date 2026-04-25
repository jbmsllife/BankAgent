import csv
import re
from pathlib import Path
from datetime import datetime

DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d.%m.%y"]

DATE_KEYWORDS   = {"date", "datum", "jour", "date opé", "date operation", "date valeur"}
DESC_KEYWORDS   = {"libellé", "libelle", "description", "opération", "operation",
                   "label", "motif", "intitulé", "wording", "details"}
DEBIT_KEYWORDS  = {"débit", "debit", "montant déb", "retrait", "sortie", "withdrawal"}
CREDIT_KEYWORDS = {"crédit", "credit", "montant créd", "versement", "entrée", "deposit"}
AMOUNT_KEYWORDS = {"montant", "amount", "solde", "valeur", "somme", "transaction"}


def _parse_date(s: str) -> str | None:
    s = re.sub(r"[\s\xa0]", "", s.strip())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_amount(s: str) -> float | None:
    s = re.sub(r"[€EUR\s\xa0+]", "", s.strip())
    if not s or s in ("-",):
        return None
    # French format: 1.234,56 → 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _detect_encoding(path: Path) -> str:
    try:
        import chardet
        with open(path, "rb") as f:
            return chardet.detect(f.read(10_000))["encoding"] or "utf-8"
    except ImportError:
        for enc in ("utf-8-sig", "latin-1", "utf-8"):
            try:
                with open(path, encoding=enc) as f:
                    f.read(1024)
                return enc
            except UnicodeDecodeError:
                pass
        return "latin-1"


def _col_idx(headers: list[str], keywords: set[str]) -> int | None:
    for i, h in enumerate(headers):
        h_clean = h.lower().strip()
        for kw in keywords:
            if kw in h_clean:
                return i
    return None


class CSVParser:
    def parse(self, filepath: Path) -> list[dict]:
        encoding = _detect_encoding(filepath)
        for delimiter in (";", ",", "\t", "|"):
            try:
                result = self._try_parse(filepath, encoding, delimiter)
                if result:
                    return result
            except Exception:
                continue
        return []

    def _try_parse(self, filepath: Path, encoding: str, delimiter: str) -> list[dict]:
        with open(filepath, encoding=encoding, errors="replace", newline="") as f:
            rows = [r for r in csv.reader(f, delimiter=delimiter) if any(c.strip() for c in r)]

        if len(rows) < 2:
            return []

        # Find header row (first 15 rows)
        for header_idx, header_row in enumerate(rows[:15]):
            headers = [c.lower().strip() for c in header_row]
            date_col = _col_idx(headers, DATE_KEYWORDS)
            desc_col = _col_idx(headers, DESC_KEYWORDS)
            if date_col is None or desc_col is None:
                continue

            debit_col  = _col_idx(headers, DEBIT_KEYWORDS)
            credit_col = _col_idx(headers, CREDIT_KEYWORDS)
            amount_col = _col_idx(headers, AMOUNT_KEYWORDS) if not (debit_col and credit_col) else None

            transactions = []
            for row in rows[header_idx + 1:]:
                if len(row) < max(filter(None, [date_col, desc_col, debit_col, credit_col, amount_col]), default=0) + 1:
                    continue
                t = self._parse_row(row, date_col, desc_col, amount_col, debit_col, credit_col)
                if t:
                    transactions.append(t)

            if transactions:
                return transactions

        return []

    def _parse_row(self, row, date_col, desc_col, amount_col, debit_col, credit_col) -> dict | None:
        date = _parse_date(row[date_col])
        if not date:
            return None

        description = row[desc_col].strip()
        if not description or len(description) < 2:
            return None

        amount = None
        if amount_col is not None and amount_col < len(row):
            amount = _parse_amount(row[amount_col])
        else:
            debit = _parse_amount(row[debit_col]) if debit_col is not None and debit_col < len(row) else None
            credit = _parse_amount(row[credit_col]) if credit_col is not None and credit_col < len(row) else None
            if debit and debit != 0:
                amount = -abs(debit)
            elif credit and credit != 0:
                amount = abs(credit)

        if amount is None:
            # Last resort: scan remaining cells for a number
            for cell in reversed(row):
                a = _parse_amount(cell)
                if a is not None:
                    amount = a
                    break

        if amount is None:
            return None

        return {"date": date, "description": description, "amount": amount}
