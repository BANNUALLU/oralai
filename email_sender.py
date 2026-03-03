import smtplib
from email.message import EmailMessage
import os

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

def send_report(receiver, report_path):

    if not EMAIL_USER or not EMAIL_PASS:
        raise Exception("Email credentials not set")

    msg = EmailMessage()
    msg["Subject"] = "OralAI – Your Dental Screening Report"
    msg["From"] = EMAIL_USER
    msg["To"] = receiver

    msg.set_content(
        """
Hello,

Your OralAI dental screening report is attached.

Please review the attached PDF for detailed analysis.

Thank you for using OralAI.

- Team OralAI
"""
    )

    with open(report_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename="OralAI_Report.pdf"
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)