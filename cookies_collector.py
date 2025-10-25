# playwright_scrape_followers.py
# Usage:
# 1) pip install playwright
# 2) playwright install
# 3) Run the script once with DO_LOGIN=True to interactively log in and save storage state
#    OR manually log in via a browser and export Playwright storage state to state.json
#
# Then run with DO_LOGIN=False to reuse saved session.

from playwright.sync_api import sync_playwright, TimeoutError as PlayTimeout
import time
import json

PROFILE = "the.crude.kid"        # target profile
MAX_FOLLOWERS = 500              # max usernames to collect (keep small)
SCROLL_PAUSE = 1.5               # seconds between scrolls (be polite)
DO_LOGIN = True                 # set True first run to login and save storage
STORAGE_STATE = "state.json"     # where the logged-in session is saved

def save_storage_state(context):
    context.storage_state(path=STORAGE_STATE)
    print(f"[INFO] Saved storage state to {STORAGE_STATE}")

def login_and_save_state(page):
    print("[INFO] Please log in manually in the opened browser window.")
    print("[INFO] Wait until you're logged in, then press Enter here.")
    input("Press Enter after login...")

def scroll_modal_and_collect(page, max_count):
    # Wait for followers modal to appear and the scrollable container
    # Instagram uses a dialog with role="dialog", the scrolling element is often a div with role="dialog" or a child ul
    page.wait_for_selector('div[role="dialog"]', timeout=10000)
    modal = page.query_selector('div[role="dialog"]')
    if not modal:
        print("[ERROR] followers modal not found")
        return []

    # The scrollable container is usually the first div inside the dialog with overflow: auto
    scrollable = modal.query_selector('div > div:nth-child(2)') or modal.query_selector('div[role="dialog"] ul')
    # fallback to the modal itself
    if not scrollable:
        scrollable = modal

    usernames = set()
    last_height = -1
    retries = 0

    while len(usernames) < max_count and retries < 6:
        # extract visible usernames
        elems = scrollable.query_selector_all('a[href^="/"] > div > div > span')  # common selector for username, may need tuning
        if not elems:
            elems = scrollable.query_selector_all('li a[href^="/"]')  # fallback
        for el in elems:
            text = el.inner_text().strip()
            if text:
                usernames.add(text)
        # scroll down
        page.evaluate("(el) => { el.scrollBy(0, el.scrollHeight); }", scrollable)
        time.sleep(SCROLL_PAUSE)
        # check if height changed (simple heuristic)
        height = page.evaluate("(el) => el.scrollHeight", scrollable)
        if height == last_height:
            retries += 1
        else:
            retries = 0
            last_height = height
    return list(usernames)[:max_count]

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)  # visible browser helps avoid blocks
        if DO_LOGIN:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            page.wait_for_timeout(2000)
            print("[INFO] Login page opened. Please log in manually in the browser window.")
            login_and_save_state(page)
            save_storage_state(context)
            context.close()
            browser.close()
            return

        # reuse saved session
        try:
            context = browser.new_context(storage_state=STORAGE_STATE)
        except Exception as e:
            print(f"[ERROR] Failed to load storage_state '{STORAGE_STATE}': {e}")
            print("Run once with DO_LOGIN=True to save session state.")
            browser.close()
            return

        page = context.new_page()
        page.set_default_timeout(20000)
        profile_url = f"https://www.instagram.com/{PROFILE}/"
        print(f"[INFO] Navigating to {profile_url}")
        page.goto(profile_url)

        # Wait for profile header to load and click followers count
        try:
            page.wait_for_selector('header', timeout=15000)
        except PlayTimeout:
            print("[ERROR] Profile header not loaded. Instagram may be blockading requests.")
            context.close()
            browser.close()
            return

        # Open followers modal by clicking followers link (the links are inside header)
        try:
            # follower link often has href="/<profile>/followers/"
            page.click(f'a[href="/{PROFILE}/followers/"]', timeout=8000)
        except PlayTimeout:
            # fallback: click first link that looks like followers count
            possible = page.query_selector_all('header li a')
            clicked = False
            for el in possible:
                href = el.get_attribute('href') or ""
                if "followers" in href:
                    el.click()
                    clicked = True
                    break
            if not clicked:
                print("[ERROR] Could not find followers link. Instagram layout may have changed.")
                context.close()
                browser.close()
                return

        # Wait for modal and collect
        try:
            followers = scroll_modal_and_collect(page, MAX_FOLLOWERS)
            print(f"[DONE] Collected {len(followers)} usernames.")
            # Save to file
            fname = f"{PROFILE}_followers.txt"
            with open(fname, "w", encoding="utf-8") as f:
                for u in followers:
                    f.write(u + "\n")
            print(f"[INFO] Written followers to {fname}")
        except Exception as e:
            print("[ERROR] Exception while collecting followers:", e)

        context.close()
        browser.close()

if __name__ == "__main__":
    run()

