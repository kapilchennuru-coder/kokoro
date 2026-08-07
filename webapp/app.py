# =============================================================
# Zebl Calling Agent - web app
#
# Client logs in -> uploads their patient list -> triggers calls ->
# sees answered/no-answer/rejected status per patient.
#
# Reuses the existing Kokoro voice generation (voice.py) and Asterisk
# AMI Originate logic (ami_client.py) that were already proven to
# work from the command-line prototype - this just wraps them behind
# a browser UI with per-client login and stored call history.
# =============================================================

import os

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import db
import ami_client
import voice

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

REQUIRED_COLUMNS = {"patient_id", "patient_name", "phone_number", "balance_amount"}


def login_required(view):
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["client_name"] = user["client_name"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    patients = db.get_patients(session["user_id"])
    return render_template("dashboard.html", patients=patients, client_name=session.get("client_name"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files.get("patients_file")
        if not file or file.filename == "":
            flash("Choose a file first")
            return redirect(url_for("upload"))

        filename = secure_filename(file.filename)
        saved_path = os.path.join(UPLOAD_DIR, f"user{session['user_id']}_{filename}")
        file.save(saved_path)

        try:
            if filename.lower().endswith(".csv"):
                df = pd.read_csv(saved_path)
            else:
                df = pd.read_excel(saved_path)
        except Exception as exc:
            flash(f"Could not read file: {exc}")
            return redirect(url_for("upload"))

        missing = REQUIRED_COLUMNS - set(df.columns.str.strip())
        if missing:
            flash(f"File is missing required columns: {', '.join(sorted(missing))}")
            return redirect(url_for("upload"))

        patients = [
            {
                "patient_id": str(row["patient_id"]),
                "patient_name": str(row["patient_name"]),
                "phone_number": str(row["phone_number"]),
                "balance_amount": float(row["balance_amount"]),
            }
            for _, row in df.iterrows()
        ]
        db.replace_patients(session["user_id"], patients)
        flash(f"Uploaded {len(patients)} patients")
        return redirect(url_for("dashboard"))

    return render_template("upload.html")


@app.route("/call/<int:row_id>", methods=["POST"])
@login_required
def call_patient(row_id):
    patient = db.get_patient(session["user_id"], row_id)
    if not patient:
        flash("Patient not found")
        return redirect(url_for("dashboard"))

    try:
        audio_name = voice.generate_patient_audio(
            patient["patient_id"], patient["patient_name"], patient["balance_amount"]
        )
        result = ami_client.place_call(patient["phone_number"], audio_name)
    except Exception as exc:
        result = {"status": "error", "detail": str(exc)}

    db.update_call_result(row_id, result["status"], result.get("detail") or result.get("raw", ""))
    flash(f"Call to {patient['patient_name']}: {result['status']}")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
