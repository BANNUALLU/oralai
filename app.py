from flask import Flask, render_template, request, redirect, send_file, jsonify, session
import base64
import os
import uuid
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import anthropic

from detect import run_yolo
from report_generator import generate_pdf
from email_sender import send_report
from ai_recommendation import generate_recommendations
from whatsapp_sender import send_whatsapp_report

app = Flask(__name__)
app.secret_key = "oralai_secret_2024"

user_data = {}

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
REPORT_DIR = "static/reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ── Anthropic client ──────────────────────────────────────
client = anthropic.Anthropic(api_key="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")

# ── Email config ──────────────────────────────────────────
EMAIL_USER      = os.getenv("EMAIL_USER", "oralai.site@gmail.com")
EMAIL_PASS      = os.getenv("EMAIL_PASS", "ykfiyejpuqqypiez")
DEVELOPER_EMAIL = "bannuallu123@gmail.com"


# ════════════════════════════════════════════════════════════
#  HOME PAGE
# ════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


# ════════════════════════════════════════════════════════════
#  START PAGE
# ════════════════════════════════════════════════════════════
@app.route("/start")
def start():
    return render_template("start.html")


# ════════════════════════════════════════════════════════════
#  DETAILS PAGE
# ════════════════════════════════════════════════════════════
@app.route("/details", methods=["GET", "POST"])
def details():
    if request.method == "POST":
        user_data.clear()
        user_data.update(request.form)
        session["language"] = request.form.get("language", "English")
        return redirect("/capture")
    return render_template("details.html")


# ════════════════════════════════════════════════════════════
#  CAPTURE PAGE
# ════════════════════════════════════════════════════════════
@app.route("/capture")
def capture_page():
    language = session.get("language", "English")
    return render_template("capture.html", session_language=language)


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
#  SAVE CAPTURED IMAGE
# ════════════════════════════════════════════════════════════
@app.route("/capture", methods=["POST"])
def capture_image():
    data         = request.get_json()
    image_type   = data["type"]
    image_base64 = data["image"].split(",")[1]
    image_bytes  = base64.b64decode(image_base64)
    image_path   = os.path.join(UPLOAD_DIR, f"{image_type}.jpg")
    with open(image_path, "wb") as f:
        f.write(image_bytes)
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
                content.append({"type": "text", "text": f"Image {i+1} — {label}:"})
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
            "text": f"""
You are an expert dental AI assistant reviewing 3 dental images for a patient.

Patient Info:
- Name: {name}
- Age: {age}
- Gender: {gender}
- Preferred Language: {language}

The images have green bounding boxes drawn by a YOLO model showing detected dental issues.

IMPORTANT: Write your ENTIRE response in {language} language only.

Please analyse all 3 images carefully and provide:
1. OVERALL SUMMARY: A 2-3 sentence friendly overview of the patient's oral health.
2. IMAGE-BY-IMAGE FINDINGS: For each image (Upper, Front, Lower), describe what you see.
3. KEY CONCERNS: List the most important issues found (if any).
4. PERSONALISED ADVICE: Give specific advice based on age ({age}) and gender ({gender}).
5. URGENCY LEVEL: Rate as Routine / Soon (within 1 month) / Urgent (within 1 week).

Write in a warm, professional, easy-to-understand tone.
Use bullet points where helpful.
"""
        })

        print(f"Sending 3 YOLO images to Claude for analysis in {language}...")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=(
                f"You are a friendly expert dental AI assistant. "
                f"Always respond in {language} language as requested."
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
    if not user_data:
        return redirect("/details")

    age      = user_data.get("age", "25")
    gender   = user_data.get("gender", "Other")
    language = user_data.get("language", "English")

    print(f"Report language: {language}")

    all_detections  = []
    detected_labels = []
    yolo_paths      = {}

    for part in ["upper", "front", "lower"]:
        img_path = f"{UPLOAD_DIR}/{part}.jpg"
        out_path = f"{RESULT_DIR}/{part}_yolo.jpg"

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
        patient_info=user_data
    )

    report_id   = str(uuid.uuid4())[:8]
    report_path = generate_pdf(
        user_data=user_data,
        detected_labels=detected_labels,
        report_id=report_id,
        recommendations=recommendations,
        claude_analysis=claude_analysis
    )

    user_data["report_path"] = report_path
    user_data["report_id"]   = report_id

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
#  SEND EMAIL (report to patient)
# ════════════════════════════════════════════════════════════
@app.route("/send_email", methods=["POST"])
def send_email_route():
    email       = user_data.get("email")
    report_path = user_data.get("report_path")
    if not email or not report_path:
        return "Email or report missing."
    try:
        send_report(email, report_path)
        return "Email sent successfully!"
    except Exception as e:
        return f"Email failed: {str(e)}"


# ════════════════════════════════════════════════════════════
#  SEND WHATSAPP
# ════════════════════════════════════════════════════════════
@app.route("/send_whatsapp", methods=["POST"])
def send_whatsapp_route():
    print("WhatsApp send requested...")

    phone       = user_data.get("phone", "").strip()
    name        = user_data.get("name", "Patient")
    report_id   = user_data.get("report_id", "")
    report_path = user_data.get("report_path", "")

    if not phone:
        return "No phone number found. Please re-enter patient details."
    if not report_id or not report_path:
        return "Report not found. Please generate the report first."
    if not os.path.exists(report_path):
        return "Report file missing on server."

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
        return f"WhatsApp failed: {str(e)}"


# ════════════════════════════════════════════════════════════
#  CONTACT FORM (sends email to developer)
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
        msg["Subject"] = f"OralAI Contact: {subject}"
        msg["From"]    = EMAIL_USER
        msg["To"]      = DEVELOPER_EMAIL
        msg["Reply-To"] = email

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
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
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        print(f"Using EMAIL_USER: {EMAIL_USER}")
        print(f"Using EMAIL_PASS length: {len(EMAIL_PASS)}")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            print("Login success!")
            server.sendmail(EMAIL_USER, DEVELOPER_EMAIL, msg.as_string())
            print("Email sent!")

        print(f"Contact email sent from {name} ({email})")
        return jsonify({"success": True})

    except smtplib.SMTPAuthenticationError as e:
        print(f"AUTH ERROR: {e}")
        return jsonify({"success": False, "error": f"Auth failed: {str(e)}"})
    except Exception as e:
        print(f"Contact form error: {e}")
        return jsonify({"success": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
#  RUN APP
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)