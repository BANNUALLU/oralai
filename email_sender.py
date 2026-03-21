import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# ── Gmail credentials from environment variables ──────────
EMAIL_USER = os.getenv("EMAIL_USER", "oralai.site@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")


def send_report(to_email, report_path):
    """
    Send OralAI PDF report to patient via Gmail SMTP.
    Credentials are read from environment variables.
    """

    msg = MIMEMultipart()
    msg["From"]    = f"OralAI <{EMAIL_USER}>"
    msg["To"]      = to_email
    msg["Subject"] = "Your OralAI Dental Screening Report"

    body = MIMEText("""
    <html>
    <body style="font-family:Arial,sans-serif;background:#f4f7ff;padding:20px;">
      <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

        <div style="background:#0a1628;padding:24px 28px;">
          <h2 style="color:#ffffff;margin:0;font-size:20px;">Your OralAI Dental Report is Ready!</h2>
          <p style="color:#8a9bb5;margin:6px 0 0;font-size:13px;">AI-Powered Oral Health Screening</p>
        </div>

        <div style="padding:28px;">
          <p style="font-size:15px;color:#0f172a;line-height:1.7;margin-bottom:16px;">
            Hello! Your AI-powered oral health screening report is attached to this email.
          </p>
          <p style="font-size:14px;color:#64748b;line-height:1.7;margin-bottom:20px;">
            Please find your detailed dental screening report in the attachment below.
            Review the findings and consult a dentist for professional advice.
          </p>

          <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;margin-bottom:20px;">
            <p style="font-size:13px;color:#78350f;margin:0;">
              This is an AI-based screening tool and does not replace a
              professional dental diagnosis. Please consult a dentist.
            </p>
          </div>

          <p style="font-size:13px;color:#94a3b8;margin:0;">
            Thank you for using OralAI!<br>
            <a href="https://www.oralai.site" style="color:#1a6fff;">www.oralai.site</a>
          </p>
        </div>

        <div style="background:#f8fafc;padding:14px 28px;border-top:1px solid #e2e8f0;">
          <p style="font-size:11px;color:#94a3b8;margin:0;">
            OralAI — AI Oral Health Screening | Swarnandhra College of Engineering and Technology
          </p>
        </div>

      </div>
    </body>
    </html>
    """, "html")

    msg.attach(body)

    # Attach PDF
    if os.path.exists(report_path):
        with open(report_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment; filename=OralAI_Report.pdf"
        )
        msg.attach(part)
    else:
        raise FileNotFoundError(f"Report not found: {report_path}")

    # Send via Gmail SMTP
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())

    print(f"Report email sent to {to_email}")