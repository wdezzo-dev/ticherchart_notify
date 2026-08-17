import os
import imaplib
import email
from email.policy import default
import re
import requests
import time

# --- Environment Variables (injected from GitHub Secrets) ---
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- FILTERS (specific to your email) ---
SENDER_FILTER = "live-alerts@tickerchart.com"   # <-- UPDATED
SUBJECT_FILTER = "تنبيه"                        # Optional, catches all alerts

def connect_gmail():
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_USER, GMAIL_PASSWORD)
    imap.select("INBOX")
    return imap

def fetch_unread_emails(imap):
    # Search for unread emails from this specific sender
    search_criteria = f'(UNSEEN FROM "{SENDER_FILTER}")'
    result, data = imap.uid_search(None, search_criteria)
    return data[0].split() if data[0] else []

def get_email_body(uid, imap):
    result, msg_data = imap.uid_fetch(uid, "(RFC822)")
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email, policy=default)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return body.strip()

def format_tickerchart_alert(raw_body):
    """
    Parse the specific TickerChart alert format and return a clean Telegram message.
    """
    lines = raw_body.split('\n')
    
    stock_name = ""
    stock_code = ""
    alert_msg = ""
    price = ""
    date = ""
    interval = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Extract fields that contain a colon
        if 'الرسالة:' in line:
            alert_msg = line.split(':', 1)[1].strip()
        elif 'السعر:' in line:
            price = line.split(':', 1)[1].strip()
        elif 'التاريخ:' in line:
            date = line.split(':', 1)[1].strip()
        elif 'الفاصل:' in line:
            interval = line.split(':', 1)[1].strip()
        elif 'القيمة المتحققة:' in line:
            # Ignore this field, or you can capture it if needed
            pass
        # Detect stock code (a standalone 4-digit number, like 7202)
        elif line.isdigit() and len(line) <= 5:
            stock_code = line
        # Detect stock name (Arabic text, no colon, not a header like "تنبيه تكرشات لايف")
        elif line and not line.startswith('تنبيه') and not line.startswith('تكرشات') and ':' not in line:
            stock_name = line

    # Build a beautiful Telegram message
    message = f"📊 *{stock_name}* ({stock_code})\n"
    message += f"📌 *الرسالة:* {alert_msg}\n"
    message += f"💰 *السعر:* {price}\n"
    message += f"📅 *التاريخ:* {date}\n"
    message += f"⏱️ *الفاصل:* {interval}"
    
    return message

def mark_as_read(uid, imap):
    imap.uid_store(uid, "+FLAGS", "\\Seen")

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send: {e}")

def main():
    if not all([GMAIL_USER, GMAIL_PASSWORD, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("Missing environment variables.")
        return

    try:
        imap = connect_gmail()
        uids = fetch_unread_emails(imap)
        print(f"Found {len(uids)} new TickerChart alerts.")

        for uid in uids:
            raw_body = get_email_body(uid, imap)
            if raw_body:
                # Format the alert nicely
                formatted_msg = format_tickerchart_alert(raw_body)
                send_to_telegram(formatted_msg)
                mark_as_read(uid, imap)
                print(f"Sent alert for UID {uid}")
                time.sleep(1)  # Avoid rate limits

        imap.close()
        imap.logout()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
