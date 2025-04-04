import asyncio
from apscheduler.schedulers.blocking import BlockingScheduler
from playwright.async_api import async_playwright
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

# ====== Load ENV Vars ======
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "Software Developer")
LOCATION = os.getenv("LOCATION", "Canada")
ALREADY_SENT = set()

# ====== Telegram Notifier ======
def send_telegram(jobs):
    message = "<b>🚨 New LinkedIn Jobs Found:</b>\n\n"
    for title, url in jobs:
        message += f"<b>{title}</b>\n{url}\n\n"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload)
        if response.status_code == 200:
            print(f"✅ Telegram notification sent with {len(jobs)} job(s).")
        else:
            print("❌ Telegram API error:", response.text)
    except Exception as e:
        print("❌ Failed to send Telegram message:", e)

# ====== Scrape LinkedIn Jobs ======
async def fetch_linkedin_jobs():
    print(f"[{datetime.now()}] Running job check...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state="linkedin_state.json")
        page = await context.new_page()

        query = SEARCH_QUERY.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={LOCATION}"
        await page.goto(url)
        await page.wait_for_load_state("load")
        await page.wait_for_selector("a.job-card-container__link", timeout=60000)

        job_links = await page.query_selector_all("a.job-card-container__link")
        jobs = []

        for job in job_links[:5]:  # limit to top 5
            url = await job.get_attribute("href")
            title = await job.inner_text()
            if url and url not in ALREADY_SENT:
                ALREADY_SENT.add(url)
                full_url = f"https://www.linkedin.com{url}" if url.startswith("/jobs/") else url
                jobs.append((title.strip(), full_url))

        if jobs:
            send_telegram(jobs)
        else:
            print("No new jobs found.")

        await browser.close()

# ====== First Time Login ======
async def login_and_save_state():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("🔑 Please log in manually...")

        await page.wait_for_url("https://www.linkedin.com/feed/", timeout=180_000)
        print("✅ Login successful. Saving session...")
        await context.storage_state(path="linkedin_state.json")
        await browser.close()

# ====== Scheduler ======
def start_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(lambda: asyncio.run(fetch_linkedin_jobs()), 'interval', hours=3)
    print("🔁 Scheduler started. Job check every 3 hours.")
    asyncio.run(fetch_linkedin_jobs())  # Run immediately on start
    scheduler.start()

# ====== Entry Point ======
if __name__ == "__main__":
    if not os.path.exists("linkedin_state.json"):
        print("🔐 No LinkedIn session found. Starting login...")
        asyncio.run(login_and_save_state())

    start_scheduler()
