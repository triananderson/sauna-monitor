#!/usr/bin/env python3
# monitor_good_hot_hourly.py
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
import smtplib
from datetime import datetime, time as dtime, timedelta
import re
import json
from pathlib import Path
import time as time_mod
import os

# ---------- CONFIG ----------
URL = "https://www.good-hot-booking.com/book"
TARGET_END_DATE = "2026-03-14"   # run until end of this date (YYYY-MM-DD)
MIN_HOUR = 15
SAUNAS_KEYWORDS = {4: ["sauna 4", "big view"], 5: ["sauna 5", "big sky"]}

# Email (SMTP) - fill these
EMAIL_FROM = "tvnl pfji hxtk mjki.com"
EMAIL_TO = "triananderson@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "triananderson@gmail.com"
SMTP_PASS = "tvnl pfji hxtk mjki"

STATE_FILE = Path.home() / ".monitor_good_hot_state.json"
# ----------------------------

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

def send_email(subject, body):
    msg = MIMEText(body)
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def fetch_page():
    r = requests.get(URL, timeout=20)
    r.raise_for_status()
    return r.text

def find_bookings(html, target_date_str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n").lower()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results = []

    date_obj = datetime.fromisoformat(target_date_str).date()
    month_name = date_obj.strftime("%B").lower()
    day_num = str(date_obj.day)

    time_re = re.compile(r"(?:(?:[01]?\d|2[0-3]):[0-5]\d)|(?:\d{1,2}\s*(?:am|pm))|(?:\b(?:[01]?\d|2[0-3])\b)")

    for i, line in enumerate(lines):
        for sauna_no, kws in SAUNAS_KEYWORDS.items():
            if any(kw in line for kw in kws):
                window = " ".join(lines[i:i+6])
                if month_name in window and day_num in window or target_date_str in window:
                    for m in time_re.finditer(window):
                        time_str = m.group(0)
                        hour = None
                        try:
                            if ":" in time_str:
                                hour = int(time_str.split(":")[0])
                            elif time_str.endswith("am") or time_str.endswith("pm"):
                                t = time_str.replace(" ", "")
                                hh = int(re.match(r"(\d+)(?:am|pm)", t).group(1))
                                if t.endswith("pm") and hh != 12:
                                    hh += 12
                                if t.endswith("am") and hh == 12:
                                    hh = 0
                                hour = hh
                            else:
                                hour = int(time_str)
                        except Exception:
                            continue
                        if hour is not None and hour >= MIN_HOUR:
                            results.append({
                                "sauna_no": sauna_no,
                                "label": SAUNAS_KEYWORDS[sauna_no][0],
                                "date": target_date_str,
                                "time": f"{hour:02d}:00",
                                "context": window.strip()
                            })
    return results

def run_check_once(target_date_str):
    state = load_state()
    html = fetch_page()
    matches = find_bookings(html, target_date_str)

    if matches:
        body_lines = ["Found available bookings:"]
        for m in matches:
            body_lines.append(f"Sauna {m['sauna_no']} ({m['label']}), {m['date']} at {m['time']}")
            body_lines.append(f"Context: {m['context']}")
            body_lines.append("")
        send_email(f"Sauna cancellation(s) found for {target_date_str}", "\n".join(body_lines))
        print(f"[{datetime.now().isoformat()}] Notification sent: matches found.")
    else:
        key = f"no_available_test_sent_{target_date_str}"
        if not state.get(key):
            subj = f"No available 8-person saunas on {target_date_str}"
            body = f"Hello,\n\nThere are currently no available 8-person saunas (sauna no. 4 or 5) on {target_date_str}.\n\nRegards."
            send_email(subj, body)
            state[key] = True
            save_state(state)
            print(f"[{datetime.now().isoformat()}] One-time test email sent: no available saunas for {target_date_str}.")
        else:
            print(f"[{datetime.now().isoformat()}] No matches for {target_date_str}; no email (one-time test already sent).")

def run_until_end_date(end_date_str):
    end_date_obj = datetime.fromisoformat(end_date_str).date()
    end_dt = datetime.combine(end_date_obj, dtime(23, 59, 59))
    print(f"Starting monitor at {datetime.now().isoformat()}; will run until {end_dt.isoformat()} (local time).")
    # We will check for each date from today up to end_date_obj (inclusive)
    current_date = datetime.now().date()
    while datetime.now() <= end_dt:
        # determine which target date to search on this run:
        # if current_date <= end_date_obj, check current_date; otherwise break
        now = datetime.now()
        target_for_run = now.date()
        if target_for_run > end_date_obj:
            print(f"[{now.isoformat()}] Past end date; exiting.")
            break
        target_date_str = target_for_run.isoformat()
        try:
            run_check_once(target_date_str)
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error during check: {e}")
        # Sleep until the next full hour (at least 60 seconds)
        next_hour = (datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        sleep_seconds = max(60, (next_hour - datetime.now()).total_seconds())
        time_mod.sleep(sleep_seconds)

if __name__ == "__main__":
    run_until_end_date(TARGET_END_DATE)