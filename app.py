import os
import io
import csv
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file

from database import Database
from categorizer import Categorizer
from parsers.csv_parser import CSVParser
from parsers.pdf_parser import PDFParser

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-in-prod")

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
SUPPORTED_EXTENSIONS = {".csv", ".pdf"}

db = Database()
categorizer = Categorizer()


def process_file(filepath: Path) -> tuple[int, int]:
    """Return (imported, skipped) counts."""
    ext = filepath.suffix.lower()
    try:
        if ext == ".csv":
            transactions = CSVParser().parse(filepath)
        elif ext == ".pdf":
            transactions = PDFParser().parse(filepath)
        else:
            return 0, 0
    except Exception as e:
        print(f"Erreur parsing {filepath.name}: {e}")
        return 0, 0

    if not transactions:
        return 0, 0

    new, skipped = [], 0
    for t in transactions:
        if db.exists(t["date"], t["description"], t["amount"]):
            skipped += 1
        else:
            new.append(t)

    if new:
        categorized = categorizer.categorize_batch(new)
        for t in categorized:
            t["source_file"] = filepath.name
            db.insert(t)

    return len(new), skipped


@app.route("/")
def index():
    stats = db.get_stats()
    recent = db.get_transactions(limit=10)
    by_category = db.get_by_category()
    monthly = db.get_monthly_summary()
    files = sorted(UPLOAD_FOLDER.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return render_template(
        "index.html",
        stats=stats,
        recent=recent,
        by_category=by_category,
        monthly=monthly,
        files=[f.name for f in files if f.suffix.lower() in SUPPORTED_EXTENSIONS],
    )


@app.route("/transactions")
def transactions():
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    month = request.args.get("month", "")
    txns = db.get_transactions(category=category, search=search, month=month)
    categories = db.get_categories()
    months = db.get_months()
    return render_template(
        "transactions.html",
        transactions=txns,
        categories=categories,
        months=months,
        current_category=category,
        current_search=search,
        current_month=month,
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("index"))

    file = request.files["file"]
    if not file.filename:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("index"))

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        flash(f"Format non supporté. Utilisez : {', '.join(SUPPORTED_EXTENSIONS)}", "error")
        return redirect(url_for("index"))

    filepath = UPLOAD_FOLDER / file.filename
    file.save(filepath)

    imported, skipped = process_file(filepath)
    msg = f"{imported} transaction(s) importée(s) depuis « {file.filename} »"
    if skipped:
        msg += f" ({skipped} doublon(s) ignoré(s))"
    flash(msg, "success" if imported else "info")
    return redirect(url_for("transactions"))


@app.route("/process-folder")
def process_folder():
    total_imported, total_skipped = 0, 0
    files = [p for p in UPLOAD_FOLDER.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        flash("Aucun fichier compatible trouvé dans le dossier uploads/.", "info")
        return redirect(url_for("index"))

    for filepath in files:
        imp, skp = process_file(filepath)
        total_imported += imp
        total_skipped += skp

    msg = f"{total_imported} transaction(s) importée(s) depuis {len(files)} fichier(s)"
    if total_skipped:
        msg += f" ({total_skipped} doublon(s) ignoré(s))"
    flash(msg, "success" if total_imported else "info")
    return redirect(url_for("transactions"))


@app.route("/recategorize/<int:txn_id>", methods=["POST"])
def recategorize(txn_id):
    category = request.form.get("category", "Autre")
    db.update_category(txn_id, category)
    return redirect(request.referrer or url_for("transactions"))


@app.route("/delete/<int:txn_id>", methods=["POST"])
def delete_transaction(txn_id):
    db.delete(txn_id)
    flash("Transaction supprimée.", "info")
    return redirect(request.referrer or url_for("transactions"))


@app.route("/export")
def export():
    txns = db.get_transactions()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Description", "Montant", "Catégorie", "Fichier source"])
    for t in txns:
        writer.writerow([t["date"], t["description"], t["amount"], t["category"], t["source_file"]])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"transactions_{datetime.now().strftime('%Y%m%d')}.csv",
    )


if __name__ == "__main__":
    print("BankAgent démarré sur http://localhost:5000")
    app.run(debug=True, port=5000)
