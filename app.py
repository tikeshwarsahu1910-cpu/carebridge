from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import re
import json
import base64
from functools import wraps
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "carebridge.db")

with open(os.path.join(BASE_DIR, "medicine_catalog.json"), encoding="utf-8") as catalog_file:
    MEDICINE_CATALOG = json.load(catalog_file)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("CAREBRIDGE_SECRET_KEY", "carebridge-demo-secret")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
if os.environ.get("FLASK_ENV") == "production" and app.config["SECRET_KEY"] == "carebridge-demo-secret":
    raise RuntimeError("Set CAREBRIDGE_SECRET_KEY before deploying CareBridge.")


@app.after_request
def add_reminder_controls(response):
    """Load shared notification and sound controls on every CareBridge page."""
    if response.content_type.startswith("text/html"):
        html = response.get_data(as_text=True)
        if "reminders.js" not in html:
            response.set_data(html.replace(
                "</body>",
                '<script src="/static/reminders.js"></script></body>',
            ))
    return response


# =========================
# DATABASE
# =========================

def get_db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


DEFAULT_MEDICINES = (
    ("Aspirin", "75 mg", "After breakfast", "30 days"),
    ("Atorvastatin", "20 mg", "After dinner", "30 days"),
    ("Metoprolol", "25 mg", "Morning", "14 days"),
)


def ensure_default_medicines(connection, patient_id):
    """Give a new/empty care plan a usable three-medicine starter schedule."""
    count = connection.execute(
        "SELECT COUNT(*) FROM medicines WHERE patient_id = ?", (patient_id,)
    ).fetchone()[0]
    if count:
        return
    connection.executemany(
        "INSERT INTO medicines (patient_id, name, dose, timing, duration, taken) VALUES (?, ?, ?, ?, ?, 0)",
        [(patient_id, *medicine) for medicine in DEFAULT_MEDICINES],
    )
    connection.commit()


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Please sign in first."}), 401
        return view(*args, **kwargs)
    return wrapped


def get_current_patient_id(connection):
    """Return the signed-in user's private care-plan record, creating it once."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    patient = connection.execute(
        "SELECT id FROM patients WHERE user_id = ?", (user_id,)
    ).fetchone()
    if patient:
        ensure_default_medicines(connection, patient["id"])
        return patient["id"]
    # Preserve the original demo plan for the first real account that uses
    # this upgraded database, instead of unexpectedly showing an empty plan.
    unassigned = connection.execute(
        "SELECT id FROM patients WHERE user_id IS NULL ORDER BY id LIMIT 1"
    ).fetchone()
    if unassigned:
        connection.execute("UPDATE patients SET user_id = ? WHERE id = ?", (user_id, unassigned["id"]))
        connection.commit()
        ensure_default_medicines(connection, unassigned["id"])
        return unassigned["id"]
    user = connection.execute(
        "SELECT name, age FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        return None
    cursor = connection.execute(
        "INSERT INTO patients (user_id, name, age, condition, language, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, user["name"], user["age"], "Post-discharge recovery", "English", datetime.now().isoformat()),
    )
    connection.commit()
    ensure_default_medicines(connection, cursor.lastrowid)
    return cursor.lastrowid


def init_db():

    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            condition TEXT,
            language TEXT,
            created_at TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            mobile TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            weight REAL NOT NULL,
            gender TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    patient_columns = {row["name"] for row in connection.execute("PRAGMA table_info(patients)")}
    if "user_id" not in patient_columns:
        connection.execute("ALTER TABLE patients ADD COLUMN user_id INTEGER")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            name TEXT,
            dose TEXT,
            timing TEXT,
            duration TEXT,
            taken INTEGER DEFAULT 0
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            title TEXT,
            date TEXT,
            status TEXT DEFAULT 'Upcoming'
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS caregivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            name TEXT,
            relation TEXT,
            phone TEXT
        )
    """)

    # Create demo patient only once
    patient_count = connection.execute(
        "SELECT COUNT(*) FROM patients"
    ).fetchone()[0]

    if patient_count == 0:

        cursor = connection.execute("""
            INSERT INTO patients
            (name, age, condition, language, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "Rajesh Kumar",
            67,
            "Post-discharge cardiac recovery",
            "Hindi",
            datetime.now().isoformat()
        ))

        patient_id = cursor.lastrowid

        for medicine in DEFAULT_MEDICINES:

            connection.execute("""
                INSERT INTO medicines
                (patient_id, name, dose, timing, duration)
                VALUES (?, ?, ?, ?, ?)
            """, (
                patient_id,
                medicine[0],
                medicine[1],
                medicine[2],
                medicine[3]
            ))

        connection.execute("""
            INSERT INTO appointments
            (patient_id, title, date)
            VALUES (?, ?, ?)
        """, (
            patient_id,
            "Cardiology follow-up",
            "2026-09-28"
        ))

        caregivers = [
            ("Amit Kumar", "Son", "+91 90000 11111"),
            ("Sunita Kumar", "Wife", "+91 90000 22222")
        ]

        for caregiver in caregivers:

            connection.execute("""
                INSERT INTO caregivers
                (patient_id, name, relation, phone)
                VALUES (?, ?, ?, ?)
            """, (
                patient_id,
                caregiver[0],
                caregiver[1],
                caregiver[2]
            ))

        connection.commit()

    connection.close()


# =========================
# GET DASHBOARD DATA
# =========================

def get_patient_data():

    connection = get_db()

    patient_id = get_current_patient_id(connection)
    patient = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()

    medicines = connection.execute("""
        SELECT *
        FROM medicines
        WHERE patient_id = ?
    """, (patient["id"],)).fetchall()

    appointments = connection.execute("""
        SELECT *
        FROM appointments
        WHERE patient_id = ?
        ORDER BY date
    """, (patient["id"],)).fetchall()

    caregivers = connection.execute("""
        SELECT *
        FROM caregivers
        WHERE patient_id = ?
    """, (patient["id"],)).fetchall()

    connection.close()

    return {
        "patient": dict(patient),
        "medicines": [dict(x) for x in medicines],
        "appointments": [dict(x) for x in appointments],
        "caregivers": [dict(x) for x in caregivers]
    }


# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html", user_name=session.get("user_name", "Rajesh Kumar"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        connection = get_db()
        user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        connection.close()
        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Email or password is incorrect."), 401
        session["logged_in"] = True
        session["user_name"] = user["name"]
        session["user_id"] = user["id"]
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fields = {key: request.form.get(key, "").strip() for key in ("name", "age", "mobile", "email", "blood_group", "weight", "gender")}
        password = request.form.get("password", "")
        if not all(fields.values()) or len(password) < 6:
            return render_template("signup.html", error="Complete every field. Your password must have at least 6 characters.", values=fields), 400
        try:
            connection = get_db()
            cursor = connection.execute("""
                INSERT INTO users (name, age, mobile, email, password_hash, blood_group, weight, gender, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fields["name"], int(fields["age"]), fields["mobile"], fields["email"].lower(), generate_password_hash(password), fields["blood_group"], float(fields["weight"]), fields["gender"], datetime.now().isoformat()))
            connection.commit()
            user_id = cursor.lastrowid
            connection.close()
        except (ValueError, sqlite3.IntegrityError):
            try: connection.close()
            except: pass
            return render_template("signup.html", error="Use a valid age and weight. This email may already have an account.", values=fields), 400
        session["logged_in"] = True
        session["user_name"] = fields["name"]
        session["user_id"] = user_id
        return redirect(url_for("home"))
    return render_template("signup.html", values={})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


FEATURE_PAGES = {
    "care-plan": {
        "eyebrow": "RECOVERY OVERVIEW",
        "title": "My care plan",
        "description": "A clear, day-by-day view of medicines, routines, and priorities after discharge.",
        "icon": "assignment",
        "items": [{"label": "Review your medicine schedule", "href": "/#medications"}, {"label": "Track follow-up and recovery milestones", "href": "/#appointments"}, {"label": "Share the plan with your care circle", "href": "/#care-circle"}],
    },
    "medications": {
        "eyebrow": "MEDICATION CENTER",
        "title": "Medications",
        "description": "Review medicine timing, marked doses, and general safety guidance in one place.",
        "icon": "medication",
        "items": [{"label": "Review your prescribed medicine list", "href": "/#medications"}, {"label": "Mark a dose as taken on the dashboard", "href": "/#medications"}, {"label": "Use official label lookup for general information", "href": "/#assistant"}],
    },
    "reminders": {
        "eyebrow": "MEDICINE ROUTINE",
        "title": "Medicine reminders",
        "description": "Keep every dose visible and build a dependable recovery routine.",
        "icon": "notifications_active",
        "items": [{"label": "Review the morning dose schedule", "href": "/#medications"}, {"label": "Mark a scheduled dose as taken", "href": "/#medications"}, {"label": "Check reminder permissions", "href": "/#reminders"}],
    },
    "appointments": {
        "eyebrow": "FOLLOW-UP TRACKER",
        "title": "Appointments",
        "description": "See your next clinical touchpoint and arrive prepared.",
        "icon": "calendar_month",
        "items": [{"label": "View your next follow-up", "href": "/#appointments"}, {"label": "Review your discharge summary", "href": "/#care-plan"}, {"label": "Ask the assistant to prepare questions", "href": "/#assistant"}],
    },
    "care-circle": {
        "eyebrow": "CAREGIVER DASHBOARD",
        "title": "Care circle",
        "description": "Keep family and trusted caregivers connected to the recovery plan.",
        "icon": "group",
        "items": [{"label": "View your care-circle members", "href": "/#care-circle"}, {"label": "Call a trusted caregiver", "href": "/#care-circle"}, {"label": "Add or remove a caregiver", "href": "/#care-circle"}],
    },
    "assistant": {
        "eyebrow": "CAREBRIDGE GUIDE",
        "title": "Care assistant",
        "description": "Get clear, simple guidance about the care plan, medicines, and follow-up.",
        "icon": "smart_toy",
        "items": [{"label": "Ask about a missed dose", "href": "/#assistant"}, {"label": "Understand a follow-up visit", "href": "/#assistant"}, {"label": "Learn urgent warning signs", "href": "/#assistant"}],
    },
    "help": {
        "eyebrow": "SUPPORT & REFERENCES",
        "title": "Hospital and care contacts",
        "description": "Keep important support contacts close by when you need them.",
        "icon": "support_agent",
        "items": [{"label": "Emergency services — 112", "href": "tel:112"}, {"label": "CareBridge hospital desk — +91 90000 11111", "href": "tel:+919000011111"}, {"label": "Ask a non-emergency care question", "href": "/#assistant"}],
    },
    "safety": {
        "eyebrow": "CLINICAL SAFETY",
        "title": "Safety checks",
        "description": "Simple safety prompts to support—never replace—professional medical advice.",
        "icon": "health_and_safety",
        "items": [{"label": "Review medicine safety guidance", "href": "/#safety"}, {"label": "Review your medicine list", "href": "/#medications"}, {"label": "Call emergency services for urgent warning signs", "href": "tel:112"}],
    },
}


@app.route("/feature/<feature>")
def feature_page(feature):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    page = FEATURE_PAGES.get(feature)
    if not page:
        return redirect(url_for("home"))
    return render_template("feature.html", page=page, feature=feature, user_name=session.get("user_name", "Rajesh Kumar"))


# =========================
# DASHBOARD API
# =========================

@app.route("/api/dashboard")
@api_login_required
def dashboard():

    return jsonify(get_patient_data())


@app.route("/api/medicines/import", methods=["POST"])
@api_login_required
def import_medicines():
    """Save the verified extraction so it survives navigation and refreshes."""
    payload = request.get_json(silent=True) or {}
    entries = payload.get("medicines")
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": "No medicine entries were provided."}), 400

    medicines = []
    for entry in entries[:30]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()[:80]
        if not name:
            continue
        medicines.append((
            name,
            str(entry.get("dose") or "As prescribed").strip()[:40],
            str(entry.get("timing") or "As prescribed").strip()[:120],
            str(entry.get("duration") or "As prescribed").strip()[:80],
        ))

    if not medicines:
        return jsonify({"error": "No valid medicine entries were found."}), 400

    connection = get_db()
    patient_id = get_current_patient_id(connection)
    connection.execute("DELETE FROM medicines WHERE patient_id = ?", (patient_id,))
    connection.executemany(
        "INSERT INTO medicines (patient_id, name, dose, timing, duration, taken) VALUES (?, ?, ?, ?, ?, 0)",
        [(patient_id, *medicine) for medicine in medicines],
    )
    connection.commit()
    connection.close()
    return jsonify({"success": True, "count": len(medicines)})


# =========================
# CARE ASSISTANT
# =========================

MEDICINE_GUIDES = {
    "aspirin": {
        "summary": "Aspirin is commonly used to help prevent harmful blood clots after some heart conditions.",
        "how_to": "Take it exactly as prescribed, usually with food or water if it upsets your stomach.",
        "caution": "Seek urgent help for vomiting blood, black stools, severe bleeding, or an allergic reaction. Do not stop it without medical advice."
    },
    "atorvastatin": {
        "summary": "Atorvastatin lowers cholesterol and helps protect the heart and blood vessels.",
        "how_to": "Take it at the prescribed time each day. Your care team may monitor blood tests.",
        "caution": "Contact your care team promptly for unexplained severe muscle pain, weakness, or dark urine."
    },
    "metoprolol": {
        "summary": "Metoprolol can slow the heart rate and reduce the heart's workload.",
        "how_to": "Take it exactly as prescribed and do not suddenly stop it unless a clinician tells you to.",
        "caution": "Get medical advice for fainting, a very slow pulse, severe dizziness, or worsening breathing problems."
    },
}


@app.route("/api/assistant", methods=["POST"])
@api_login_required
def care_assistant():
    question = (request.get_json(silent=True) or {}).get("question", "").strip()
    query = question.lower()

    if not question:
        return jsonify({"answer": "Ask a question about your medicines, recovery, follow-up, or warning signs.", "level": "info"})

    urgent_terms = ["chest pain", "difficulty breathing", "shortness of breath", "faint", "fainting", "severe bleeding", "vomit blood", "black stool", "stroke", "suicide"]
    if any(term in query for term in urgent_terms):
        return jsonify({
            "answer": "This could be urgent. Call emergency services (112) now or contact your care team immediately. Do not wait for an online response.",
            "level": "urgent"
        })

    for medicine, guide in MEDICINE_GUIDES.items():
        if medicine in query:
            return jsonify({
                "answer": f"{guide['summary']} {guide['how_to']} Important: {guide['caution']}",
                "level": "medicine",
                "source": "General medicine guide — verify with your prescription label and care team."
            })

    for medicine in MEDICINE_CATALOG:
        if medicine["name"].lower() in query:
            return jsonify({
                "answer": f"{medicine['name']} is commonly used for {medicine['use'].lower()}. It belongs to the {medicine['category']} area. For warnings, interactions, and exact product instructions, use the Official medicine-label lookup or ask a pharmacist.",
                "level": "medicine",
                "source": "CareBridge common-medicine catalog — general education only."
            })

    if any(term in query for term in ["miss", "forgot", "skipped", "double dose"]):
        answer = "For a missed dose, do not take an extra or double dose unless your prescriber gave specific instructions. Check your medicine leaflet or call your pharmacist/care team for medicine-specific advice."
    elif any(term in query for term in ["food", "eat", "diet", "drink"]):
        answer = "Follow the diet instructions in your discharge summary. If you have heart-related recovery instructions, ask your care team about salt, fluid, and alcohol limits that are right for you."
    elif any(term in query for term in ["exercise", "walk", "activity", "rest"]):
        answer = "Start only with the activity level written in your discharge plan. Increase gradually and stop if you have chest pain, severe breathlessness, dizziness, or feel unwell."
    elif any(term in query for term in ["follow", "appointment", "review"]):
        answer = "For follow-up, bring your discharge summary, medicine list, symptom notes, and questions. Contact the clinic if you need to change an appointment."
    elif any(term in query for term in ["side effect", "reaction", "allergy"]):
        answer = "New or worrying side effects should be discussed with a pharmacist or care team. For swelling of the face/lips, trouble breathing, severe rash, or collapse, call emergency services now."
    else:
        answer = "I can explain the care plan, common medicine instructions, warning signs, and follow-up preparation. For a diagnosis, medication change, dose decision, or personal treatment advice, please contact your clinician."

    return jsonify({"answer": answer, "level": "info", "source": "CareBridge provides general education, not diagnosis or personalized prescribing."})


def compact_label_text(value, limit=280):
    """Turn an openFDA label section into a short, readable excerpt."""
    if isinstance(value, list):
        value = " ".join(value)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    sentence_end = text.rfind(". ", 0, limit)
    return text[:sentence_end + 1 if sentence_end > 80 else limit].rstrip() + "…"


@app.route("/api/medicine-research", methods=["POST"])
@api_login_required
def medicine_research():
    medicine = (request.get_json(silent=True) or {}).get("medicine", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9 .,'()-]{2,80}", medicine):
        return jsonify({"error": "Enter a medicine name using letters and numbers only."}), 400

    def query_label(field):
        params = urlencode({"search": f'{field}:"{medicine}"', "limit": 1})
        url = f"https://api.fda.gov/drug/label.json?{params}"
        with urlopen(url, timeout=8) as response:
            return json.load(response), url

    try:
        try:
            payload, source_url = query_label("openfda.generic_name")
        except HTTPError as error:
            if error.code != 404:
                raise
            payload, source_url = query_label("openfda.brand_name")

        label = payload["results"][0]
        openfda = label.get("openfda", {})
        title = (openfda.get("generic_name") or openfda.get("brand_name") or [medicine])[0]
        sections = []
        for label_name, key in (("Use", "indications_and_usage"), ("Warnings", "warnings"), ("Interactions", "drug_interactions"), ("Do not use", "do_not_use")):
            text = compact_label_text(label.get(key))
            if text:
                sections.append(f"{label_name}: {text}")

        if not sections:
            sections.append("An FDA label record was found, but it does not include a short consumer-facing summary.")
        return jsonify({
            "medicine": title,
            "answer": " ".join(sections[:3]),
            "source": "Current U.S. FDA drug-label record",
            "source_url": source_url,
            "disclaimer": "Label data may not match your exact product or country. Do not use this to change a dose or treatment; verify with a pharmacist or clinician."
        })
    except HTTPError as error:
        if error.code == 404:
            return jsonify({"error": "No matching U.S. FDA label was found. Check the generic/brand spelling or ask a pharmacist."}), 404
        return jsonify({"error": "The official label service is temporarily unavailable. Please try again later."}), 503
    except (URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return jsonify({"error": "Could not reach the official label service. Please try again later."}), 503


@app.route("/api/medicine-catalog")
@api_login_required
def medicine_catalog():
    return jsonify({"count": len(MEDICINE_CATALOG), "medicines": MEDICINE_CATALOG})


# =========================
# MEDICINE TOGGLE
# =========================

@app.route("/api/medicine/<int:medicine_id>/toggle", methods=["POST"])
@api_login_required
def toggle_medicine(medicine_id):

    connection = get_db()

    patient_id = get_current_patient_id(connection)
    medicine = connection.execute("""
        SELECT taken
        FROM medicines
        WHERE id = ? AND patient_id = ?
    """, (medicine_id, patient_id)).fetchone()

    if medicine is None:

        connection.close()

        return jsonify({
            "error": "Medicine not found"
        }), 404

    new_status = 0 if medicine["taken"] else 1

    connection.execute("""
        UPDATE medicines
        SET taken = ?
        WHERE id = ? AND patient_id = ?
    """, (
        new_status,
        medicine_id,
        patient_id,
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True,
        "taken": new_status
    })


# =========================
# ADD CAREGIVER
# =========================

@app.route("/api/caregiver", methods=["POST"])
@api_login_required
def add_caregiver():

    data = request.get_json()

    connection = get_db()

    patient_id = get_current_patient_id(connection)

    connection.execute("""
        INSERT INTO caregivers
        (patient_id, name, relation, phone)
        VALUES (?, ?, ?, ?)
    """, (
        patient_id,
        data.get("name", "New caregiver"),
        data.get("relation", "Family"),
        data.get("phone", "")
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


@app.route("/api/caregiver/<int:caregiver_id>", methods=["DELETE"])
@api_login_required
def remove_caregiver(caregiver_id):
    connection = get_db()
    patient_id = get_current_patient_id(connection)
    caregiver = connection.execute(
        "SELECT id FROM caregivers WHERE id = ? AND patient_id = ?", (caregiver_id, patient_id)
    ).fetchone()

    if caregiver is None:
        connection.close()
        return jsonify({"error": "Caregiver not found"}), 404

    connection.execute("DELETE FROM caregivers WHERE id = ? AND patient_id = ?", (caregiver_id, patient_id))
    connection.commit()
    connection.close()
    return jsonify({"success": True})


# =========================
# DISCHARGE SUMMARY PARSER
# =========================

@app.route("/api/analyze-prescription-image", methods=["POST"])
@api_login_required
def analyze_prescription_image():
    """Extract medicine entries with Groq vision. The image is not stored."""
    image = request.files.get("image")
    api_key = os.environ.get("GROQ_API_KEY")

    if image is None or not image.filename:
        return jsonify({"error": "Please choose a prescription image."}), 400
    if not api_key:
        return jsonify({"error": "AI image analysis is not configured. Add GROQ_API_KEY before starting CareBridge."}), 503

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    mime_type = image.mimetype if image.mimetype in allowed_types else ""
    if not mime_type:
        return jsonify({"error": "Use a JPG, PNG, or WEBP prescription image."}), 400

    image_bytes = image.read()
    if not image_bytes or len(image_bytes) > 20 * 1024 * 1024:
        return jsonify({"error": "Choose an image smaller than 20 MB."}), 400

    prompt = """You are a careful prescription transcription assistant. Read this image.
Return JSON only, with this exact shape: {\"medicines\":[{\"name\":\"\",\"dose\":\"\",\"timing\":\"\",\"duration\":\"\"}]}.
Extract ONLY medicines that are explicitly written. Do not include patient details, diagnoses, advice, doctors, or invented medicines. Preserve uncertainty by using \"As prescribed\" for missing timing or duration. Do not provide medical advice."""
    payload = {
        "model": "qwen/qwen3.8-27b",
        "temperature": 0,
        "max_completion_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"}},
            ],
        }],
    }

    try:
        groq_request = Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(groq_request, timeout=35) as response:
            completion = json.loads(response.read().decode("utf-8"))
        content = completion["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return jsonify({"error": "AI image analysis could not read this prescription. You can still paste the text or try a clearer image."}), 502

    medicines = []
    for entry in result.get("medicines", []):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()[:80]
        if not name:
            continue
        medicines.append({
            "name": name,
            "dose": str(entry.get("dose") or "As prescribed").strip()[:40],
            "timing": str(entry.get("timing") or "As prescribed").strip()[:120],
            "duration": str(entry.get("duration") or "As prescribed").strip()[:80],
        })

    return jsonify({"medicines": medicines, "source": "Groq AI vision"})

@app.route("/api/parse", methods=["POST"])
@api_login_required
def parse_discharge():

    text = request.form.get("text", "").strip()

    if not text:

        return jsonify({
            "error": "Please enter discharge summary text."
        }), 400

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    medicines = []

    # Image OCR can confuse the "g" in mg with q, 9, or y. Keep the
    # displayed strength clinically readable after accepting those variants.
    def normalize_dose(dose):
        return re.sub(r"m[gq9y]\\b", "mg", dose.strip(), flags=re.I)

    non_medicine_terms = {
        "patient", "name", "age", "date", "diagnosis", "diagnoses", "advice",
        "follow up", "follow-up", "review", "discharge", "history", "blood",
        "pressure", "hospital", "doctor", "instruction", "warning"
    }
    medicine_forms = ("tab", "tablet", "cap", "capsule", "syrup", "suspension", "injection", "inj", "drops", "cream", "ointment")

    for line in lines:

        # Accept common typed/OCR prescription formats, for example:
        # "Tab. Aspirin 75mg OD", "Aspirin - 75 mg", or "1. Aspirin 75 mg".
        match = re.search(
            r"^(?:[-•*]|\d+[.)])?\s*"
            r"(?:(?:tab(?:let)?|cap(?:sule)?|syrup|inj(?:ection)?|drops?)\.?\s*)?"
            r"([A-Za-z][A-Za-z0-9+/' -]{1,40}?)\s*[-:,]?\s*"
            r"(\d+(?:\.\d+)?\s*(?:mcg|m[gq9y]|g|ml|iu|units?))\b\s*(.*)$",
            line,
            re.I
        )

        if match:

            name = match.group(1).strip()
            remainder = match.group(3).strip()
            normalized_name = name.lower()
            normalized_line = line.lower()

            # A medicine-strength pattern is strong evidence by itself. Only
            # discard obvious non-medicine headings or administrative fields.
            if normalized_name in non_medicine_terms or any(
                term in normalized_name for term in non_medicine_terms
            ):
                continue

            medicines.append({

                "name": name.strip(" -,:"),

                "dose": normalize_dose(match.group(2)),

                "timing":
                    remainder
                    or "As prescribed",

                "duration":
                    "As prescribed"
            })

    # OCR sometimes splits a prescription entry across a line break or reads
    # the leading number separately (e.g. "1. Paracetamol\n500 mg"). Search
    # the complete OCR text as a fallback for those otherwise-valid entries.
    # Always run a complete-text pass too. Image OCR often reads the first
    # prescription line cleanly but merges later numbered lines together.
    normalized_text = re.sub(r"[\r\n]+", " ", text)
    fallback_pattern = re.compile(
        r"(?:^|\s)(?:\d+[.)]\s*)?"
        r"(?:(?:tab(?:let)?|cap(?:sule)?|syrup|inj(?:ection)?|drops?)\.?\s*)?"
        r"([A-Za-z][A-Za-z+/' -]{1,36}?)\s+"
        r"(\d+(?:\.\d+)?\s*(?:mcg|m[gq9y]|g|ml|iu|units?))\b",
        re.I,
    )
    for match in fallback_pattern.finditer(normalized_text):
        name = match.group(1).strip(" -,:.")
        normalized_name = name.lower()
        if (
            normalized_name in non_medicine_terms
            or any(term in normalized_name for term in non_medicine_terms)
            or len(name) > 40
        ):
            continue
        medicines.append({
            "name": name,
            "dose": normalize_dose(match.group(2)),
            "timing": "As prescribed",
            "duration": "As prescribed",
        })

    # A catalogue pass recovers common medicine names when OCR damages a
    # strength (for example, it reads "10 mg" as "10 mq").
    for item in MEDICINE_CATALOG:
        medicine_name = item["name"]
        known_match = re.search(
            rf"\b{re.escape(medicine_name)}\b\s*[-,:]?\s*"
            r"(\d+(?:\.\d+)?\s*(?:mcg|m[gq9y]|g|ml|iu|units?))\b",
            normalized_text,
            re.I,
        )
        if known_match:
            medicines.append({
                "name": medicine_name,
                "dose": normalize_dose(known_match.group(1)),
                "timing": "As prescribed",
                "duration": "As prescribed",
            })

    # Preserve order while preventing duplicate OCR reads of the same entry.
    unique_medicines = []
    seen_medicines = set()
    for medicine in medicines:
        key = (medicine["name"].lower(), medicine["dose"].lower())
        if key not in seen_medicines:
            seen_medicines.add(key)
            unique_medicines.append(medicine)
    medicines = unique_medicines

    # Find follow-up
    follow_up = re.findall(
        r"(?:follow[- ]?up|review|appointment)"
        r"\s*[:\-]?\s*([A-Za-z0-9 ,/-]{4,40})",
        text,
        re.I
    )

    # Find warning symptoms
    warnings = []

    possible_warnings = [
        "chest pain",
        "breathing difficulty",
        "severe bleeding",
        "fainting",
        "high fever",
        "difficulty breathing"
    ]

    for warning in possible_warnings:

        if warning.lower() in text.lower():

            warnings.append(
                warning.title()
            )

    return jsonify({

        "summary": "Medicine-only draft generated from the prescription.",

        "medicines":
            medicines,

        "follow_up":
            follow_up[0].strip()
            if follow_up
            else
            "See discharge summary",

        "warning_signs":
            warnings
            if warnings
            else
            [
                "Severe or worsening symptoms",
                "Difficulty breathing",
                "Fainting or unusual confusion"
            ],

        "note":
            "Prototype only. Always verify extracted information against the original discharge summary and a healthcare professional."
    })


# =========================
# RESET DEMO
# =========================

@app.route("/api/reset-demo", methods=["POST"])
@api_login_required
def reset_demo():

    connection = get_db()

    patient_id = get_current_patient_id(connection)
    connection.execute("""
        UPDATE medicines
        SET taken = 0
        WHERE patient_id = ?
    """, (patient_id,))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================
# START SERVER
# =========================

# Initialise schema when served by Flask locally or by a production WSGI server.
init_db()

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000"))
    )
