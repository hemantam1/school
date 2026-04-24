import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

def format_to_four_lines(text):
    if not text: return ""
    single_para = " ".join(text.split()).strip()
    if len(single_para) > 450:
        return single_para[:447] + "..."
    return single_para

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
        "Coaching Credentials": ["teacher", "faculty", "staff", "educators", "expert", "experience", "qualified"],
        "Student Wellbeing": ["wellbeing", "pastoral", "support", "care", "health", "safety", "counseling"],
        "Academic Integration": ["curriculum", "academic", "learning", "classroom", "subjects", "program"],
        "Competitive Pathway": ["exam", "assessment", "destination", "university", "results", "future"],
        "Facilities & Resources": ["facilities", "campus", "resources", "library", "labs", "sports", "building"],
        "Ongoing Accountability": ["progress", "tracking", "assessment", "standards", "quality", "review"]
    }
    kws = metric_keywords.get(metric, [])
    matched = [p for p in text_pool if any(k in p.lower() for k in kws)]
    if matched:
        return format_to_four_lines(" ".join(matched[:2]))
    long_paras = [p for p in text_pool if len(p) > 150]
    return format_to_four_lines(long_paras[0] if long_paras else "Information regarding this program is available through the school's central office.")

async def extract_school_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        results = {
            "Name": "", "Founded": "", "City": "", "Ages": "", "Ratio": "Competitive", "Fees": "",
            "About": "", "Philosophy": "", "Outcomes": "", "Admissions": "",
            "Performance": {}, "URL": url, "Images": []
        }

        global_text_pool = []
        print(f"Connecting to: {url}...")

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await handle_cookies_automatically(page)

            # --- TAGDA IMAGE EXTRACTION LOGIC ---
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(0.5)
            
            found_urls = await page.evaluate("""
                () => {
                    const urls = new Set();
                    document.querySelectorAll('img').forEach(img => {
                        const src = img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src');
                        if (src && src.startsWith('http')) {
                            if (img.naturalWidth > 100 || img.naturalHeight > 100 || !img.naturalWidth) {
                                urls.add(src);
                            }
                        }
                    });
                    document.querySelectorAll('*').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const bg = style.backgroundImage;
                        if (bg && bg !== 'none' && bg.includes('url')) {
                            const match = bg.match(/url\\(["']?(.*?)["']?\\)/);
                            if (match && match[1].startsWith('http')) {
                                urls.add(match[1]);
                            }
                        }
                    });
                    return Array.from(urls);
                }
            """)

            image_set = set()
            for img_url in found_urls:
                clean_url = img_url.split('?')[0]
                is_valid_ext = any(ext in clean_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp'])
                is_not_junk = not any(junk in clean_url.lower() for junk in ['logo', 'icon', 'svg', 'avatar', 'button', 'loader', 'facebook', 'twitter'])
                if is_valid_ext and is_not_junk:
                    image_set.add(clean_url)
            
            results["Images"] = list(image_set)[:12]

            title = await page.title()
            results["Name"] = title.split("|")[0].strip()
            body_text = await page.inner_text("body")
            
            def clean_para_list(paras):
                return [p.strip() for p in paras if len(p.strip()) > 85 and not any(x in p.lower() for x in ["cookie", "privacy", "menu", "footer"])]

            global_text_pool.extend(clean_para_list(body_text.split('\n')))

            # Stats logic
            current_year = datetime.now().year
            years = re.findall(r'(18\d{2}|19\d{2}|20\d{2})', body_text)
            valid_years = [int(y) for y in years if 1800 <= int(y) <= current_year - 2]
            results["Founded"] = str(min(valid_years)) if valid_years else "Established"
            
            AGE_MAP = {"nursery": (3, 4), "reception": (4, 5), "primary": (5, 11), "secondary": (11, 18), "sixth form": (16, 18)}
            found_ages = [v for k, v in AGE_MAP.items() if k in body_text.lower()]
            results["Ages"] = f"{min(x[0] for x in found_ages)}–{max(x[1] for x in found_ages)}" if found_ages else "3–18"
            results["Fees"] = (re.search(r'((?:£|\$|SGD)[\d,]+.*?(?:term|year|annum))', body_text, re.IGNORECASE) or re.search(r'', '')).group(0) or "Available on request"

            # --- UPDATED CITY EXTRACTION LOGIC (Starts Here) ---
            # Priority 1: Check URL and Title for common cities
            city_list = ["Dubai", "Abu Dhabi", "Singapore", "London", "New York", "Hong Kong", "Doha", "Bangkok", "Mumbai"]
            potential_city = "International"
            
            search_area = (url + " " + title).lower()
            for city in city_list:
                if city.lower() in search_area:
                    potential_city = city
                    break
            
            # Priority 2: If still International, check the footer area/address
            if potential_city == "International":
                footer_text = await page.locator("footer").inner_text() if await page.locator("footer").count() > 0 else ""
                for city in city_list:
                    if city.lower() in footer_text.lower():
                        potential_city = city
                        break
            
            results["City"] = potential_city
            # --- UPDATED CITY EXTRACTION LOGIC (Ends Here) ---

        except Exception as e:
            print(f"Error during homepage scan: {e}")

        # Crawling subpages for content
        soup = BeautifulSoup(await page.content(), 'html.parser')
        links = soup.find_all('a', href=True)
        seen_urls = {url.rstrip('/')}
        targets = {"about": ["about", "history", "philosophy"], "outcomes": ["results", "university"], "admission": ["apply", "entry"]}
        
        queue = []
        for link in links:
            href = link['href']
            full_url = urljoin(url, href).split('#')[0].rstrip('/')
            if full_url not in seen_urls and url in full_url:
                if any(k in link.get_text().lower() for cat in targets.values() for k in cat):
                    queue.append(full_url)
                    seen_urls.add(full_url)

        for target_url in queue[:8]:
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                paras = await page.locator("p").all_text_contents()
                clean_ps = clean_para_list(paras)
                global_text_pool.extend(clean_ps)
                combined = " ".join(clean_ps)
                
                if any(k in target_url.lower() for k in targets["about"]):
                    if not results["About"]: results["About"] = format_to_four_lines(combined)
                if any(k in target_url.lower() for k in targets["outcomes"]):
                    if not results["Outcomes"]: results["Outcomes"] = format_to_four_lines(combined)
                if any(k in target_url.lower() for k in targets["admission"]):
                    if not results["Admissions"]: results["Admissions"] = format_to_four_lines(combined)
            except: continue

        # Final Fallbacks
        results["About"] = format_to_four_lines(results["About"] or " ".join(global_text_pool[:3]))
        results["Philosophy"] = format_to_four_lines(results["Philosophy"] or "A holistic approach to education focusing on global citizenship.")
        results["Outcomes"] = format_to_four_lines(results["Outcomes"] or "Graduates typically progress to leading universities globally.")
        results["Admissions"] = format_to_four_lines(results["Admissions"] or "Please contact the admissions team for details on requirements.")

        perf_keywords = {
            "Coaching Credentials": ["teacher", "faculty"], "Student Wellbeing": ["wellbeing", "care"],
            "Academic Integration": ["curriculum", "academic"], "Competitive Pathway": ["exam", "university"],
            "Facilities & Resources": ["facilities", "campus"], "Ongoing Accountability": ["progress", "standards"]
        }
        for key, kws in perf_keywords.items():
            if not results["Performance"].get(key):
                results["Performance"][key] = generate_fallback(key, global_text_pool)

        await browser.close()

        # PRINT FORMAT
        print("\n" + "—"*50)
        print(f"Elite › {results['City']} › {results['Name']}")
        print(f"{results['Name']} — Listed")
        print("—"*50)
        print(f"{results['Ages']}\tCompetitive\t{results['Founded']}")
        print(f"Ages\tRatio\t\tFounded")
        
        print(f"\nImages Found: {len(results['Images'])}")
        for i, img in enumerate(results["Images"][:12], 1):
            print(f"{i}. {img}")

        print(f"\nAbout {results['Name']}\n{results['About']}")
        print(f"\nInstitution Details\nType:\tPrivate School\nAges:\t{results['Ages']}\nFounded:\t{results['Founded']}\nCity:\t{results['City']}\nFees:\t{results['Fees']}")
        print(f"\nHow they teach\n{results['Philosophy']}")
        print(f"\nOutcomes\n{results['Outcomes']}")
        print(f"\nAdmissions\n{results['Admissions']}")
        print("\nPerformance Metrics")
        for k, v in results["Performance"].items():
            print(f"{k}:\n{v}\n")
        print(f"Website: {results['URL']}\n" + "—"*50)

if __name__ == "__main__":
    asyncio.run(extract_school_data("https://www.stanislas.fr/"))