import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Any

DB_PATH = Path("data/transactions.db")

CATEGORIES = [
    "Alimentation/Courses",
    "Restaurant/Café",
    "Transport",
    "Logement/Loyer",
    "Santé",
    "Loisirs/Entertainment",
    "Shopping/Vêtements",
    "Services/Abonnements",
    "Voyages",
    "Salaire/Revenus",
    "Virements",
    "Banque/Frais",
    "Impôts/Taxes",
    "Autre",
]

CATEGORY_ICONS = {
    "Alimentation/Courses": "🛒",
    "Restaurant/Café": "🍽️",
    "Transport": "🚗",
    "Logement/Loyer": "🏠",
    "Santé": "🏥",
    "Loisirs/Entertainment": "🎮",
    "Shopping/Vêtements": "👗",
    "Services/Abonnements": "📱",
    "Voyages": "✈️",
    "Salaire/Revenus": "💰",
    "Virements": "🔄",
    "Banque/Frais": "🏦",
    "Impôts/Taxes": "📋",
    "Autre": "📌",
}


class Database:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT    NOT NULL,
                    description TEXT    NOT NULL,
                    amount      REAL    NOT NULL,
                    category    TEXT    NOT NULL DEFAULT 'Autre',
                    source_file TEXT    NOT NULL DEFAULT '',
                    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date     ON transactions(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON transactions(category)")

    # ── writes ────────────────────────────────────────────────────────────────

    def insert(self, t: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO transactions (date, description, amount, category, source_file) VALUES (?,?,?,?,?)",
                (t["date"], t["description"], t["amount"], t.get("category", "Autre"), t.get("source_file", "")),
            )

    def update_category(self, txn_id: int, category: str):
        with self._conn() as conn:
            conn.execute("UPDATE transactions SET category=? WHERE id=?", (category, txn_id))

    def delete(self, txn_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM transactions WHERE id=?", (txn_id,))

    # ── reads ─────────────────────────────────────────────────────────────────

    def exists(self, date: str, description: str, amount: float) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM transactions WHERE date=? AND description=? AND amount=?",
                (date, description, amount),
            ).fetchone()
            return row is not None

    def get_transactions(self, category="", search="", month="", limit: int | None = None) -> list[dict]:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list[Any] = []
        if category:
            query += " AND category=?"
            params.append(category)
        if search:
            query += " AND description LIKE ?"
            params.append(f"%{search}%")
        if month:
            query += " AND date LIKE ?"
            params.append(f"{month}%")
        query += " ORDER BY date DESC, id DESC"
        if limit:
            query += f" LIMIT {limit}"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        result = [dict(r) for r in rows]
        for r in result:
            r["icon"] = CATEGORY_ICONS.get(r["category"], "📌")
        return result

    def get_categories(self) -> list[str]:
        return CATEGORIES

    def get_months(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substr(date,1,7) AS m FROM transactions ORDER BY m DESC"
            ).fetchall()
        return [r[0] for r in rows]

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            debit = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE amount<0").fetchone()[0]
            credit = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE amount>0").fetchone()[0]
        return {"total": total, "total_debit": debit, "total_credit": credit}

    def get_by_category(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT category,
                       COUNT(*)    AS count,
                       SUM(amount) AS total
                FROM   transactions
                GROUP  BY category
                ORDER  BY total ASC
            """).fetchall()
        result = [dict(r) for r in rows]
        for r in result:
            r["icon"] = CATEGORY_ICONS.get(r["category"], "📌")
        return result

    def get_monthly_summary(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT substr(date,1,7)          AS month,
                       COALESCE(SUM(CASE WHEN amount<0 THEN amount ELSE 0 END),0) AS depenses,
                       COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS revenus
                FROM   transactions
                GROUP  BY month
                ORDER  BY month DESC
                LIMIT  12
            """).fetchall()
        return [dict(r) for r in reversed(rows)]
