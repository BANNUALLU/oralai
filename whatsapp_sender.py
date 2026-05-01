import requests
import os

# ── AiSensy API credentials from environment variables ────
AISENSY_API_KEY     = os.getenv("AISENSY_API_KEY", "")
AISENSY_CAMPAIGN    = os.getenv("AISENSY_CAMPAIGN_NAME", "oralai_report")  # your campaign name in AiSensy
AISENSY_API_URL     = "https://backend.aisensy.com/campaign/t1/api/v2"
REPORT_BASE_URL     = os.getenv("REPORT_BASE_URL", "https://yourdomain.com/reports")  # public URL to your reports


def send_whatsapp_report(phone_number, patient_name, report_id, report_path):
    """
    Send OralAI PDF report via WhatsApp using AiSensy API.
    
    ⚠️  Prerequisites:
        1. AiSensy account approved & WhatsApp Business API active
        2. A WhatsApp template created & approved in AiSensy
           (type: FILE, with {{1}} = patient name, {{2}} = report ID)
        3. AISENSY_API_KEY set in environment
        4. AISENSY_CAMPAIGN_NAME matches your campaign name in AiSensy
        5. PDF must be publicly accessible via REPORT_BASE_URL
    
    Returns: (success: bool, message: str)
    """

    # ── Check if API key is configured ────────────────────────
    if not AISENSY_API_KEY:
        return False, "AiSensy API key not configured. Set AISENSY_API_KEY env variable."

    # ── Check report file exists locally ──────────────────────
    if not os.path.exists(report_path):
        return False, "Report file not found on server."

    # ── Clean & format phone number ───────────────────────────
    phone = phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = f"+91{phone.lstrip('0')}"  # default to India if no country code

    # ── Build public URL for the PDF ──────────────────────────
    # AiSensy requires a publicly accessible media URL (not file upload)
    filename = os.path.basename(report_path)
    pdf_url = f"{REPORT_BASE_URL.rstrip('/')}/{filename}"

    print(f"Sending WhatsApp report via AiSensy to: {phone}")
    print(f"PDF URL: {pdf_url}")

    # ── Build AiSensy API payload ──────────────────────────────
    payload = {
        "apiKey":       AISENSY_API_KEY,
        "campaignName": AISENSY_CAMPAIGN,
        "destination":  phone,
        "userName":     patient_name,
        "source":       "OralAI App",
        "media": {
            "url":      pdf_url,
            "filename": f"OralAI_Report_{report_id}.pdf"
        },
        "templateParams": [
            patient_name,   # {{1}} in your template
            report_id       # {{2}} in your template
        ]
    }

    # ── Send API request ──────────────────────────────────────
    try:
        response = requests.post(
            AISENSY_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        print(f"AiSensy response: {response.status_code} — {response.text}")

        if response.status_code in [200, 201]:
            return True, "✅ Report sent to WhatsApp successfully via AiSensy!"
        else:
            return False, f"AiSensy error ({response.status_code}): {response.text[:200]}"

    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to AiSensy. Check your internet connection."
    except requests.exceptions.Timeout:
        return False, "AiSensy request timed out. Please try again."
    except Exception as e:
        return False, f"Send error: {str(e)}"