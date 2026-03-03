from flask import Flask, render_template, request, redirect, send_file, jsonify
import base64
import os
import uuid

from detect import run_yolo
from report_generator import generate_pdf
from email_sender import send_report
from sms_sender import send_sms

app = Flask(__name__)

# -----------------------
# TEMP USER STORAGE
# -----------------------
user_data = {}

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
REPORT_DIR = "static/reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# -----------------------
# ROUTES
# -----------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start")
def start():
    return render_template("start.html")


@app.route("/details", methods=["GET", "POST"])
def details():
    if request.method == "POST":
        user_data.clear()
        user_data.update(request.form)
        return redirect("/capture")
    return render_template("details.html")


@app.route("/capture")
def capture_page():
    return render_template("capture.html")


@app.route("/capture", methods=["POST"])
def capture_image():
    data = request.get_json()
    image_type = data["type"]
    image_base64 = data["image"].split(",")[1]
    image_bytes = base64.b64decode(image_base64)

    image_path = os.path.join(UPLOAD_DIR, f"{image_type}.jpg")

    with open(image_path, "wb") as f:
        f.write(image_bytes)

    return jsonify({"status": "saved"})


# -----------------------
# GENERATE REPORT
# -----------------------

@app.route("/generate", methods=["POST"])
def generate():
    if not user_data:
        return redirect("/details")

    detected_labels = []

    for part in ["upper", "front", "lower"]:
        img_path = f"{UPLOAD_DIR}/{part}.jpg"
        out_path = f"{RESULT_DIR}/{part}_yolo.jpg"

        if not os.path.exists(img_path):
            return render_template(
                "result.html",
                error="❌ Missing images. Please capture again."
            )

        labels = run_yolo(img_path, out_path)

        if labels:
            detected_labels.extend(labels)

    detected_labels = list(set(detected_labels))

    # 🔥 UNIQUE REPORT ID
    report_id = str(uuid.uuid4())[:8]

    report_path = generate_pdf(
        user_data=user_data,
        detected_labels=detected_labels,
        report_id=report_id
    )

    user_data["report_path"] = report_path
    user_data["report_id"] = report_id

    return render_template(
        "result.html",
        success=True,
        email=user_data.get("email"),
        phone=user_data.get("phone"),
        labels=detected_labels,
        report_id=report_id
    )


# -----------------------
# SECURE REPORT DOWNLOAD
# -----------------------

@app.route("/report/<report_id>")
def view_report(report_id):
    report_path = f"{REPORT_DIR}/{report_id}.pdf"

    if not os.path.exists(report_path):
        return "❌ Report not found"

    return send_file(
        report_path,
        as_attachment=True,
        download_name="OralAI_Report.pdf"
    )


# -----------------------
# EMAIL (PDF ATTACHMENT)
# -----------------------

@app.route("/send_email", methods=["POST"])
def send_email_route():
    email = user_data.get("email")
    report_path = user_data.get("report_path")

    if not email or not report_path:
        return "❌ Email or report missing."

    try:
        send_report(email, report_path)
        return "✅ Email sent successfully!"
    except Exception as e:
        return f"❌ Email failed: {str(e)}"


# -----------------------
# SMS (SECURE LINK)
# -----------------------

@app.route("/send_sms", methods=["POST"])
def send_sms_route():
    phone = user_data.get("phone")
    name = user_data.get("name", "Patient")
    report_id = user_data.get("report_id")

    if not phone or not report_id:
        return "❌ Phone or report missing."

    phone = phone.strip()
    if phone.startswith("+91"):
        phone = phone.replace("+91", "")
    if phone.startswith("+"):
        phone = phone[1:]

    report_url = request.host_url + f"report/{report_id}"

    try:
        result = send_sms(phone, report_url, name)

        if result.get("return"):
            return "✅ SMS sent successfully!"
        else:
            return f"❌ SMS failed: {result}"

    except Exception as e:
        return f"❌ SMS error: {str(e)}"


if __name__ == "__main__":
    app.run(debug=True)