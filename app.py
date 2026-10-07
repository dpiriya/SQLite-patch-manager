from __future__ import annotations

import atexit
import os
import re
import secrets
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from services.comparison import compare_databases
from services.merge import merge_databases


if getattr(sys, "frozen", False):
    instance_dir = Path(sys.executable).resolve().parent / "instance"
else:
    instance_dir = Path(__file__).resolve().parent / "instance"

app = Flask(__name__, instance_path=str(instance_dir))
app.config.update(
    SECRET_KEY=os.environ.get("PATCH_MANAGER_SECRET") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=200 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=False,
)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict[str, Any]] = {}


def _cleanup_jobs() -> None:
    for job in list(JOBS.values()):
        shutil.rmtree(job["job_dir"], ignore_errors=True)


atexit.register(_cleanup_jobs)


def _valid_database(path: Path) -> None:
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("SQLite integrity check failed.")
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError("The uploaded file is not a readable SQLite database.") from error


def _current_job() -> dict[str, Any]:
    job = JOBS.get(session.get("job_id", ""))
    if job is None:
        abort(404, "This comparison has expired. Upload the databases again.")
    return job


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token() -> dict[str, Any]:
    return {"csrf_token": _csrf_token}


@app.before_request
def protect_post_requests() -> None:
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, "Request verification failed. Reload the page and try again.")


def _report(job: dict[str, Any]) -> dict[str, Any]:
    base = job.get("merged_path") or job["base_path"]
    return compare_databases(job["patch_path"], base)


def _table_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    schema_by_name = {item["name"]: item for item in report["schema_tables"]}
    names = set(report["row_changes"]) | set(report["tables_added"]) | set(report["tables_deleted"])
    entries = []
    for name in sorted(names, key=str.casefold):
        row_change = report["row_changes"].get(name)
        schema = schema_by_name.get(name, {})
        kinds: list[str] = []
        if name in report["tables_added"]:
            kinds.append("table_added")
        if name in report["tables_deleted"]:
            kinds.append("table_deleted")
        if schema.get("added_columns") or schema.get("deleted_columns") or schema.get("changed_columns") or schema.get("definition_changed"):
            kinds.append("schema_changed")
        if row_change:
            for label, kind in (("added", "row_added"), ("changed", "row_changed"), ("deleted", "row_deleted")):
                if row_change.get(label):
                    kinds.append(kind)
            if not row_change["supported"]:
                kinds.append("unsupported")
        entries.append({
            "name": name,
            "kinds": kinds,
            "row_change": row_change,
            "schema": schema,
            "added_count": len(row_change["added"]) if row_change else 0,
            "changed_count": len(row_change["changed"]) if row_change else 0,
            "deleted_count": len(row_change["deleted"]) if row_change else 0,
        })
    return entries


def _wildcard_match(pattern: str, value: str) -> bool:
    expression = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    expression = expression.replace(r"\?", ".")
    return re.match(expression, value, re.IGNORECASE) is not None


@app.get("/")
def index():
    message = request.args.get("message")
    return render_template("index.html", message=message)


@app.post("/compare")
def compare_uploads():
    patch_file = request.files.get("patch")
    base_file = request.files.get("base")
    if not patch_file or not base_file or not patch_file.filename or not base_file.filename:
        flash("Choose both a Patch database and a Base database.", "error")
        return redirect(url_for("index"))

    job_id = uuid.uuid4().hex
    job_dir = Path(app.instance_path) / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    patch_path = job_dir / "patch.sqlite"
    base_path = job_dir / "base.sqlite"
    try:
        patch_file.save(patch_path)
        base_file.save(base_path)
        _valid_database(patch_path)
        _valid_database(base_path)
        report = compare_databases(patch_path, base_path)
    except (ValueError, sqlite3.Error) as error:
        shutil.rmtree(job_dir, ignore_errors=True)
        flash(str(error), "error")
        return redirect(url_for("index"))
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    old_job_id = session.get("job_id")
    if old_job_id and old_job_id in JOBS:
        shutil.rmtree(JOBS[old_job_id]["job_dir"], ignore_errors=True)
        JOBS.pop(old_job_id, None)
    JOBS[job_id] = {
        "job_dir": job_dir,
        "patch_path": patch_path,
        "base_path": base_path,
        "merged_path": None,
    }
    session["job_id"] = job_id
    return redirect(url_for("dashboard"))


@app.get("/dashboard")
def dashboard():
    job = _current_job()
    report = _report(job)
    return render_template(
        "dashboard.html",
        report=report,
        merged=job["merged_path"] is not None,
    )


@app.get("/changes")
def changes():
    job = _current_job()
    report = _report(job)
    entries = _table_entries(report)
    query = request.args.get("q", "").strip()
    change_type = request.args.get("type", "all")
    allowed_types = {
        "all", "schema_changed", "table_added", "table_deleted",
        "row_added", "row_changed", "row_deleted", "unsupported",
    }
    if change_type not in allowed_types:
        change_type = "all"
    if query:
        entries = [entry for entry in entries if _wildcard_match(query, entry["name"])]
    if change_type != "all":
        entries = [entry for entry in entries if change_type in entry["kinds"]]
    try:
        page_size = int(request.args.get("page_size", "25"))
    except ValueError:
        page_size = 25
    if page_size not in (10, 25, 50, 100):
        page_size = 25
    page_count = max(1, (len(entries) + page_size - 1) // page_size)
    try:
        page = min(max(1, int(request.args.get("page", "1"))), page_count)
    except ValueError:
        page = 1
    visible = entries[(page - 1) * page_size:page * page_size]
    return render_template(
        "changes.html",
        entries=visible,
        query=query,
        change_type=change_type,
        page=page,
        page_count=page_count,
        page_size=page_size,
        total=len(entries),
    )


@app.get("/changes/<path:table_name>")
def table_detail(table_name: str):
    report = _report(_current_job())
    entries = {entry["name"]: entry for entry in _table_entries(report)}
    entry = entries.get(table_name)
    if entry is None:
        abort(404, "Table not found in this comparison.")
    changes = []
    row_change = entry["row_change"]
    if row_change and row_change["supported"]:
        for kind in ("added", "changed", "deleted"):
            for row in row_change[kind]:
                changes.append({"kind": kind, **row})
    return render_template("detail.html", entry=entry, changes=changes)


@app.post("/merge")
def merge():
    job = _current_job()
    apply_structure = request.form.get("apply_structure") == "on"
    apply_updates = request.form.get("apply_updates") == "on"
    apply_deletions = request.form.get("apply_deletions") == "on"
    output = job["job_dir"] / "merged.sqlite"
    try:
        merge_databases(
            job["patch_path"],
            job["base_path"],
            output,
            apply_structure=apply_structure,
            apply_updates=apply_updates,
            apply_deletions=apply_deletions,
        )
        _valid_database(output)
    except (ValueError, sqlite3.Error) as error:
        flash(f"Merge failed: {error}", "error")
        return redirect(url_for("dashboard"))
    job["merged_path"] = output
    flash("Merged database created. Review the refreshed comparison or download the file.", "success")
    return redirect(url_for("dashboard"))


@app.get("/download")
def download():
    output = _current_job().get("merged_path")
    if output is None or not output.is_file():
        abort(404, "Run a merge before downloading the result.")
    return send_file(output, as_attachment=True, download_name="merged.sqlite", mimetype="application/vnd.sqlite3")


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return render_template("index.html", message="Each upload must be 200 MB or smaller."), 413


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=error.description), 400


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message=error.description), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
