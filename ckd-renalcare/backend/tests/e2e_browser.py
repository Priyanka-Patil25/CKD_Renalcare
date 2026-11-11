# Optional browser test (needs: pip install playwright && playwright install chromium, and the server running on :8000 with seeded data).
# Not collected by pytest because the file name does not start with test_.
import asyncio, sys
from playwright.async_api import async_playwright
B="http://localhost:8000"
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        ctx = await br.new_context(viewport={"width":1400,"height":900})
        page = await ctx.new_page()
        errs=[]
        page.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
        page.on("pageerror", lambda e: errs.append("PAGEERR "+str(e)))
        # --- reception
        await page.goto(B+"/reception-login.html")
        await page.fill('input[name=identity]','reception1'); await page.fill('input[name=password]','reception123')
        await page.click('button[type=submit]'); await page.wait_for_url("**/reception.html")
        await page.wait_for_selector("#queue-body tr")
        await page.fill('input[name=name]','Asha Patil'); await page.fill('input[name=age]','63'); await page.select_option('select[name=sex]','F')
        await page.fill('input[name=reason]','New: diabetes'); await page.click('#register-form button[type=submit]')
        await page.wait_for_function("document.querySelector('#register-panel h2').textContent.startsWith('Added')")
        print("reception:", await page.inner_text('#register-panel h2'), "| waiting", await page.inner_text('#waiting-count'))
        await page.screenshot(path="/tmp/shot_reception.png", full_page=True)
        # wrong role
        await page.goto(B+"/doctor-login.html")
        await page.fill('input[name=identity]','reception1'); await page.fill('input[name=password]','reception123'); await page.click('button[type=submit]')
        await page.wait_for_timeout(800); print("wrong-role msg:", await page.inner_text('.form-error'))
        # --- doctor
        await page.fill('input[name=identity]','dr.morgan'); await page.fill('input[name=password]','doctor123'); await page.click('button[type=submit]')
        await page.wait_for_url("**/doctor.html"); await page.wait_for_selector("[data-open]")
        await page.screenshot(path="/tmp/shot_queue.png", full_page=True)
        await page.click('[data-open=DEMO-001]'); await page.wait_for_selector(".kgrid td.here")
        await page.wait_for_timeout(2500)
        await page.screenshot(path="/tmp/shot_patient1.png", full_page=True)
        print("flags:", await page.inner_text('#flag-count'))
        await page.click('.flag [data-act=accepted] >> nth=0'); await page.wait_for_timeout(500)
        print("after accept:", await page.inner_text('#flag-count'))
        # add results with NSAID
        await page.fill('#results-form input[name=creatinine]','2.1'); await page.fill('#results-form input[name=uacr]','310')
        await page.fill('#results-form input[name=medicines]','ACEi, Diclofenac')
        await page.click('#results-form button[type=submit]'); await page.wait_for_timeout(1500)
        print("results:", await page.inner_text('#results-status'))
        print("stage now:", await page.inner_text('#summary .sum >> nth=0'))
        print("nsaid flag:", await page.locator('.flag h4', has_text='NSAID').count())
        await page.screenshot(path="/tmp/shot_patient1_after.png", full_page=True)
        # draft + rag
        await page.click('#draft-btn'); await page.wait_for_timeout(1200); print("draft len:", len(await page.input_value('#notes')))
        await page.fill('#rag-question','ACE inhibitor'); await page.click('#rag-form button'); await page.wait_for_timeout(600); print("rag:", (await page.inner_text('#rag-answer'))[:90])
        await page.click('#back-queue'); await page.wait_for_selector("[data-open]")
        # no-labs patient
        await page.click('[data-open=DEMO-007]'); await page.wait_for_selector("#screen-result .risk-big"); await page.wait_for_timeout(500)
        await page.screenshot(path="/tmp/shot_patient7.png", full_page=True)
        print("screen:", (await page.inner_text('#screen-result .risk-big'))[:80].replace("\n"," "))
        await page.click('#screen-form button[type=submit]'); await page.wait_for_timeout(800)
        print("errors:", errs)
        await br.close()
asyncio.run(main())
