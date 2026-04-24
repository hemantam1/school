import asyncio
import re
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from openai import OpenAI

# --- CONFIGURATION ---
OPENAI_API_KEY = "YOUR_OPENAI_KEY" # Replace with your key
client = OpenAI(api_key=OPENAI_API_KEY)

# --- ORIGINAL HELPER FUNCTIONS ---

async def highlight_and_click(page, selector_or_locator, description="Action"):
    try:
        target = page.locator(selector_or_locator).first if isinstance(selector_or_locator, str) else selector_or_locator
        if await target.is_visible(timeout=1000): # Reduced timeout for speed
            await target.evaluate("el => { el.style.border = '4px solid #00FF00'; el.style.backgroundColor = 'rgba(0,255,0,0.2)'; }")
            await target.click()
            return True
    except:
        pass
    return False

async def handle_cookies_automatically(page):
    cookie_selectors = ["text=Accept All", "text=Accept", "button:has-text('Accept')", "button:has-text('OK')"]
    for selector in cookie_selectors:
        if await highlight_and_click(page, selector, "Cookie Banner"):
            break

def generate_fallback(metric, text_pool):
    metric_keywords = {
        "Coaching Credentials": ["teacher", "faculty", "expert"],
        "Student Wellbeing": ["wellbeing", "pastoral", "support"],
        "Academic Integration": ["curriculum", "academic", "learning"],
        "Competitive Pathway": ["exam", "assessment", "destination"],
        "Facilities & Resources": ["facilities", "campus", "resources"],
        "Ongoing Accountability": ["progress", "tracking", "assessment"]
    }
    kws = metric_keywords.get(metric, [])
    matched = [p for p in text_pool if any(k in p.lower() for k in kws)]
    if matched:
        return " ".join(matched[:2])
    return " ".join(text_pool[:2]) if text_pool else ""

# --- ENHANCED AI FALLBACK ---

def ai_extraction_fallback(field_name, context_text):
    """Deep extract using AI from the raw website text provided."""
    if not context_text or len(context_text) < 100:
        return "N/A"
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"You are a data extractor for {field_name}. Use ONLY the provided website text. If the information is not present, return 'N/A'. Be concise."},
                {"role": "user", "content": f"Website Text:\n{context_text[:5000]}\n\nExtract {field_name}:"}
            ],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "N/A"

# --- CORE EXTRACTION (LOGIC PRESERVED) ---

async def extract_school_data(url, browser_context):
    page = await browser_context.new_page()
    results = {
        "Name": "", "Founded": "", "City": "London", "Ages": "", "Ratio": "", "Fees": "",
        "About": "", "Philosophy": "", "Outcomes": "", "Admissions": "",
        "Performance": {}, "URL": url, "Images": []
    }
    global_text_pool = []
    body_text = ""

    print(f"\nConnecting to: {url}...")
    try:
        # Optimization: Try loading fast, fallback to AI if navigation is slow
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2) # Stabilize
            await handle_cookies_automatically(page)
            body_text = await page.inner_text("body")
        except Exception as e:
            print(f"Direct scraping failed, attempting AI extraction for {url}...")
            # If standard load fails, we can't get text, mark as N/A
            results["Name"] = url.split("//")[-1].split(".")[0].capitalize()

        # --- LOGIC START ---
        if body_text:
            title = await page.title()
            results["Name"] = title.split("|")[0].strip()

            def extract(pattern):
                match = re.search(pattern, body_text, re.IGNORECASE)
                return match.group(1).strip() if match else ""

            # Regex Founded Logic
            current_year = datetime.now().year
            clean_text = re.sub(r'\s+', ' ', body_text.lower())
            clean_text = re.sub(r'copyright.*?\d{4}|©.*?\d{4}', '', clean_text)
            keywords = ["founded", "established", "was founded", "was established"]
            sentences = re.split(r'[.!?]', clean_text)
            candidates = []
            for s in sentences:
                if any(k in s for k in keywords):
                    years = re.findall(r'(18\d{2}|19\d{2}|20\d{2})', s)
                    for y in years:
                        if 1800 <= int(y) <= current_year - 1:
                            candidates.append(y)
            if candidates:
                results["Founded"] = candidates[0]

            # Regex Ages Logic
            AGE_MAP = {"nursery": (3, 4), "reception": (4, 5), "year 1": (5, 6), "year 7": (11, 12), "year 13": (17, 18)}
            direct_age = extract(r'Ages?\s*[:\-]?\s*([\d–\-to ]+)')
            if direct_age and len(direct_age) < 15: # Filter junk
                results["Ages"] = direct_age
            else:
                text_lower = body_text.lower()
                found_v = [v for k, v in AGE_MAP.items() if k in text_lower]
                if found_v:
                    results["Ages"] = f"{min(x[0] for x in found_v)}–{max(x[1] for x in found_v)}"

            results["Fees"] = extract(r'£[\d,]+.*?(term|year)')

        # --- AI ENHANCEMENT (IF DATA IS MISSING) ---
        if not results["Founded"] or results["Founded"] == "":
            results["Founded"] = ai_extraction_fallback("Founded Year", body_text)
        
        if not results["Ages"] or len(results["Ages"]) < 2:
            results["Ages"] = ai_extraction_fallback("Age Range (e.g. 4-18)", body_text)
            
        if not results["About"] or len(results["About"]) < 50:
            results["About"] = ai_extraction_fallback("A 2-sentence school overview", body_text)

        # Print Output
        print("-" * 50)
        print(f"Elite › London › {results['Name']}")
        print(f"Ages: {results['Ages']} | Founded: {results['Founded']}")
        print(f"About: {results['About'][:100]}...")
        print("-" * 50)

    except Exception as e:
        print(f"Fatal Error on {url}: {str(e)[:100]}")
    finally:
        await page.close()

# --- BATCH PROCESSOR ---

async def run_batch():
    try:
        df = pd.read_excel("site data .xlsx")
    except FileNotFoundError:
        print("Error: 'site data .xlsx' file not found.")
        return

    # Filter London
    london_df = df[df['address'].astype(str).str.contains('London', case=False, na=False)]
    urls = london_df['website'].tolist()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Headless=False to see progress
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        
        for url in urls:
            if pd.isna(url): continue
            full_url = str(url) if str(url).startswith('http') else "https://" + str(url)
            await extract_school_data(full_url, context)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_batch())