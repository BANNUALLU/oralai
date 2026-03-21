import requests
import os


# ── WATI API credentials from environment variables ───────
WATI_API_URL   = os.getenv("WATI_API_URL", "https://live.wati.io/10110653")
WATI_API_TOKEN = os.getenv("WATI_API_TOKEN", "")


def send_whatsapp_report(phone_number, patient_name, report_id, report_path):
    """
    Send OralAI PDF report directly via WhatsApp using WATI API.
    Credentials are read from environment variables.
    Returns: (success: bool, message: str)
    """

    # ── Check if token is configured ──────────────────────────
    if not WATI_API_TOKEN:
        return False, "WhatsApp API not configured yet. Token will be added soon."

    # ── Check report file exists ───────────────────────────────
    if not os.path.exists(report_path):
        return False, "Report file not found on server."

    # ── Clean phone number ─────────────────────────────────────
    phone = phone_number.strip().replace("+", "").replace(" ", "").replace("-", "")

    headers = {
        "Authorization": f"Bearer {WATI_API_TOKEN}",
        "accept":        "application/json"
    }

    # ── Step 1: Send PDF file ──────────────────────────────────
    print(f"Sending PDF to WhatsApp: {phone}")

    try:
        with open(report_path, "rb") as pdf_file:
            file_response = requests.post(
                f"{WATI_API_URL}/api/v1/sendSessionFile/{phone}",
                headers=headers,
                files={"file": ("OralAI_Report.pdf", pdf_file, "application/pdf")},
                timeout=30
            )

        print(f"File send: {file_response.status_code} — {file_response.text}")

        # Try alternate endpoint if first fails
        if file_response.status_code not in [200, 201]:
            with open(report_path, "rb") as pdf_file:
                file_response = requests.post(
                    f"{WATI_API_URL}/sendSessionFile/{phone}",
                    headers=headers,
                    files={"file": ("OralAI_Report.pdf", pdf_file, "application/pdf")},
                    timeout=30
                )
            print(f"Alt send: {file_response.status_code} — {file_response.text}")

    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to WATI. Check your internet connection."
    except requests.exceptions.Timeout:
        return False, "WATI request timed out. Please try again."
    except Exception as e:
        return False, f"Send error: {str(e)}"

    if file_response.status_code not in [200, 201]:
        return False, f"WATI error ({file_response.status_code}): {file_response.text[:150]}"

    # ── Step 2: Send follow-up text message ───────────────────
    message_text = (
        f"Hello {patient_name}! 👋\n\n"
        f"🦷 *Your OralAI Dental Report is attached above.*\n\n"
        f"📋 Report ID: {report_id}\n\n"
        f"Please review and consult a dentist for professional advice.\n\n"
        f"⚠️ This is an AI-based screening tool only.\n\n"
        f"Thank you for using OralAI! 😊\n"
        f"🌐 www.oralai.site"
    )

    try:
        requests.post(
            f"{WATI_API_URL}/api/v1/sendSessionMessage/{phone}",
            headers={**headers, "Content-Type": "application/json"},
            json={"messageText": message_text},
            timeout=15
        )
    except Exception as e:
        print(f"Follow-up message failed (PDF was sent): {e}")

    return True, "✅ Report PDF sent to WhatsApp successfully!"