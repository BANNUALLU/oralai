from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from datetime import datetime
import os


def generate_pdf(user_data, detected_labels, report_id):

    name = user_data.get("name", "Patient")
    age = user_data.get("age", "")
    gender = user_data.get("gender", "")
    phone = user_data.get("phone", "")

    # 🔥 UNIQUE FILE NAME
    report_path = f"static/reports/{report_id}.pdf"

    c = canvas.Canvas(report_path, pagesize=A4)
    width, height = A4

    # ================= HEADER =================
    c.setFillColor(colors.HexColor("#7E57C2"))
    c.rect(0, height - 90, width, 90, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#2DB6A3"))
    c.rect(0, height - 90, 150, 90, fill=1, stroke=0)

    logo = "static/logo.png"
    if os.path.exists(logo):
        c.drawImage(logo, 25, height - 75, 100, 55, mask="auto")

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(
        width / 2 + 50,
        height - 55,
        "Oral Health Screening Report"
    )

    # ================= PATIENT INFO =================
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)

    c.drawString(50, height - 120, f"Name: {name} ({age}/{gender})")
    c.drawString(250, height - 120, f"Phone: {phone}")

    c.drawRightString(
        width - 50,
        height - 120,
        datetime.now().strftime("%d %b %Y %I:%M %p")
    )

    c.setStrokeColor(colors.lightgrey)
    c.line(40, height - 135, width - 40, height - 135)

    # ================= AI SCREENING =================
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 165, "AI SCREENING REPORT")

    # ================= IMAGES =================
    img_y = height - 380
    img_w, img_h = 150, 120

    images = [
        ("Upper Teeth", "upper_yolo.jpg", 60),
        ("Front Teeth", "front_yolo.jpg", 235),
        ("Lower Teeth", "lower_yolo.jpg", 410),
    ]

    for label, img, x in images:
        img_path = f"static/results/{img}"

        c.setFillColor(colors.whitesmoke)
        c.roundRect(x - 8, img_y - 8, img_w + 16, img_h + 40, 12, fill=1)

        if os.path.exists(img_path):
            c.drawImage(
                img_path,
                x,
                img_y,
                width=img_w,
                height=img_h,
                preserveAspectRatio=True,
                mask="auto"
            )

        c.setFillColor(colors.HexColor("#EF5350"))
        c.roundRect(x + 15, img_y - 28, 120, 22, 11, fill=1)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + 75, img_y - 23, label)

    # ================= LEGEND =================
    legend = {
        "malaligned": ("Malaligned tooth", colors.yellow),
        "stains": ("Stains", colors.red),
        "caries": ("Caries", colors.orange),
        "pit_fissure": ("Pit & fissure caries", colors.blue),
    }

    legend_y = img_y - 55
    lx = 70
    c.setFont("Helvetica", 10)

    for key in detected_labels:
        if key in legend:
            text, col = legend[key]
            c.setFillColor(col)
            c.rect(lx, legend_y, 10, 10, fill=1)
            c.setFillColor(colors.black)
            c.drawString(lx + 15, legend_y, text)
            lx += 130

    # ================= TREATMENT =================
    y = legend_y - 45
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "TREATMENT RECOMMENDATIONS")
    y -= 25

    treatments = {
        "malaligned": "Orthodontic braces or clear aligners recommended.",
        "stains": "Professional scaling and polishing advised.",
        "caries": "Restoration or RCT depending on severity.",
        "pit_fissure": "Sealants or restorative treatment required.",
    }

    c.setFont("Helvetica", 11)

    if not detected_labels:
        c.drawString(60, y, "No major oral health issues detected.")
    else:
        for key in detected_labels:
            if key in treatments:
                c.drawString(60, y, f"• {legend[key][0]}:")
                c.drawString(230, y, treatments[key])
                y -= 18

    # ================= DISCLAIMER =================
    y -= 20
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(
        50,
        y,
        "Disclaimer: This is an AI-based screening tool and not a medical diagnosis."
    )

    c.save()
    return report_path