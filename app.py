from flask import Flask, render_template, request, redirect, send_file, jsonify, session
import base64
import os
import uuid
import json
import glob
import smtplib
import threading
from datetime import timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import anthropic

from detect import run_yolo
from report_generator import generate_pdf
from email_sender import send_report
from ai_recommendation import generate_recommendations
from whatsapp_sender import send_whatsapp_report

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "oralai_secret_2024")

app.config["SESSION_PERMANENT"]          = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
REPORT_DIR = "static/reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Max 3 simultaneous report generations — others wait, never crash
report_semaphore = threading.Semaphore(3)

# ── Screening counter ─────────────────────────────────────────
COUNTER_FILE  = "static/screening_count.txt"
COUNTER_START = 50

def get_screening_count():
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r") as f:
                return int(f.read().strip())
        return COUNTER_START
    except:
        return COUNTER_START

def increment_screening_count():
    count = get_screening_count() + 1
    try:
        with open(COUNTER_FILE, "w") as f:
            f.write(str(count))
    except:
        pass
    return count

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

EMAIL_USER      = os.getenv("EMAIL_USER", "oralai.site@gmail.com")
EMAIL_PASS      = os.getenv("EMAIL_PASS", "")
DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL", "bannuallu123@gmail.com")

# ── File-based phone session store (works across all Gunicorn workers) ──
PHONE_SESSIONS_DIR = "static/phone_sessions"
os.makedirs(PHONE_SESSIONS_DIR, exist_ok=True)
phone_sessions_lock = threading.Lock()


def get_phone_session(token):
    path = os.path.join(PHONE_SESSIONS_DIR, f"{token}.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_phone_session(token, data):
    path = os.path.join(PHONE_SESSIONS_DIR, f"{token}.json")
    with open(path, "w") as f:
        json.dump(data, f)


def delete_phone_session(token):
    path = os.path.join(PHONE_SESSIONS_DIR, f"{token}.json")
    try:
        os.remove(path)
    except Exception:
        pass


# ── HTML error page helper ────────────────────────────────────
def html_error(title, message, status=400):
    """Return a styled HTML error page instead of plain text."""
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OralAI — {title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:'Segoe UI',sans-serif;background:#0a1628;color:#fff;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      min-height:100vh;padding:24px;text-align:center;}}
    .icon{{font-size:56px;margin-bottom:16px;}}
    h1{{font-size:22px;font-weight:800;color:#ef4444;margin-bottom:10px;}}
    p{{color:#8a9bb5;font-size:14px;line-height:1.7;max-width:300px;}}
    .box{{margin-top:20px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);
      border-radius:12px;padding:14px 18px;font-size:13px;color:#ef4444;max-width:320px;}}
    .logo{{font-size:20px;font-weight:800;margin-bottom:32px;}}
    .logo span{{color:#1a6fff;}}
  </style>
</head>
<body>
  <div class="logo">Oral<span>AI</span></div>
  <div class="icon">⚠️</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <div class="box">Please ask the operator to show the QR code again and scan it with your camera.</div>
</body>
</html>"""
    return html, status


# ════════════════════════════════════════════════════════════
#  HELPER — Delete all files for a given screening_id
# ════════════════════════════════════════════════════════════
def cleanup_old_files(screening_id):
    if not screening_id:
        return
    patterns = [
        os.path.join(UPLOAD_DIR, f"{screening_id}_*.jpg"),
        os.path.join(RESULT_DIR, f"{screening_id}_*.jpg"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"Deleted old file: {f}")
            except Exception as e:
                print(f"Could not delete {f}: {e}")


# ════════════════════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


# ════════════════════════════════════════════════════════════
#  SCREENING COUNT API
# ════════════════════════════════════════════════════════════
@app.route("/screening_count")
def screening_count():
    return jsonify({"count": get_screening_count()})


# ════════════════════════════════════════════════════════════
#  START
# ════════════════════════════════════════════════════════════
@app.route("/start")
def start():
    return render_template("start.html")


# ════════════════════════════════════════════════════════════
#  DETAILS
# ════════════════════════════════════════════════════════════
@app.route("/details", methods=["GET", "POST"])
def details():
    if request.method == "POST":
        old_screening_id = session.get("screening_id")
        if old_screening_id:
            cleanup_old_files(old_screening_id)

        session.clear()

        session["patient_name"]   = request.form.get("name", "").strip()
        session["patient_age"]    = request.form.get("age", "").strip()
        session["patient_gender"] = request.form.get("gender", "").strip()
        session["patient_phone"]  = request.form.get("phone", "").strip()
        session["patient_email"]  = request.form.get("email", "").strip()
        session["language"]       = request.form.get("language", "English").strip()
        session["screening_id"]   = str(uuid.uuid4())
        session["session_token"]  = str(uuid.uuid4())

        session.permanent = True
        session.modified  = True

        token = session["session_token"]
        save_phone_session(token, {
            "screening_id": session["screening_id"],
            "language":     session["language"],
            "upper":        False,
            "front":        False,
            "lower":        False,
            "upper_thumb":  "",
            "front_thumb":  "",
            "lower_thumb":  "",
        })

        return redirect("/capture")
    return render_template("details.html")


# ════════════════════════════════════════════════════════════
#  CAPTURE PAGE (laptop/desktop)
# ════════════════════════════════════════════════════════════
@app.route("/capture")
def capture_page():
    if not session.get("patient_name"):
        return redirect("/details")
    language      = session.get("language", "English")
    session_token = session.get("session_token", "")
    return render_template("capture.html", session_language=language, session_token=session_token)


# ════════════════════════════════════════════════════════════
#  PHONE CAPTURE PAGE  (patient opens on phone via QR)
# ════════════════════════════════════════════════════════════
@app.route("/phone_capture")
def phone_capture():
    token = request.args.get("token", "").strip()

    # ── No token at all — user opened URL without QR ──
    if not token:
        print("phone_capture: no token in request")
        return html_error(
            "Missing Session Token",
            "This link is incomplete. It must be opened by scanning the QR code shown at the clinic, not typed manually."
        )

    ps = get_phone_session(token)

    # ── Token not found on disk ──
    if not ps:
        print(f"phone_capture: token not found: {token[:8]}...")
        return html_error(
            "Session Expired or Not Found",
            "This QR code session has expired or is no longer valid. Please ask the operator to start a new screening.",
            404
        )

    language = ps.get("language", "English")
    print(f"phone_capture: valid session for screening {ps.get('screening_id', '?')[:8]}, lang={language}")
    return render_template("phone_capture.html", token=token, session_language=language)


# ════════════════════════════════════════════════════════════
#  PHONE STATUS  (laptop polls this to check photo progress)
# ════════════════════════════════════════════════════════════
@app.route("/phone_status")
def phone_status():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "missing token"}), 400

    ps = get_phone_session(token)

    if not ps:
        return jsonify({"error": "session not found"}), 404

    return jsonify({
        "upper":       ps["upper"],
        "front":       ps["front"],
        "lower":       ps["lower"],
        "upper_thumb": ps["upper_thumb"],
        "front_thumb": ps["front_thumb"],
        "lower_thumb": ps["lower_thumb"],
    })


# ════════════════════════════════════════════════════════════
#  PHONE CAPTURE SAVE  (phone POSTs images here)
# ════════════════════════════════════════════════════════════
@app.route("/phone_save", methods=["POST"])
def phone_save():
    try:
        data       = request.get_json()
        token      = data.get("token", "").strip()
        image_type = data.get("type", "")
        image_b64  = data.get("image", "")

        if not token or image_type not in ("upper", "front", "lower") or not image_b64:
            return jsonify({"status": "error", "msg": "bad params"}), 400

        ps = get_phone_session(token)

        if not ps:
            return jsonify({"status": "error", "msg": "session expired"}), 404

        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]

        image_bytes  = base64.b64decode(image_b64)
        screening_id = ps["screening_id"]
        image_path   = os.path.join(UPLOAD_DIR, f"{screening_id}_{image_type}.jpg")

        with open(image_path, "wb") as f:
            f.write(image_bytes)

        print(f"[Phone] Saved {image_type} image for screening {screening_id}")

        thumb_b64 = "data:image/jpeg;base64," + image_b64

        with phone_sessions_lock:
            ps = get_phone_session(token) or ps
            ps[image_type]            = True
            ps[image_type + "_thumb"] = thumb_b64
            save_phone_session(token, ps)

        return jsonify({"status": "saved"})

    except Exception as e:
        print("PHONE_SAVE ERROR:", str(e))
        return jsonify({"status": "error", "msg": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  VALIDATE IMAGE
# ════════════════════════════════════════════════════════════
@app.route("/validate", methods=["POST"])
def validate():
    try:
        data      = request.get_json()
        image_b64 = data.get("image", "")

        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]

        print("Validating image with Claude...")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=(
                "You are a dental image validator. "
                "Check whether the image shows human teeth (upper, lower, or front view). "
                "Reply with ONLY raw JSON, no markdown:\n"
                '{"isTeeth": true, "reason": "Teeth visible"}\n'
                "or\n"
                '{"isTeeth": false, "reason": "No teeth visible"}'
            ),
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64
                        }
                    },
                    {"type": "text", "text": "Does this image show human teeth? Reply only with raw JSON."}
                ]
            }]
        )

        raw   = message.content[0].text.strip()
        clean = raw.replace("```json", "").replace("```", "").strip()
        print("Claude validation:", clean)
        return jsonify(json.loads(clean))

    except json.JSONDecodeError:
        return jsonify({"isTeeth": True, "reason": "Validation inconclusive"})
    except Exception as e:
        print("VALIDATE ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  SAVE CAPTURED IMAGE  (local camera mode)
# ════════════════════════════════════════════════════════════
@app.route("/capture", methods=["POST"])
def capture_image():
    data         = request.get_json()
    image_type   = data["type"]
    image_base64 = data["image"].split(",")[1]
    image_bytes  = base64.b64decode(image_base64)

    screening_id = session.get("screening_id", "default")
    image_path   = os.path.join(UPLOAD_DIR, f"{screening_id}_{image_type}.jpg")

    with open(image_path, "wb") as f:
        f.write(image_bytes)

    print(f"Saved image: {image_path}")
    return jsonify({"status": "saved"})


# ════════════════════════════════════════════════════════════
#  CLAUDE VISION ANALYSIS
# ════════════════════════════════════════════════════════════
def analyse_with_claude(yolo_image_paths, patient_info):
    try:
        age      = patient_info.get("age", "unknown")
        gender   = patient_info.get("gender", "unknown")
        name     = patient_info.get("name", "Patient")
        language = patient_info.get("language", "English")

        content = []
        labels  = ["Upper Teeth", "Front Teeth", "Lower Teeth"]
        paths   = [
            yolo_image_paths.get("upper"),
            yolo_image_paths.get("front"),
            yolo_image_paths.get("lower"),
        ]

        for i, (path, label) in enumerate(zip(paths, labels)):
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                content.append({"type": "text", "text": f"Image {i+1} - {label}:"})
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_b64
                    }
                })

        content.append({
            "type": "text",
            "text": f"""You are an expert dental AI assistant reviewing 3 dental images for a patient.

Patient: {name}, Age: {age}, Gender: {gender}, Language: {language}

The images have green bounding boxes drawn by a YOLO model showing detected dental issues.

Write EXACTLY these 6 sections in {language} language. No markdown symbols (no **, ##, *, _). Use plain text with numbered sections and - bullet points only.

1. DETECTED PROBLEMS
For each detected problem write one bullet like this:
- [Condition name] | Area: [upper/front/lower teeth] | Observed: [what is visually seen - color, position, shape, texture in 1-2 lines] | Affected teeth: [estimate which teeth eg. front 2, molars, gumline] | Confidence: [High/Medium/Low] | Risk: [why this needs attention in 1 line]
List max 4 problems actually seen. Be specific about what the AI saw visually.

2. PROBLEM STATUS
For each problem write one bullet like this:
- [Condition name]: [Starting/Middle/Advanced] Stage | Signs: [2-3 visible signs that indicate this stage] | Est. duration: [how long it may have been developing] | If untreated: [what will happen in 1 line]
Be detailed — explain WHY it is at that stage based on visual evidence.

3. SUGGESTIONS TO OVERCOME
For each problem write one bullet:
- [Condition name]: Dentist: [specific treatment needed] | Urgency: [Routine/Soon/Urgent] | Home: [2 specific tips] | Avoid: [1 thing to avoid] | Tip: [1 motivating tip]

4. MONTHLY RECOVERY PLAN
Month 1: [clinic action] + [home routine] | Products: [2 specific Indian products with prices eg. Colgate Total Rs.120, Oral-B brush Rs.250]
Month 2: [clinic action] + [home routine] | Products: [2 specific Indian products with prices]
Month 3: [clinic action] + [home routine] | Products: [2 specific Indian products with prices]

5. TOTAL COST ESTIMATE
Write a detailed cost breakdown:
- [Condition 1 treatment]: Rs.[min]-Rs.[max] (eg. Scaling & Polishing: Rs.800-Rs.1500)
- [Condition 2 treatment]: Rs.[min]-Rs.[max]
- [Condition 3 treatment if any]: Rs.[min]-Rs.[max]
- Monthly dental products: Rs.[amount] per month (list 2-3 products with prices)
- One-time product cost: Rs.[amount] (eg. electric toothbrush, flosser)
- Budget option total: Rs.[min]-Rs.[max]
- Standard option total: Rs.[min]-Rs.[max]
Use realistic Indian clinic prices. Keep affordable — not too high, not too low.

6. CONCLUSION
Write exactly 3 warm sentences: summarise the overall oral health status, encourage {name} with what can be improved, and state the single most important first action to take now.

STRICT RULES:
- Write entire response in {language} only
- No markdown, no asterisks, no hashtags
- All 6 sections must be present
- Total response under 700 words
"""
        })

        print(f"Sending 3 YOLO images to Claude for analysis in {language}...")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2500,
            system=(
                f"You are a concise expert dental AI assistant. "
                f"Always respond in {language} language only. "
                f"Never use markdown symbols like **, ##, *, _ in your response. "
                f"Use plain text with numbered sections and simple - bullet points only. "
                f"All 6 sections must be present. Be specific and informative but concise."
            ),
            messages=[{"role": "user", "content": content}]
        )

        analysis = message.content[0].text.strip()
        print(f"Claude analysis done in {language}!")
        return analysis

    except Exception as e:
        print("Claude analysis error:", str(e))
        return None


# ════════════════════════════════════════════════════════════
#  GENERATE REPORT
# ════════════════════════════════════════════════════════════
@app.route("/generate", methods=["POST"])
def generate():
    name         = session.get("patient_name", "")
    age          = session.get("patient_age", "25")
    gender       = session.get("patient_gender", "Other")
    phone        = session.get("patient_phone", "")
    email        = session.get("patient_email", "")
    language     = session.get("language", "English")
    screening_id = session.get("screening_id", "")

    if not name or not screening_id:
        return redirect("/details")

    print(f"Generating report for: {name}, language: {language}, screening: {screening_id}")

    patient_info = {
        "name":     name,
        "age":      age,
        "gender":   gender,
        "phone":    phone,
        "email":    email,
        "language": language,
    }

    with report_semaphore:
        print(f"Report slot acquired for: {name}")

        all_detections  = []
        detected_labels = []
        yolo_paths      = {}

        for part in ["upper", "front", "lower"]:
            img_path = os.path.join(UPLOAD_DIR, f"{screening_id}_{part}.jpg")
            out_path = os.path.join(RESULT_DIR, f"{screening_id}_{part}_yolo.jpg")

            if not os.path.exists(img_path):
                return render_template("result.html", error="Missing images. Please capture again.")

            detections = run_yolo(img_path, out_path)
            yolo_paths[part] = out_path

            if detections:
                all_detections.extend(detections)
                for d in detections:
                    if d["label"] not in detected_labels:
                        detected_labels.append(d["label"])

        recommendations = generate_recommendations(
            detections=all_detections,
            age=age,
            gender=gender
        )

        claude_analysis = analyse_with_claude(
            yolo_image_paths=yolo_paths,
            patient_info=patient_info
        )

        report_id   = str(uuid.uuid4())
        report_path = generate_pdf(
            user_data=patient_info,
            detected_labels=detected_labels,
            report_id=report_id,
            recommendations=recommendations,
            claude_analysis=claude_analysis,
            screening_id=screening_id
        )

        cleanup_old_files(screening_id)
        print(f"Report slot released for: {name}")

    session["report_path"] = report_path
    session["report_id"]   = report_id
    session.modified       = True

    token = session.get("session_token", "")
    if token:
        delete_phone_session(token)

    increment_screening_count()

    return render_template("result.html", success=True, report_id=report_id)


# ════════════════════════════════════════════════════════════
#  DOWNLOAD REPORT
# ════════════════════════════════════════════════════════════
@app.route("/report/<report_id>")
def view_report(report_id):
    report_path = f"{REPORT_DIR}/{report_id}.pdf"
    if not os.path.exists(report_path):
        return "Report not found"
    return send_file(report_path, as_attachment=True, download_name="OralAI_Report.pdf")


# ════════════════════════════════════════════════════════════
#  SEND EMAIL
# ════════════════════════════════════════════════════════════
@app.route("/send_email", methods=["POST"])
def send_email_route():
    email       = session.get("patient_email", "").strip()
    report_path = session.get("report_path", "")
    report_id   = session.get("report_id", "")

    if not report_path and report_id:
        report_path = f"{REPORT_DIR}/{report_id}.pdf"

    if not email:
        return "❌ Patient email not found. Please start a new screening."
    if not report_path or not os.path.exists(report_path):
        return "❌ Report not found. Please generate the report first."

    try:
        send_report(email, report_path)
        return "✅ Report sent successfully to " + email
    except Exception as e:
        return f"❌ Email failed: {str(e)}"


# ════════════════════════════════════════════════════════════
#  SEND WHATSAPP
# ════════════════════════════════════════════════════════════
@app.route("/send_whatsapp", methods=["POST"])
def send_whatsapp_route():
    print("WhatsApp send requested...")

    phone       = session.get("patient_phone", "").strip()
    name        = session.get("patient_name", "Patient")
    report_id   = session.get("report_id", "")
    report_path = session.get("report_path", "")

    if not report_path and report_id:
        report_path = f"{REPORT_DIR}/{report_id}.pdf"

    if not phone:
        return "❌ No phone number found. Please re-enter patient details."
    if not report_id or not report_path:
        return "❌ Report not found. Please generate the report first."
    if not os.path.exists(report_path):
        return "❌ Report file missing on server."

    try:
        success, message = send_whatsapp_report(
            phone_number=phone,
            patient_name=name,
            report_id=report_id,
            report_path=report_path
        )
        if success:
            print(f"WhatsApp sent to {phone}")
            return f"{message}"
        else:
            print(f"WhatsApp failed: {message}")
            return f"{message}"

    except Exception as e:
        print(f"WhatsApp exception: {str(e)}")
        return f"❌ WhatsApp failed: {str(e)}"


# ════════════════════════════════════════════════════════════
#  REVIEW FORM
# ════════════════════════════════════════════════════════════
@app.route("/review", methods=["POST"])
def review():
    try:
        data    = request.get_json()
        name    = data.get("name", "Anonymous")
        contact = data.get("contact", "N/A")
        review  = data.get("review", "")
        rtype   = data.get("type", "General")
        rating  = data.get("rating", "N/A")
        stars   = data.get("stars", "")

        if not review.strip():
            return jsonify({"success": False, "error": "Review cannot be empty."})

        msg = MIMEMultipart("alternative")
        msg["Subject"]  = f"⭐ OralAI Review ({rating}/5) — {name}"
        msg["From"]     = EMAIL_USER
        msg["To"]       = EMAIL_USER

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
            <div style="background:#0a1628;padding:24px 28px;">
              <h2 style="color:#ffffff;margin:0;font-size:20px;">⭐ New OralAI Review</h2>
              <p style="color:#8a9bb5;margin:4px 0 0;font-size:13px;">Submitted from the OralAI website</p>
            </div>
            <div style="padding:28px;">
              <div style="text-align:center;font-size:32px;margin-bottom:8px;letter-spacing:4px;">{stars}</div>
              <div style="text-align:center;font-size:15px;font-weight:700;color:#1a6fff;margin-bottom:24px;">{rating} / 5 Stars</div>
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:120px;font-weight:600;">Name</td><td style="padding:8px 0;font-size:14px;color:#0f172a;font-weight:700;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;font-weight:600;">Contact</td><td style="padding:8px 0;font-size:14px;color:#0f172a;">{contact}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;font-weight:600;">Used for</td><td style="padding:8px 0;font-size:14px;color:#1a6fff;font-weight:600;">{rtype}</td></tr>
              </table>
              <div style="margin-top:20px;padding:18px;background:#f8fafc;border-radius:10px;border-left:4px solid #f5c842;">
                <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Review</div>
                <p style="font-size:15px;color:#0f172a;line-height:1.8;margin:0;font-style:italic;">"{review}"</p>
              </div>
            </div>
            <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0;">
              <p style="font-size:12px;color:#94a3b8;margin:0;">OralAI — AI Oral Health Screening | www.oralai.site</p>
            </div>
          </div>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, EMAIL_USER, msg.as_string())

        print(f"Review received from {name} — {rating}/5 stars")
        return jsonify({"success": True})

    except smtplib.SMTPAuthenticationError:
        return jsonify({"success": False, "error": "Email config error."})
    except Exception as e:
        print(f"Review error: {e}")
        return jsonify({"success": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
#  CONTACT FORM
# ════════════════════════════════════════════════════════════
@app.route("/contact", methods=["POST"])
def contact():
    try:
        data    = request.get_json()
        name    = data.get("name", "Unknown")
        phone   = data.get("phone", "N/A")
        email   = data.get("email", "N/A")
        subject = data.get("subject", "General Inquiry")
        message = data.get("message", "")

        if not message.strip():
            return jsonify({"success": False, "error": "Message cannot be empty."})

        msg = MIMEMultipart("alternative")
        msg["Subject"]  = f"OralAI Contact: {subject}"
        msg["From"]     = EMAIL_USER
        msg["To"]       = DEVELOPER_EMAIL
        msg["Reply-To"] = email

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
            <div style="background:#0a1628;padding:24px 28px;">
              <h2 style="color:#ffffff;margin:0;font-size:20px;">OralAI — New Contact Message</h2>
              <p style="color:#8a9bb5;margin:4px 0 0;font-size:13px;">Received from the OralAI website contact form</p>
            </div>
            <div style="padding:28px;">
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:100px;font-weight:600;">Name</td><td style="padding:8px 0;font-size:14px;color:#0f172a;font-weight:600;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;font-weight:600;">Email</td><td style="padding:8px 0;font-size:14px;color:#0f172a;">{email}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;font-weight:600;">Phone</td><td style="padding:8px 0;font-size:14px;color:#0f172a;">{phone}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;font-weight:600;">Subject</td><td style="padding:8px 0;font-size:14px;color:#1a6fff;font-weight:600;">{subject}</td></tr>
              </table>
              <div style="margin-top:20px;padding:16px;background:#f8fafc;border-radius:10px;border-left:4px solid #1a6fff;">
                <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Message</div>
                <p style="font-size:14px;color:#0f172a;line-height:1.7;margin:0;">{message}</p>
              </div>
              <div style="margin-top:16px;padding:12px 16px;background:#fffbeb;border-radius:8px;border:1px solid #fde68a;">
                <p style="font-size:12px;color:#78350f;margin:0;">Reply to this email to respond to {name} at {email}</p>
              </div>
            </div>
            <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0;">
              <p style="font-size:12px;color:#94a3b8;margin:0;">OralAI — AI Oral Health Screening | www.oralai.site</p>
            </div>
          </div>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, DEVELOPER_EMAIL, msg.as_string())

        print(f"Contact email sent from {name} ({email})")
        return jsonify({"success": True})

    except smtplib.SMTPAuthenticationError:
        print("Gmail auth failed — check EMAIL_USER and EMAIL_PASS env vars")
        return jsonify({"success": False, "error": "Email configuration error. Please contact us directly."})
    except Exception as e:
        print(f"Contact form error: {e}")
        return jsonify({"success": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
#  RUN APP
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)