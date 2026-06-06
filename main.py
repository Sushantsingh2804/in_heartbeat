import schedule
import subprocess
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def run_bot(slot):
    logging.info(f"▶ Running bot.py {slot}")
    subprocess.run(["python3", "bot.py", slot])

def run_replies():
    logging.info("▶ Running reply_bot.py")
    subprocess.run(["python3", "reply_bot.py"])

# All times in IST — set TZ=Asia/Kolkata in Railway dashboard
schedule.every().day.at("09:00").do(run_bot, "morning")
schedule.every().day.at("13:00").do(run_bot, "afternoon")
schedule.every().day.at("18:30").do(run_replies)
schedule.every().day.at("19:00").do(run_bot, "evening")

logging.info("🚀 HeartbeatIN scheduler running")
logging.info("⏰ 9AM morning | 1PM afternoon | 6:30PM replies | 7PM thread")

while True:
    schedule.run_pending()
    time.sleep(30)