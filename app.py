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
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB
app.secret_key = os.getenv("SECRET_KEY", "oralai_secret_2024")

app.config["SESSION_PERMANENT"]          = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
REPORT_DIR = "static/reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

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

# ── File-based phone session store ──
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


# ── HTML error/done helpers ───────────────────────────────────
def html_error(title, message, status=400):
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


def html_done(title, message):
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
    .icon{{font-size:64px;margin-bottom:16px;animation:popIn .5s cubic-bezier(.175,.885,.32,1.275) both;}}
    @keyframes popIn{{0%{{transform:scale(0);opacity:0}}100%{{transform:scale(1);opacity:1}}}}
    h1{{font-size:22px;font-weight:800;color:#22e88e;margin-bottom:10px;}}
    p{{color:#8a9bb5;font-size:14px;line-height:1.7;max-width:300px;}}
    .box{{margin-top:20px;background:rgba(34,232,142,0.08);border:1px solid rgba(34,232,142,0.25);
      border-radius:12px;padding:14px 18px;font-size:13px;color:#22e88e;max-width:320px;}}
    .logo{{font-size:20px;font-weight:800;margin-bottom:32px;}}
    .logo span{{color:#1a6fff;}}
  </style>
</head>
<body>
  <div class="logo">Oral<span>AI</span></div>
  <div class="icon">✅</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <div class="box">📋 The operator will now generate your AI dental report. Please wait at the clinic.</div>
</body>
</html>"""
    return html, 200


# ── Delete uploaded + YOLO result images for a screening ──────
def cleanup_old_files(screening_id):
    if not screening_id:
        return
    patterns = [
        os.path.join(UPLOAD_DIR, f"{screening_id}_*.jpg"),
        os.path.join(RESULT_DIR, f"{screening_id}_*.jpg"),
    ]
    deleted = 0
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"[Cleanup] Deleted: {f}")
                deleted += 1
            except Exception as e:
                print(f"[Cleanup] Could not delete {f}: {e}")
    print(f"[Cleanup] {deleted} file(s) removed for screening {screening_id[:8]}...")


# ════════════════════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/screening_count")
def screening_count():
    return jsonify({"count": get_screening_count()})


@app.route("/start")
def start():
    return render_template("start.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


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
            "face":         False,
            "upper":        False,
            "front":        False,
            "lower":        False,
            "face_thumb":   "",
            "upper_thumb":  "",
            "front_thumb":  "",
            "lower_thumb":  "",
            "expired":      False,
        })

        return redirect("/capture")
    return render_template("details.html")


# ════════════════════════════════════════════════════════════
#  CAPTURE PAGE
# ════════════════════════════════════════════════════════════
@app.route("/capture")
def capture_page():
    if not session.get("patient_name"):
        return redirect("/details")
    language      = session.get("language", "English")
    session_token = session.get("session_token", "")
    return render_template("capture.html", session_language=language, session_token=session_token)


# ════════════════════════════════════════════════════════════
#  PHONE CAPTURE PAGE
# ════════════════════════════════════════════════════════════
@app.route("/phone_capture")
def phone_capture():
    token = request.args.get("token", "").strip()

    if not token:
        return html_error(
            "Missing Session Token",
            "This link is incomplete. It must be opened by scanning the QR code shown at the clinic."
        )

    ps = get_phone_session(token)

    if not ps:
        return html_error(
            "Session Expired or Not Found",
            "This QR code session has expired or is no longer valid. Please ask the operator to start a new screening.",
            404
        )

    if ps.get("expired"):
        return html_done(
            "All Photos Received!",
            "All 4 photos have been successfully sent to the operator. You can return the phone."
        )

    language = ps.get("language", "English")
    return render_template("phone_capture.html", token=token, session_language=language)


@app.route("/phone_status")
def phone_status():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "missing token"}), 400

    ps = get_phone_session(token)
    if not ps:
        return jsonify({"error": "session not found"}), 404

    return jsonify({
        "face":        ps.get("face", False),
        "upper":       ps.get("upper", False),
        "front":       ps.get("front", False),
        "lower":       ps.get("lower", False),
        "face_thumb":  ps.get("face_thumb", ""),
        "upper_thumb": ps.get("upper_thumb", ""),
        "front_thumb": ps.get("front_thumb", ""),
        "lower_thumb": ps.get("lower_thumb", ""),
        "expired":     ps.get("expired", False),
    })


@app.route("/phone_expire", methods=["POST"])
def phone_expire():
    try:
        data  = request.get_json()
        token = data.get("token", "").strip()
        if not token:
            return jsonify({"status": "error", "msg": "missing token"}), 400

        ps = get_phone_session(token)
        if not ps:
            return jsonify({"status": "already_expired"})

        ps["expired"] = True
        save_phone_session(token, ps)
        return jsonify({"status": "expired"})

    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@app.route("/phone_save", methods=["POST"])
def phone_save():
    try:
        data       = request.get_json()
        token      = data.get("token", "").strip()
        image_type = data.get("type", "")
        image_b64  = data.get("image", "")

        if not token or image_type not in ("face", "upper", "front", "lower") or not image_b64:
            return jsonify({"status": "error", "msg": "bad params"}), 400

        ps = get_phone_session(token)
        if not ps:
            return jsonify({"status": "error", "msg": "session expired"}), 404

        if ps.get("expired"):
            return jsonify({"status": "error", "msg": "session already expired"}), 403

        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]

        image_bytes  = base64.b64decode(image_b64)
        screening_id = ps["screening_id"]
        image_path   = os.path.join(UPLOAD_DIR, f"{screening_id}_{image_type}.jpg")

        with open(image_path, "wb") as f:
            f.write(image_bytes)

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
        return jsonify(json.loads(clean))

    except json.JSONDecodeError:
        return jsonify({"isTeeth": True, "reason": "Validation inconclusive"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  SAVE CAPTURED IMAGE
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

    print(f"[Capture] Saved: {image_path}")
    return jsonify({"status": "saved"})


# ════════════════════════════════════════════════════════════
#  STEP 1 — CLAUDE VISION ANALYSIS (always in English)
# ════════════════════════════════════════════════════════════
def analyse_with_claude(yolo_image_paths, patient_info):
    try:
        age    = patient_info.get("age", "unknown")
        gender = patient_info.get("gender", "unknown")
        name   = patient_info.get("name", "Patient")

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

Patient: {name}, Age: {age}, Gender: {gender}

The images have green bounding boxes drawn by a YOLO model showing detected dental issues.

Write EXACTLY these 6 sections in English language. No markdown symbols (no **, ##, *, _). Use plain text with numbered sections and - bullet points only.

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
Use realistic Indian clinic prices.

6. CONCLUSION
Write exactly 3 warm sentences: summarise the overall oral health status, encourage {name} with what can be improved, and state the single most important first action to take now.

STRICT RULES:
- Write entire response in English only
- No markdown, no asterisks, no hashtags
- All 6 sections must be present
- Total response under 700 words
"""
        })

        print(f"[Claude] Sending 3 YOLO images for analysis in English...")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2500,
            system=(
                "You are a concise expert dental AI assistant. "
                "Always respond in English only. "
                "Never use markdown symbols like **, ##, *, _ in your response. "
                "Use plain text with numbered sections and simple - bullet points only. "
                "All 6 sections must be present. Be specific and informative but concise."
            ),
            messages=[{"role": "user", "content": content}]
        )

        analysis = message.content[0].text.strip()
        print(f"[Claude] English analysis done — {len(analysis)} chars")
        return analysis

    except Exception as e:
        print("Claude analysis error:", str(e))
        return None


# ════════════════════════════════════════════════════════════
#  STEP 2 — TRANSLATE English analysis to target language
# ════════════════════════════════════════════════════════════
def translate_analysis(english_text, target_language):
    """Translate English dental analysis to the target language using Claude."""
    if target_language == "English":
        return english_text

    try:
        print(f"[Translate] Translating to {target_language}...")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            system=(
                f"You are an expert translator specialising in medical and dental content. "
                f"Translate the given dental health report accurately into {target_language}. "
                f"STRICT RULES: "
                f"1. Translate EVERYTHING including section numbers and bullet points. "
                f"2. Keep the same structure — numbered sections, dash bullets. "
                f"3. Do NOT use any markdown (no **, ##, *, _). "
                f"4. Output ONLY the translated text, nothing else — no preamble, no explanation. "
                f"5. Preserve all numbers, prices (Rs. amounts), and medical/dental terms accurately. "
                f"6. Make the translation natural and easy to read for a patient."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Translate the following dental report to {target_language}. "
                    f"Output only the translated text:\n\n{english_text}"
                )
            }]
        )

        translated = message.content[0].text.strip()
        print(f"[Translate] Done — {len(translated)} chars in {target_language}")
        return translated

    except Exception as e:
        print(f"[Translate] Failed: {e} — falling back to English")
        return english_text


# ════════════════════════════════════════════════════════════
#  GENERATE REPORT
#  Pipeline: YOLO → Claude (English) → Translate → PDF
# ════════════════════════════════════════════════════════════
@app.route("/generate", methods=["POST"])
def generate():
    name     = session.get("patient_name", "")
    age      = session.get("patient_age", "25")
    gender   = session.get("patient_gender", "Other")
    phone    = session.get("patient_phone", "")
    email    = session.get("patient_email", "")
    language = session.get("language", "English")
    screening_id = session.get("screening_id", "")

    session_token = session.get("session_token", "")
    if session_token and not screening_id:
        ps = get_phone_session(session_token)
        if ps:
            screening_id = ps.get("screening_id", "")
            if screening_id:
                session["screening_id"] = screening_id
                session.modified = True

    if not name or not screening_id:
        return redirect("/details")

    print(f"[Generate] Starting: {name} | lang: {language} | id: {screening_id[:8]}...")

    patient_info = {
        "name":     name,
        "age":      age,
        "gender":   gender,
        "phone":    phone,
        "email":    email,
        "language": language,
    }

    with report_semaphore:

        # ── Step 1: Run YOLO on all 3 teeth images ─────────────
        all_detections  = []
        detected_labels = []
        yolo_paths      = {}

        for part in ["upper", "front", "lower"]:
            img_path = os.path.join(UPLOAD_DIR, f"{screening_id}_{part}.jpg")
            out_path = os.path.join(RESULT_DIR, f"{screening_id}_{part}_yolo.jpg")

            if not os.path.exists(img_path):
                print(f"[Generate] Missing image: {img_path}")
                return render_template("result.html", error="Missing images. Please capture again.")

            print(f"[YOLO] Running on {part} image...")
            detections = run_yolo(img_path, out_path)
            yolo_paths[part] = out_path

            if detections:
                all_detections.extend(detections)
                for d in detections:
                    if d["label"] not in detected_labels:
                        detected_labels.append(d["label"])
                print(f"[YOLO] {part}: {len(detections)} detection(s)")
            else:
                print(f"[YOLO] {part}: no detections")

        # ── Step 2: Generate recommendations ──────────────────
        recommendations = generate_recommendations(
            detections=all_detections,
            age=age,
            gender=gender
        )

        # ── Step 3: Claude analyses YOLO images — always English
        claude_analysis = analyse_with_claude(
            yolo_image_paths=yolo_paths,
            patient_info=patient_info
        )

        # ── Step 4: Translate to patient's language ────────────
        if claude_analysis and language != "English":
            claude_analysis = translate_analysis(claude_analysis, language)

        # ── Step 5: Build PDF ──────────────────────────────────
        report_id   = str(uuid.uuid4())
        report_path = generate_pdf(
            user_data=patient_info,
            detected_labels=detected_labels,
            report_id=report_id,
            recommendations=recommendations,
            claude_analysis=claude_analysis,
            screening_id=screening_id
        )
        print(f"[Generate] PDF created: {report_path}")

        # ── Step 6: Delete uploaded + YOLO images ─────────────
        cleanup_old_files(screening_id)

    session["report_path"] = report_path
    session["report_id"]   = report_id
    session.modified       = True

    if session_token:
        delete_phone_session(session_token)

    increment_screening_count()
    print(f"[Generate] Done — report_id: {report_id}")

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
        return message
    except Exception as e:
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
            </div>
            <div style="padding:28px;">
              <div style="text-align:center;font-size:32px;margin-bottom:8px;">{stars}</div>
              <div style="text-align:center;font-size:15px;font-weight:700;color:#1a6fff;margin-bottom:24px;">{rating} / 5 Stars</div>
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:120px;">Name</td><td style="font-size:14px;color:#0f172a;font-weight:700;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Contact</td><td style="font-size:14px;color:#0f172a;">{contact}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Used for</td><td style="font-size:14px;color:#1a6fff;">{rtype}</td></tr>
              </table>
              <div style="margin-top:20px;padding:18px;background:#f8fafc;border-radius:10px;border-left:4px solid #f5c842;">
                <p style="font-size:15px;color:#0f172a;line-height:1.8;margin:0;font-style:italic;">"{review}"</p>
              </div>
            </div>
          </div>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, EMAIL_USER, msg.as_string())

        return jsonify({"success": True})

    except Exception as e:
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
          <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;">
            <div style="background:#0a1628;padding:24px 28px;">
              <h2 style="color:#ffffff;margin:0;font-size:20px;">OralAI — New Contact Message</h2>
            </div>
            <div style="padding:28px;">
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:100px;">Name</td><td style="font-size:14px;color:#0f172a;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Email</td><td style="font-size:14px;color:#0f172a;">{email}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Phone</td><td style="font-size:14px;color:#0f172a;">{phone}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Subject</td><td style="font-size:14px;color:#1a6fff;">{subject}</td></tr>
              </table>
              <div style="margin-top:20px;padding:16px;background:#f8fafc;border-radius:10px;border-left:4px solid #1a6fff;">
                <p style="font-size:14px;color:#0f172a;line-height:1.7;margin:0;">{message}</p>
              </div>
            </div>
          </div>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, DEVELOPER_EMAIL, msg.as_string())

        return jsonify({"success": True})

    except smtplib.SMTPAuthenticationError:
        return jsonify({"success": False, "error": "Email configuration error."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
#  RUN APP
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)