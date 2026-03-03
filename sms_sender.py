import requests
import os

FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY")

def send_sms(phone, report_url, name):

    if not FAST2SMS_API_KEY:
        raise Exception("FAST2SMS_API_KEY not set")

    message = (
        f"OralAI: Hello {name},\n"
        "Your dental screening report is ready.\n\n"
        f"Download:\n{report_url}\n\n"
        "- Team OralAI"
    )

    url = "https://www.fast2sms.com/dev/bulkV2"

    payload = {
        "route": "q",
        "message": message,
        "language": "english",
        "numbers": phone
    }

    headers = {
        "authorization": FAST2SMS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    try:
        return response.json()
    except:
        return {"error": "Invalid response from Fast2SMS"}