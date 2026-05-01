from flask import Flask, render_template, request, redirect, send_file, jsonify, session
import base64
import os
import uuid
import json
import glob
import smtplib
import threading
import traceback
import urllib.parse
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

# ── In-memory status (per-worker fallback) ────────────────────
report_status = {}

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

# ── Doctor email — set this in your .env file ─────────────────
DOCTOR_EMAIL = os.getenv("DOCTOR_EMAIL", "doctor@hospital.com")

# ── WhatsApp helper friend email — set in .env ────────────────
WHATSAPP_HELPER_EMAIL = os.getenv("WHATSAPP_HELPER_EMAIL", "")

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


# ── Disk helpers — work across ALL gunicorn workers ───────────
def report_pdf_path(report_id):
    return os.path.join(REPORT_DIR, f"{report_id}.pdf")

def report_marker_path(report_id):
    return os.path.join(REPORT_DIR, f"{report_id}.processing")

def report_error_path(report_id):
    return os.path.join(REPORT_DIR, f"{report_id}.error")

def report_is_done(report_id):
    return os.path.exists(report_pdf_path(report_id))


# ════════════════════════════════════════════════════════════
#  AUTO EMAIL TO DOCTOR — fires automatically after report ready
# ════════════════════════════════════════════════════════════
def send_report_to_doctor(patient_info, report_path, report_id):
    """
    Automatically sends the report to the doctor as soon as it's ready.
    No button needed — fires from background thread.
    """
    try:
        doctor_email = DOCTOR_EMAIL
        if not doctor_email or doctor_email == "doctor@hospital.com":
            print("[Doctor Email] DOCTOR_EMAIL not set in .env — skipping")
            return

        if not os.path.exists(report_path):
            print(f"[Doctor Email] Report file not found: {report_path}")
            return

        name   = patient_info.get("name", "Patient")
        age    = patient_info.get("age", "N/A")
        gender = patient_info.get("gender", "N/A")
        phone  = patient_info.get("phone", "N/A")
        email  = patient_info.get("email", "N/A")
        lang   = patient_info.get("language", "English")

        from email.mime.base import MIMEBase
        from email import encoders
        from datetime import datetime

        msg = MIMEMultipart()
        msg["From"]    = f"OralAI <{EMAIL_USER}>"
        msg["To"]      = doctor_email
        msg["Subject"] = f"🦷 New Patient Report — {name} | OralAI Screening"

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

            <!-- Header -->
            <div style="background:#0a1628;padding:24px 28px;">
              <h2 style="color:#ffffff;margin:0;font-size:20px;">🦷 New Patient Report Ready</h2>
              <p style="color:#8a9bb5;margin:6px 0 0;font-size:13px;">OralAI — AI Oral Health Screening System</p>
            </div>

            <!-- Alert Banner -->
            <div style="background:#1a6fff;padding:12px 28px;">
              <p style="color:#ffffff;margin:0;font-size:13px;font-weight:600;">
                📋 A new patient screening has been completed. Report is attached below.
              </p>
            </div>

            <!-- Patient Details -->
            <div style="padding:28px;">
              <h3 style="font-size:16px;color:#0f172a;margin:0 0 16px;">Patient Information</h3>

              <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:10px;overflow:hidden;">
                <tr style="border-bottom:1px solid #e2e8f0;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;width:140px;font-weight:600;">Patient Name</td>
                  <td style="padding:12px 16px;font-size:14px;color:#0f172a;font-weight:700;">{name}</td>
                </tr>
                <tr style="border-bottom:1px solid #e2e8f0;background:#ffffff;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Age</td>
                  <td style="padding:12px 16px;font-size:14px;color:#0f172a;">{age} years</td>
                </tr>
                <tr style="border-bottom:1px solid #e2e8f0;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Gender</td>
                  <td style="padding:12px 16px;font-size:14px;color:#0f172a;">{gender}</td>
                </tr>
                <tr style="border-bottom:1px solid #e2e8f0;background:#ffffff;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Phone</td>
                  <td style="padding:12px 16px;font-size:14px;color:#0f172a;">{phone}</td>
                </tr>
                <tr style="border-bottom:1px solid #e2e8f0;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Email</td>
                  <td style="padding:12px 16px;font-size:14px;color:#0f172a;">{email}</td>
                </tr>
                <tr style="border-bottom:1px solid #e2e8f0;background:#ffffff;">
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Report Language</td>
                  <td style="padding:12px 16px;font-size:14px;color:#1a6fff;font-weight:600;">{lang}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;font-size:13px;color:#64748b;font-weight:600;">Report ID</td>
                  <td style="padding:12px 16px;font-size:12px;color:#94a3b8;font-family:monospace;">{report_id}</td>
                </tr>
              </table>

              <!-- Report attached notice -->
              <div style="margin-top:20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;">
                <p style="font-size:14px;color:#16a34a;margin:0;font-weight:600;">
                  ✅ Full AI screening report (PDF) is attached to this email.
                </p>
                <p style="font-size:13px;color:#64748b;margin:6px 0 0;">
                  The report includes YOLO detection results, AI analysis in {lang},
                  treatment recommendations, cost estimates, and recovery plan.
                </p>
              </div>

              <!-- Disclaimer -->
              <div style="margin-top:16px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;">
                <p style="font-size:12px;color:#78350f;margin:0;">
                  ⚠️ This is an AI-based screening tool. Please review findings and apply
                  your professional clinical judgment before diagnosis or treatment.
                </p>
              </div>
            </div>

            <!-- Footer -->
            <div style="background:#f8fafc;padding:14px 28px;border-top:1px solid #e2e8f0;">
              <p style="font-size:11px;color:#94a3b8;margin:0;">
                OralAI — AI Oral Health Screening | Swarnandhra College of Engineering and Technology<br>
                Sent automatically on {__import__('datetime').datetime.now().strftime('%d %b %Y at %I:%M %p')}
              </p>
            </div>

          </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        # ── Attach PDF report ─────────────────────────────────
        with open(report_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="OralAI_Report_{name.replace(" ", "_")}.pdf"'
        )
        msg.attach(part)

        # ── Send via Gmail SMTP ───────────────────────────────
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, doctor_email, msg.as_string())

        print(f"[Doctor Email] ✅ Auto-sent to {doctor_email} for patient: {name}")

    except Exception as e:
        print(f"[Doctor Email] ❌ Failed: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════
#  WHATSAPP HELPER EMAIL — fires ONLY when operator clicks
#  the WhatsApp button on result page
# ════════════════════════════════════════════════════════════
def send_whatsapp_helper_email(patient_info, report_id):
    """
    Fires ONLY when operator clicks the WhatsApp button.
    Sends friend a ready-to-click WhatsApp link + copy-paste message.
    """
    try:
        helper_email = WHATSAPP_HELPER_EMAIL
        if not helper_email:
            print("[Helper Email] WHATSAPP_HELPER_EMAIL not set — skipping")
            return

        name   = patient_info.get("name", "Patient")
        age    = patient_info.get("age", "N/A")
        gender = patient_info.get("gender", "N/A")
        phone  = patient_info.get("phone", "N/A")
        email  = patient_info.get("email", "N/A")
        lang   = patient_info.get("language", "English")

        clean_phone = str(phone).strip().replace(" ", "").replace("-", "")
        if not clean_phone.startswith("+"):
            clean_phone = f"+91{clean_phone.lstrip('0')}"
        wa_phone = clean_phone.replace("+", "")

        report_url = f"https://oralai.site/report/{report_id}"
        now_str    = __import__('datetime').datetime.now().strftime('%d %b %Y at %I:%M %p')

        wa_message = (
            f"Hello {name}! 🦷\n\n"
            f"Your OralAI dental screening report is ready.\n\n"
            f"📄 *Download your report here:*\n"
            f"{report_url}\n\n"
            f"If you have any questions, please visit your nearest dentist.\n\n"
            f"— OralAI Team 😊"
        )
        wa_link = f"https://wa.me/{wa_phone}?text={urllib.parse.quote(wa_message)}"

        from email.mime.base import MIMEBase
        from email import encoders

        msg = MIMEMultipart()
        msg["From"]    = f"OralAI <{EMAIL_USER}>"
        msg["To"]      = helper_email
        msg["Subject"] = f"📱 WhatsApp SEND NOW — {name} | {phone}"

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

            <!-- Header -->
            <div style="background:#25D366;padding:20px 28px;">
              <h2 style="color:#ffffff;margin:0;font-size:20px;">📱 WhatsApp — Send Report NOW</h2>
              <p style="color:#d4f5e2;margin:6px 0 0;font-size:13px;">OralAI — Action Required Immediately</p>
            </div>

            <!-- Patient Summary -->
            <div style="background:#f0fdf4;padding:16px 28px;border-bottom:2px dashed #25D366;">
              <table style="width:100%;border-collapse:collapse;">
                <tr>
                  <td style="font-size:13px;color:#64748b;font-weight:600;width:120px;padding:6px 0;">Patient</td>
                  <td style="font-size:16px;font-weight:800;color:#0f172a;">{name}</td>
                </tr>
                <tr>
                  <td style="font-size:13px;color:#64748b;font-weight:600;padding:6px 0;">WhatsApp No.</td>
                  <td style="font-size:18px;font-weight:800;color:#25D366;letter-spacing:1px;">{phone}</td>
                </tr>
                <tr>
                  <td style="font-size:13px;color:#64748b;font-weight:600;padding:6px 0;">Age / Gender</td>
                  <td style="font-size:14px;color:#0f172a;">{age} yrs / {gender}</td>
                </tr>
                <tr>
                  <td style="font-size:13px;color:#64748b;font-weight:600;padding:6px 0;">Language</td>
                  <td style="font-size:14px;color:#1a6fff;">{lang}</td>
                </tr>
              </table>
            </div>

            <div style="padding:24px 28px;">

              <!-- Step 1: WhatsApp Button -->
              <div style="background:#f0fdf4;border:2px solid #25D366;border-radius:12px;padding:18px;margin-bottom:20px;">
                <p style="font-size:14px;font-weight:700;color:#16a34a;margin:0 0 10px;">
                  ✅ STEP 1 — Click to open WhatsApp directly (message pre-filled!):
                </p>
                <a href="{wa_link}"
                   style="display:inline-block;background:#25D366;color:#ffffff;font-size:15px;font-weight:700;
                          padding:12px 24px;border-radius:8px;text-decoration:none;">
                  📲 Open WhatsApp &amp; Send Report
                </a>
                <p style="font-size:12px;color:#64748b;margin:10px 0 0;">
                  Opens WhatsApp with the message ready — just press Send!
                </p>
              </div>

              <!-- Step 2: Copy-paste -->
              <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:18px;margin-bottom:20px;">
                <p style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 10px;">
                  📋 STEP 2 — Or copy-paste this message manually:
                </p>
                <div style="background:#ffffff;border:2px dashed #cbd5e1;border-radius:8px;padding:16px;
                            font-size:13px;color:#1e293b;line-height:1.9;white-space:pre-line;font-family:monospace;">Hello {name}! 🦷

Your OralAI dental screening report is ready.

📄 *Download your report here:*
{report_url}

If you have any questions, please visit your nearest dentist.

— OralAI Team 😊</div>
              </div>

              <!-- Report Link -->
              <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:16px;">
                <p style="font-size:13px;font-weight:700;color:#1d4ed8;margin:0 0 8px;">
                  🔗 Report Link (share if needed):
                </p>
                <a href="{report_url}" style="font-size:13px;color:#1a6fff;word-break:break-all;">{report_url}</a>
              </div>

            </div>

            <!-- Footer -->
            <div style="background:#f8fafc;padding:14px 28px;border-top:1px solid #e2e8f0;">
              <p style="font-size:11px;color:#94a3b8;margin:0;">
                OralAI — Triggered by operator | {now_str}<br>
                Send WhatsApp ASAP — patient is waiting at the clinic!
              </p>
            </div>

          </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, helper_email, msg.as_string())

        print(f"[Helper Email] ✅ Sent to {helper_email} for: {name}")

    except Exception as e:
        print(f"[Helper Email] ❌ Failed: {e}")
        traceback.print_exc()


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
                deleted += 1
            except Exception as e:
                print(f"[Cleanup] Could not delete {f}: {e}")
    print(f"[Cleanup] {deleted} file(s) removed for {screening_id[:8]}...")


# ════════════════════════════════════════════════════════════
#  DEBUG
# ════════════════════════════════════════════════════════════
@app.route("/debug")
def debug_route():
    errors = []
    try:
        from pypdf import PdfWriter, PdfReader
        errors.append("✅ pypdf OK")
    except Exception as e:
        errors.append(f"❌ pypdf: {e}")
        try:
            from PyPDF2 import PdfWriter, PdfReader
            errors.append("✅ PyPDF2 OK (fallback)")
        except Exception as e2:
            errors.append(f"❌ PyPDF2 also failed: {e2}")
    try:
        from fpdf import FPDF
        errors.append("✅ fpdf2 OK")
    except Exception as e:
        errors.append(f"❌ fpdf: {e}")
    try:
        from reportlab.pdfgen import canvas
        errors.append("✅ reportlab OK")
    except Exception as e:
        errors.append(f"❌ reportlab: {e}")
    try:
        from PIL import Image, ImageDraw, ImageFont
        errors.append("✅ Pillow OK")
    except Exception as e:
        errors.append(f"❌ Pillow: {e}")
    fonts_dir = "static/fonts"
    if os.path.exists(fonts_dir):
        errors.append(f"✅ Fonts dir exists: {os.listdir(fonts_dir)}")
    else:
        errors.append(f"❌ Fonts dir MISSING: {fonts_dir}")
    if os.path.exists("static/management/config.json"):
        errors.append("✅ management/config.json exists")
    else:
        errors.append("⚠️ management/config.json missing (optional)")
    try:
        from report_generator import generate_pdf
        errors.append("✅ report_generator import OK")
    except Exception as e:
        errors.append(f"❌ report_generator: {e}")
        errors.append(traceback.format_exc().replace("\n", "<br>"))
    try:
        from ai_recommendation import generate_recommendations
        errors.append("✅ ai_recommendation import OK")
    except Exception as e:
        errors.append(f"❌ ai_recommendation: {e}")
    try:
        from detect import run_yolo
        errors.append("✅ detect import OK")
    except Exception as e:
        errors.append(f"❌ detect: {e}")
    try:
        from whatsapp_sender import send_whatsapp_report
        errors.append("✅ whatsapp_sender import OK")
    except Exception as e:
        errors.append(f"❌ whatsapp_sender: {e}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key and len(api_key) > 10:
        errors.append(f"✅ ANTHROPIC_API_KEY set (starts: {api_key[:8]}...)")
    else:
        errors.append("❌ ANTHROPIC_API_KEY missing or empty!")

    doc_email = os.getenv("DOCTOR_EMAIL", "")
    if doc_email and doc_email != "doctor@hospital.com":
        errors.append(f"✅ DOCTOR_EMAIL set: {doc_email}")
    else:
        errors.append("⚠️ DOCTOR_EMAIL not set in .env — auto email to doctor disabled")

    helper_email = os.getenv("WHATSAPP_HELPER_EMAIL", "")
    if helper_email:
        errors.append(f"✅ WHATSAPP_HELPER_EMAIL set: {helper_email}")
    else:
        errors.append("⚠️ WHATSAPP_HELPER_EMAIL not set in .env — WhatsApp helper email disabled")

    return "<br><br>".join(errors)


# ════════════════════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/screening_count")
def screening_count():
    return jsonify({"count": get_screening_count()})

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
            "face": False, "upper": False, "front": False, "lower": False,
            "face_thumb": "", "upper_thumb": "", "front_thumb": "", "lower_thumb": "",
            "expired": False,
        })
        return redirect("/capture")
    return render_template("details.html")


# ════════════════════════════════════════════════════════════
#  CAPTURE
# ════════════════════════════════════════════════════════════
@app.route("/capture")
def capture_page():
    if not session.get("patient_name"):
        return redirect("/details")
    return render_template("capture.html",
        session_language=session.get("language", "English"),
        session_token=session.get("session_token", ""))

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
#  PHONE CAPTURE
# ════════════════════════════════════════════════════════════
@app.route("/phone_capture")
def phone_capture():
    token = request.args.get("token", "").strip()
    if not token:
        return html_error("Missing Session Token",
            "This link is incomplete. It must be opened by scanning the QR code shown at the clinic.")
    ps = get_phone_session(token)
    if not ps:
        return html_error("Session Expired or Not Found",
            "This QR code session has expired or is no longer valid.", 404)
    if ps.get("expired"):
        return html_done("All Photos Received!",
            "All 4 photos have been successfully sent to the operator.")
    return render_template("phone_capture.html",
        token=token, session_language=ps.get("language", "English"))

@app.route("/phone_status")
def phone_status():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "missing token"}), 400
    ps = get_phone_session(token)
    if not ps:
        return jsonify({"error": "session not found"}), 404
    return jsonify({
        "face": ps.get("face", False), "upper": ps.get("upper", False),
        "front": ps.get("front", False), "lower": ps.get("lower", False),
        "face_thumb": ps.get("face_thumb", ""), "upper_thumb": ps.get("upper_thumb", ""),
        "front_thumb": ps.get("front_thumb", ""), "lower_thumb": ps.get("lower_thumb", ""),
        "expired": ps.get("expired", False),
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
#  VALIDATE
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
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": "Does this image show human teeth? Reply only with raw JSON."}
            ]}]
        )
        raw   = message.content[0].text.strip()
        clean = raw.replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(clean))
    except json.JSONDecodeError:
        return jsonify({"isTeeth": True, "reason": "Validation inconclusive"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  CLAUDE ANALYSIS
# ════════════════════════════════════════════════════════════
NON_LATIN_LANGUAGES = {
    "Hindi", "Marathi", "Telugu", "Tamil",
    "Kannada", "Malayalam", "Bengali", "Arabic"
}

def analyse_with_claude(yolo_image_paths, patient_info):
    try:
        age      = patient_info.get("age", "unknown")
        gender   = patient_info.get("gender", "unknown")
        name     = patient_info.get("name", "Patient")
        language = patient_info.get("language", "English")

        content = []
        labels  = ["Upper Teeth", "Front Teeth", "Lower Teeth"]
        paths   = [yolo_image_paths.get("upper"), yolo_image_paths.get("front"), yolo_image_paths.get("lower")]
        for i, (path, label) in enumerate(zip(paths, labels)):
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                content.append({"type": "text", "text": f"Image {i+1} - {label}:"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})

        content.append({"type": "text", "text": f"""You are an expert dental AI assistant reviewing 3 dental images for a patient.

Patient: {name}, Age: {age}, Gender: {gender}

Write EXACTLY these 6 sections in English. No markdown (no **, ##, *, _). Numbered sections and - bullets only.

1. DETECTED PROBLEMS
- [Condition] | Area: [upper/front/lower] | Observed: [visual details] | Affected teeth: [estimate] | Confidence: [High/Medium/Low] | Risk: [1 line]
Max 4 problems.

2. PROBLEM STATUS
- [Condition]: [Starting/Middle/Advanced] Stage | Signs: [2-3 visible signs] | Est. duration: [time] | If untreated: [1 line]

3. SUGGESTIONS TO OVERCOME
- [Condition]: Dentist: [treatment] | Urgency: [Routine/Soon/Urgent] | Home: [2 tips] | Avoid: [1 thing] | Tip: [motivation]

4. MONTHLY RECOVERY PLAN
Month 1: [clinic] + [home] | Products: [2 Indian products with Rs. prices]
Month 2: [clinic] + [home] | Products: [2 Indian products with Rs. prices]
Month 3: [clinic] + [home] | Products: [2 Indian products with Rs. prices]

5. TOTAL COST ESTIMATE
- [Treatment 1]: Rs.[min]-Rs.[max]
- [Treatment 2]: Rs.[min]-Rs.[max]
- Monthly products: Rs.[amount]/month
- Budget total: Rs.[min]-Rs.[max]
- Standard total: Rs.[min]-Rs.[max]

6. CONCLUSION
2 warm sentences: overall status, encourage {name}, most important first action.

RULES: English only. No markdown. ALL 6 sections are REQUIRED — do not stop until all 6 are complete. Each bullet 1 line max."""})

        print(f"[Claude] Analysing images for {name} ({language})...")
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            system=(
                "You are an expert dental AI. English only. No markdown. "
                "You MUST write ALL 6 sections completely. "
                "Do not stop or truncate. All 6 sections are required."
            ),
            messages=[{"role": "user", "content": content}]
        )
        analysis = message.content[0].text.strip()
        print(f"[Claude] Done — {len(analysis)} chars, {len(analysis.split())} words")

        missing = []
        for i in range(1, 7):
            if not any(f"{i}." in line for line in analysis.split("\n")):
                missing.append(i)
        if missing:
            print(f"[Claude] WARNING: Missing sections {missing} — retrying...")
            retry_msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8000,
                system=(
                    "You are an expert dental AI. English only. No markdown. "
                    "You MUST write ALL 6 sections completely. Never stop early."
                ),
                messages=[
                    {"role": "user", "content": content},
                    {"role": "assistant", "content": analysis},
                    {"role": "user", "content": f"You are missing sections {missing}. Please write those missing sections now, completely."}
                ]
            )
            analysis = analysis + "\n" + retry_msg.content[0].text.strip()
            print(f"[Claude] Retry done — {len(analysis)} chars total")

        return analysis
    except Exception as e:
        print(f"[Claude] Error: {e}")
        traceback.print_exc()
        return None


# ════════════════════════════════════════════════════════════
#  TRANSLATE
# ════════════════════════════════════════════════════════════
def translate_analysis(english_text, target_language):
    if target_language == "English":
        return english_text
    try:
        print(f"[Translate] Translating to {target_language}...")
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            system=(
                f"You are an expert medical translator. Translate to {target_language}. "
                f"Rules: "
                f"1. Translate EVERYTHING completely — all 6 sections. "
                f"2. Keep numbered sections (1. 2. 3. 4. 5. 6.) and dash bullets (-). "
                f"3. No markdown. "
                f"4. Output translated text only — no English, no preamble. "
                f"5. Preserve all numbers and Rs. prices exactly. "
                f"6. Do NOT stop until ALL 6 sections are fully translated. "
                f"7. Section 6 CONCLUSION must be the last thing you write."
            ),
            messages=[{"role": "user", "content": (
                f"Translate ALL 6 sections completely to {target_language}. "
                f"Do not stop until Section 6. CONCLUSION is done.\n\n{english_text}"
            )}]
        )
        translated = message.content[0].text.strip()
        print(f"[Translate] Done — {len(translated)} chars")

        if len(translated) < len(english_text) * 0.5:
            print(f"[Translate] WARNING: Translation seems truncated, retrying...")
            retry = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8000,
                system=(
                    f"You are an expert medical translator to {target_language}. "
                    f"Complete the translation. No markdown. Preserve section numbers and Rs. prices."
                ),
                messages=[
                    {"role": "user", "content": f"Translate to {target_language}:\n\n{english_text}"},
                    {"role": "assistant", "content": translated},
                    {"role": "user", "content": "Continue and complete the remaining sections of the translation."}
                ]
            )
            translated = translated + "\n" + retry.content[0].text.strip()
            print(f"[Translate] Retry done — {len(translated)} chars total")

        return translated
    except Exception as e:
        print(f"[Translate] Failed: {e}")
        return english_text


# ════════════════════════════════════════════════════════════
#  GENERATE — returns immediately, processes in background
# ════════════════════════════════════════════════════════════
@app.route("/generate", methods=["POST"])
def generate():
    try:
        name          = session.get("patient_name", "")
        age           = session.get("patient_age", "25")
        gender        = session.get("patient_gender", "Other")
        phone         = session.get("patient_phone", "")
        email         = session.get("patient_email", "")
        language      = session.get("language", "English")
        screening_id  = session.get("screening_id", "")
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

        report_id = str(uuid.uuid4())
        session["report_id"] = report_id
        session.modified = True

        patient_info = {
            "name": name, "age": age, "gender": gender,
            "phone": phone, "email": email, "language": language,
        }

        try:
            with open(report_marker_path(report_id), "w") as f:
                f.write("processing")
        except:
            pass

        report_status[report_id] = {"status": "processing"}
        print(f"[Generate] Starting: {name} | {language} | {screening_id[:8]}")

        def background_generate():
            try:
                with report_semaphore:
                    all_detections  = []
                    detected_labels = []
                    yolo_paths      = {}

                    for part in ["upper", "front", "lower"]:
                        img_path = os.path.join(UPLOAD_DIR, f"{screening_id}_{part}.jpg")
                        out_path = os.path.join(RESULT_DIR, f"{screening_id}_{part}_yolo.jpg")
                        if not os.path.exists(img_path):
                            print(f"[BG] Missing: {part}")
                            continue
                        try:
                            detections = run_yolo(img_path, out_path)
                        except Exception as e:
                            print(f"[BG YOLO] {part} error: {e}")
                            detections = []
                        yolo_paths[part] = out_path
                        if detections:
                            all_detections.extend(detections)
                            for d in detections:
                                if d["label"] not in detected_labels:
                                    detected_labels.append(d["label"])
                            print(f"[BG YOLO] {part}: {len(detections)} detections")

                    try:
                        recommendations = generate_recommendations(
                            detections=all_detections, age=age, gender=gender)
                    except Exception as e:
                        print(f"[BG Rec] Error: {e}")
                        recommendations = []

                    claude_analysis = analyse_with_claude(yolo_paths, patient_info)

                    if claude_analysis and language != "English":
                        claude_analysis = translate_analysis(claude_analysis, language)

                    print(f"[BG PDF] Building {report_id[:8]}...")
                    report_path = generate_pdf(
                        user_data=patient_info,
                        detected_labels=detected_labels,
                        report_id=report_id,
                        recommendations=recommendations,
                        claude_analysis=claude_analysis,
                        screening_id=screening_id
                    )

                    cleanup_old_files(screening_id)
                    if session_token:
                        delete_phone_session(session_token)
                    increment_screening_count()

                    try:
                        os.remove(report_marker_path(report_id))
                    except:
                        pass

                    report_status[report_id] = {"status": "done", "path": report_path}
                    print(f"[BG] ✅ Done: {report_id[:8]}")

                    # ── AUTO EMAIL TO DOCTOR — fires automatically ────
                    print(f"[BG] Sending auto email to doctor...")
                    send_report_to_doctor(patient_info, report_path, report_id)

            except Exception as e:
                err_msg = str(e)
                print(f"[BG] ❌ FATAL: {err_msg}")
                traceback.print_exc()
                try:
                    with open(report_error_path(report_id), "w") as f:
                        f.write(err_msg)
                    os.remove(report_marker_path(report_id))
                except:
                    pass
                report_status[report_id] = {"status": "error", "error": err_msg}

        threading.Thread(target=background_generate, daemon=True).start()
        return render_template("processing.html", report_id=report_id)

    except Exception as e:
        traceback.print_exc()
        return render_template("result.html", error=f"Failed to start: {str(e)}"), 500


# ════════════════════════════════════════════════════════════
#  REPORT STATUS
# ════════════════════════════════════════════════════════════
@app.route("/report_status/<report_id>")
def check_report_status(report_id):
    pdf_path = report_pdf_path(report_id)
    if os.path.exists(pdf_path):
        session["report_path"] = pdf_path
        session["report_id"]   = report_id
        session.modified = True
        return jsonify({"status": "done", "path": pdf_path})

    err_path = report_error_path(report_id)
    if os.path.exists(err_path):
        try:
            with open(err_path) as f:
                err_msg = f.read()
        except:
            err_msg = "Unknown error"
        return jsonify({"status": "error", "error": err_msg})

    mem = report_status.get(report_id, {})
    if mem.get("status") == "error":
        return jsonify(mem)

    return jsonify({"status": "processing"})


# ════════════════════════════════════════════════════════════
#  RESULT PAGE
# ════════════════════════════════════════════════════════════
@app.route("/result")
def result_page():
    report_id = request.args.get("report_id", "") or session.get("report_id", "")

    if not report_id:
        return render_template("result.html", error="Report not found. Please try again.")

    session["report_id"] = report_id
    session.modified = True

    pdf_path = report_pdf_path(report_id)
    if os.path.exists(pdf_path):
        session["report_path"] = pdf_path
        session.modified = True
        return render_template("result.html", success=True, report_id=report_id)

    err_path = report_error_path(report_id)
    if os.path.exists(err_path):
        try:
            with open(err_path) as f:
                err_msg = f.read()
        except:
            err_msg = "Unknown error"
        return render_template("result.html",
            error=f"Report generation failed: {err_msg}")

    mem = report_status.get(report_id, {})
    if mem.get("status") == "error":
        return render_template("result.html",
            error=f"Report generation failed: {mem.get('error', 'Unknown error')}")

    if os.path.exists(report_marker_path(report_id)):
        return render_template("result.html",
            error="Report is still generating. Please wait and refresh.")

    return render_template("result.html", error="Report not found. Please try again.")


# ════════════════════════════════════════════════════════════
#  DOWNLOAD
# ════════════════════════════════════════════════════════════
@app.route("/report/<report_id>")
def view_report(report_id):
    path = report_pdf_path(report_id)
    if not os.path.exists(path):
        return "Report not found", 404

    with open(path, "rb") as f:
        pdf_bytes = f.read()

    from flask import make_response
    response = make_response(pdf_bytes)
    response.headers["Content-Type"]        = "application/pdf"
    response.headers["Content-Disposition"] = 'attachment; filename="OralAI_Report.pdf"'
    response.headers["Content-Length"]      = len(pdf_bytes)
    response.headers["Cache-Control"]       = "no-store"
    return response


# ════════════════════════════════════════════════════════════
#  SEND EMAIL  (manual — patient only, operator clicks button)
# ════════════════════════════════════════════════════════════
@app.route("/send_email", methods=["POST"])
def send_email_route():
    email       = session.get("patient_email", "").strip()
    report_id   = session.get("report_id", "")
    report_path = session.get("report_path", "") or report_pdf_path(report_id)
    if not email:
        return "❌ Patient email not found."
    if not report_path or not os.path.exists(report_path):
        return "❌ Report not found."
    try:
        send_report(email, report_path)
        return "✅ Report sent successfully to " + email
    except Exception as e:
        return f"❌ Email failed: {str(e)}"


# ════════════════════════════════════════════════════════════
#  SEND WHATSAPP — also triggers friend helper email
# ════════════════════════════════════════════════════════════
@app.route("/send_whatsapp", methods=["POST"])
def send_whatsapp_route():
    phone       = session.get("patient_phone", "").strip()
    name        = session.get("patient_name", "Patient")
    age         = session.get("patient_age", "N/A")
    gender      = session.get("patient_gender", "N/A")
    email       = session.get("patient_email", "N/A")
    lang        = session.get("language", "English")
    report_id   = session.get("report_id", "")
    report_path = session.get("report_path", "") or report_pdf_path(report_id)

    if not phone:
        return "❌ No phone number found."
    if not report_id:
        return "❌ Report not found."
    if not os.path.exists(report_path):
        return "❌ Report file missing on server."

    patient_info = {
        "name": name, "age": age, "gender": gender,
        "phone": phone, "email": email, "language": lang,
    }

    # ── Fire friend WhatsApp helper email ─────────────────────
    # Runs in background so button response is instant
    threading.Thread(
        target=send_whatsapp_helper_email,
        args=(patient_info, report_id),
        daemon=True
    ).start()

    # ── Also try AiSensy WhatsApp API ─────────────────────────
    try:
        success, message = send_whatsapp_report(
            phone_number=phone, patient_name=name,
            report_id=report_id, report_path=report_path)
        if success:
            return f"✅ WhatsApp sent! Your friend has also been notified to send the report."
        else:
            # AiSensy failed but friend email still fired
            return f"📧 Friend notified via email to send WhatsApp! (AiSensy: {message})"
    except Exception as e:
        return f"📧 Friend notified via email to send WhatsApp! ({str(e)})"


# ════════════════════════════════════════════════════════════
#  REVIEW
# ════════════════════════════════════════════════════════════
@app.route("/review", methods=["POST"])
def review():
    try:
        data   = request.get_json()
        name   = data.get("name", "Anonymous")
        contact= data.get("contact", "N/A")
        review = data.get("review", "")
        rtype  = data.get("type", "General")
        rating = data.get("rating", "N/A")
        stars  = data.get("stars", "")
        if not review.strip():
            return jsonify({"success": False, "error": "Review cannot be empty."})
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⭐ OralAI Review ({rating}/5) — {name}"
        msg["From"]    = EMAIL_USER
        msg["To"]      = EMAIL_USER
        html_body = f"""<html><body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
            <div style="background:#0a1628;padding:24px 28px;"><h2 style="color:#fff;margin:0;">⭐ New OralAI Review</h2></div>
            <div style="padding:28px;">
              <div style="text-align:center;font-size:32px;">{stars}</div>
              <div style="text-align:center;font-size:15px;font-weight:700;color:#1a6fff;margin-bottom:24px;">{rating} / 5 Stars</div>
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:120px;">Name</td><td style="font-size:14px;font-weight:700;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Contact</td><td style="font-size:14px;">{contact}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Used for</td><td style="font-size:14px;color:#1a6fff;">{rtype}</td></tr>
              </table>
              <div style="margin-top:20px;padding:18px;background:#f8fafc;border-radius:10px;border-left:4px solid #f5c842;">
                <p style="font-size:15px;line-height:1.8;margin:0;font-style:italic;">"{review}"</p>
              </div>
            </div>
          </div></body></html>"""
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, EMAIL_USER, msg.as_string())
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
#  CONTACT
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
        html_body = f"""<html><body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
          <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
            <div style="background:#0a1628;padding:24px 28px;"><h2 style="color:#fff;margin:0;">OralAI — Contact</h2></div>
            <div style="padding:28px;">
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;font-size:13px;color:#64748b;width:100px;">Name</td><td style="font-size:14px;">{name}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Email</td><td style="font-size:14px;">{email}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Phone</td><td style="font-size:14px;">{phone}</td></tr>
                <tr style="border-top:1px solid #f1f5f9;"><td style="padding:8px 0;font-size:13px;color:#64748b;">Subject</td><td style="font-size:14px;color:#1a6fff;">{subject}</td></tr>
              </table>
              <div style="margin-top:20px;padding:16px;background:#f8fafc;border-radius:10px;border-left:4px solid #1a6fff;">
                <p style="font-size:14px;line-height:1.7;margin:0;">{message}</p>
              </div>
            </div>
          </div></body></html>"""
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
#  RUN
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)