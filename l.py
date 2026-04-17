import asyncio
import re
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

# Logic for highlighting and clicking
async def highlight_and_click(page, selector_or_locator, description="Action"):
    try:
        target = page.locator(selector_or_locator).first if isinstance(selector_or_locator, str) else selector_or_locator
        if await target.is_visible(timeout=2000):
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
        "Coaching Credentials": ["teacher", "faculty", "expert", "instruction"],
        "Student Wellbeing": ["wellbeing", "pastoral", "support", "confidence", "nurturing"],
        "Academic Integration": ["curriculum", "academic", "learning", "ambitious"],
        "Competitive Pathway": ["exam", "assessment", "destination", "7+", "8+"],
        "Facilities & Resources": ["facilities", "campus", "resources", "tour"],
        "Ongoing Accountability": ["progress", "tracking", "assessment", "success"]
    }
    kws = metric_keywords.get(metric, [])
    matched = [p for p in text_pool if any(k in p.lower() for k in kws)]
    if matched:
        return " ".join(matched[:2])
    return " ".join(text_pool[:2]) if text_pool else ""

async def extract_school_data(url):
    # protocol check logic
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        results = {
            "Name": "", "Founded": "", "City": "", "Ages": "", "Ratio": "", "Fees": "",
            "About": "", "Philosophy": "", "Outcomes": "", "Admissions": "",
            "Performance": {}, "URL": url, "Images": []
        }

        global_text_pool = []
        print(f"Connecting to: {url}...")

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await handle_cookies_automatically(page)

            title = await page.title()
            results["Name"] = f"ᐅ {title.replace('|', 'ᐅ')}" 

            body_text = await page.inner_text("body")
            
            def extract(pattern):
                match = re.search(pattern, body_text, re.IGNORECASE)
                return match.group(1).strip() if match else ""

            current_year = datetime.now().year
            clean_text = re.sub(r'\s+', ' ', body_text.lower())
            clean_text = re.sub(r'copyright.*?\d{4}|©.*?\d{4}', '', clean_text)
            keywords = ["founded", "established", "founded in", "established in"]
            sentences = re.split(r'[.!?]', clean_text)
            candidates = []
            for s in sentences:
                if any(k in s for k in keywords):
                    years = re.findall(r'(19\d{2}|20\d{2})', s)
                    for y in years:
                        year = int(y)
                        if 1800 <= year <= current_year - 2:
                            score = sum(1 for k in keywords if k in s)
                            candidates.append((score, year))
            if candidates:
                candidates.sort(reverse=True)
                results["Founded"] = str(candidates[0][1])

            AGE_MAP = {"nursery": (3, 4), "reception": (4, 5), "year 1": (5, 6), "year 6": (10, 11), "year 13": (17, 18)}
            direct_age = extract(r'Ages?\s*[:\-]?\s*([\d–\-to ]+)')
            if direct_age:
                results["Ages"] = direct_age
            else:
                found_years = [v for k, v in AGE_MAP.items() if k in body_text.lower()]
                if found_years:
                    results["Ages"] = f"{min(x[0] for x in found_years)}–{max(x[1] for x in found_years)}"

            results["Fees"] = extract(r'£[\d,]+.*?(term|year)')
            results["City"] = "London, UK" if "London" in body_text else ""

            image_set = set()
            img_elements = await page.query_selector_all('img')
            for img in img_elements:
                src = await img.get_attribute('src')
                if src:
                    full = urljoin(url, src)
                    if any(ext in full.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        image_set.add(full)
                if len(image_set) >= 10: break
            results["Images"] = list(image_set)[:10]

            soup = BeautifulSoup(await page.content(), 'html.parser')
            targets = {
                "about": ["about", "history", "welcome"],
                "outcomes": ["destination", "senior-school", "beyond"],
                "admission": ["admissions", "apply", "entry"],
                "facilities": ["facilities", "campus", "sports"]
            }
            
            queue = []
            seen_urls = {url.rstrip('/')}
            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href']).split('#')[0].rstrip('/')
                text = link.get_text().lower().strip()
                if full_url not in seen_urls and url in full_url:
                    if any(k in text or k in full_url for cat in targets.values() for k in cat):
                        queue.append((full_url, text))
                        seen_urls.add(full_url)

            for target_url, link_text in queue[:15]:
                try:
                    await page.goto(target_url, wait_until="domcontentloaded")
                    paragraphs = await page.locator("p").all_text_contents()
                    clean_paras = [p.strip() for p in paragraphs if len(p.strip()) > 80]
                    global_text_pool.extend(clean_paras)
                    
                    full_text = " ".join(clean_paras)
                    if any(k in link_text or k in target_url for k in targets["about"]):
                        results["About"] = full_text[:1200]
                        results["Philosophy"] = " ".join(clean_paras[:3])
                    if any(k in link_text or k in target_url for k in targets["outcomes"]):
                        results["Outcomes"] = full_text[:1200]
                    if any(k in link_text or k in target_url for k in targets["admission"]):
                        results["Admissions"] = " ".join([p for p in clean_paras if any(x in p.lower() for x in ["apply", "admission", "register"])][:4])
                except: continue

            metrics = ["Coaching Credentials", "Student Wellbeing", "Academic Integration", "Competitive Pathway", "Facilities & Resources", "Ongoing Accountability"]
            for m in metrics:
                if not results["Performance"].get(m):
                    results["Performance"][m] = generate_fallback(m, global_text_pool)

            print("\n" + "—"*60)
            print(f"Elite › {results['City'].split(',')[0]} › {results['Name']}")
            print(f"{results['Name']} — Listed")
            print("Elite Academic Programs")
            print("—"*60)
            print(f"{results['Ages']}\t{results['Ratio']}\t\t{results['Founded']}")
            print(f"Ages\tRatio\t\tFounded")

            print(f"\nImages Found: {len(results['Images'])}")
            for i, img in enumerate(results["Images"], 1):
                print(f"{i}. {img}")

            print(f"\nAbout {results['Name']}\n{results['About']}...")

            print(f"\nInstitution Details\nType:\t\tPrivate Preparatory School\nAges:\t\t{results['Ages']}\nFounded:\t{results['Founded']}\nCity:\t\t{results['City']}\nAnnual Fee:\t{results['Fees']}")
            print(f"\nHow they teach\n{results['Philosophy']}")
            print(f"\nOutcomes: Where students go\n{results['Outcomes']}...")

            print("\nAdmissions & How to Apply")
            print(f"Enquiries Open: Year-round")
            print(f"Admission Policy:\tSelective entry based on assessment and registration.")
            print("-" * 20)
            print(f"Process Overview:\n{results['Admissions']}...")
            print("-" * 20)

            print("\nHow school perform")
            for k, v in results["Performance"].items():
                print(f"{k}:\n{v}\n")

            print(f"Location:\t{results['City']}")
            print(f"Website:\t{results['URL']}")
            print("—"*60)

        except Exception as e:
            print(f"Error scraping {url}: {e}")
        finally:
            await browser.close()

async def main():
    try:
        df = pd.read_excel("Site data .xlsx")
        url_column = [col for col in df.columns if col.lower() in ['website', 'url', 'links']][0]
        urls = df[url_column].dropna().tolist()
        
        for site_url in urls:
            # Cleaning the URL string just in case there are leading/trailing spaces
            clean_url = str(site_url).strip()
            await extract_school_data(clean_url)
    except Exception as e:
        print(f"Excel File Error: {e}. Please ensure 'Site data .xlsx' exists.")

if __name__ == "__main__":
    asyncio.run(main())