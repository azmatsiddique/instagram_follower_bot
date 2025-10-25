#!/usr/bin/env python3
"""
instagram_scraper_improved.py

Improved, robust Playwright scraper for Instagram followers.
Features:
 - Fixes Python escape warnings by using raw JS strings.
 - Prompts to log in & saves session state if needed.
 - Command-line args for target username, state file, outputs and max followers.
 - Exports JSON and CSV (username, profile_url).
 - Better logging and defensive retries.
"""
import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ---------- Defaults ----------
DEFAULT_STATE_FILE = "state.json"
DEFAULT_OUTPUT_JSON = "followers.json"
DEFAULT_OUTPUT_CSV = "followers.csv"
DEFAULT_MAX = 1000
BROWSER_HEADLESS = False
# ------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Instagram followers (Playwright).")
    p.add_argument("--username", "-u", required=True, help="Instagram username to scrape (no @).")
    p.add_argument("--state", "-s", default=DEFAULT_STATE_FILE, help="Playwright storage state file.")
    p.add_argument("--out-json", default=DEFAULT_OUTPUT_JSON, help="Output JSON file.")
    p.add_argument("--out-csv", default=DEFAULT_OUTPUT_CSV, help="Output CSV file.")
    p.add_argument("--max", "-m", type=int, default=DEFAULT_MAX, help="Maximum followers to fetch.")
    p.add_argument("--headless", action="store_true", help="Run browser headless (not recommended for login).")
    return p.parse_args()

async def ensure_logged_in(page):
    """Heuristic check for logged-in state. Returns True if seems logged in."""
    try:
        # allow UI to stabilize
        await page.wait_for_timeout(800)
        # Look for elements only visible when logged-in: profile svg with aria-label Profile, or the nav
        if await page.query_selector("svg[aria-label='Profile']"):
            return True
        if await page.query_selector("nav") and not await page.query_selector("text=Log in"):
            return True
    except Exception:
        pass
    return False

async def login_and_save_state(context, state_file):
    """Open login page and let user log in manually, then save storage state."""
    page = await context.new_page()
    print("[ACTION] No valid logged-in session. Opening browser for manual login.")
    await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
    print("Please log in in the opened browser window. Complete any 2FA/captcha, then press Enter here.")
    input("Press Enter after login is complete...")
    await context.storage_state(path=state_file)
    print(f"[SUCCESS] Login state saved to {state_file}")
    await page.close()

async def click_followers_button(page, username):
    """Try multiple selectors/strategies to click the followers control."""
    selectors = [
        f"a[href='/{username}/followers/']",
        f"a[href*='/{username}/followers']",
        "header a[href*='/followers']",
        "a:has-text('followers')",
        "a:has-text('Followers')",
        "ul li a[href*='/followers']",
        f"xpath=//a[contains(@href, '/{username}/followers')]",
    ]
    last_err = None
    for sel in selectors:
        try:
            locator = page.locator(sel)
            count = await locator.count()
            if count == 0:
                continue
            for i in range(count):
                item = locator.nth(i)
                try:
                    if await item.is_visible():
                        await item.scroll_into_view_if_needed()
                        await item.click(timeout=8000)
                        print(f"[INFO] Clicked followers button using selector: {sel}")
                        return True
                except Exception as e:
                    last_err = e
                    continue
        except Exception as e:
            last_err = e
            continue

    # fallback attempts
    try:
        header = await page.query_selector("header")
        if header:
            candidate = await header.query_selector("a")
            if candidate:
                await candidate.click()
                print("[INFO] Clicked a header link as fallback")
                return True
    except Exception as e:
        last_err = e

    if last_err:
        print(f"[ERROR] Could not click followers link (last error: {last_err})")
    else:
        print("[ERROR] Could not find any followers link on the profile page.")
    return False

async def scrape_followers(page, username, max_followers):
    """Main scraping logic: open profile, open followers dialog, scroll & extract usernames."""
    print(f"[INFO] Navigating to https://www.instagram.com/{username}/ ...")
    await page.goto(f"https://www.instagram.com/{username}/", timeout=60000)
    try:
        await page.wait_for_selector("header", timeout=30000)
    except PlaywrightTimeoutError:
        print("[ERROR] Profile header did not load - blocked or profile doesn't exist.")
        return []

    print("[INFO] Profile loaded. Checking login state...")
    if not await ensure_logged_in(page):
        # return control to caller to get login; we still continue but warn
        print("[WARNING] It doesn't look like you're logged in. The followers dialog might be restricted.")

    print("[INFO] Locating followers link...")
    if not await click_followers_button(page, username):
        print("[ERROR] Couldn't open followers dialog. Aborting.")
        return []

    # wait for dialog to appear
    try:
        await page.wait_for_selector("div[role='dialog']", timeout=45000)
    except PlaywrightTimeoutError:
        print("[ERROR] Followers dialog did not appear. Try logging in manually and retry.")
        return []

    dialog_selector = "div[role='dialog']"

    # Use raw string literals for JS to avoid Python escape warnings
    extract_js = r"""(el) => {
        // collects anchor hrefs like /username/
        const anchors = el.querySelectorAll('a[href^="/"]');
        const users = new Set();
        anchors.forEach(a => {
            const href = a.getAttribute('href');
            if (href && /^\/[^\/]+\/$/.test(href)) {
                users.add(href.replace(/\//g, ''));
            }
        });
        return Array.from(users);
    }"""

    # Also attempt to capture display names and profile URLs if possible
    extract_details_js = r"""(el) => {
        // returns list of {username, url, displayName} for anchors that look like /username/
        const rows = [];
        const anchors = Array.from(el.querySelectorAll('a[href^="/"]'));
        anchors.forEach(a => {
            const href = a.getAttribute('href');
            if (!href || !/^\/[^\/]+\/$/.test(href)) return;
            const username = href.replace(/\//g, '');
            const url = new URL(a.href).pathname;
            // try to find a nearby display name text (often a sibling span/div)
            let displayName = "";
            // look upward for a parent li and search within
            const li = a.closest('li');
            if (li) {
                const disp = li.querySelector('div > div > div:nth-child(2) > div > span') 
                          || li.querySelector('div > div > div:nth-child(2) > a > span')
                          || li.querySelector('span');
                if (disp) displayName = disp.innerText.trim();
            }
            rows.push({username, url, displayName});
        });
        // dedupe by username
        const seen = new Set();
        return rows.filter(r => {
            if (seen.has(r.username)) return false;
            seen.add(r.username);
            return true;
        });
    }"""

    scroll_js = r"""(el, pixels) => {
        const scrollable = el.querySelector('div[style*="overflow"]') || el.querySelector('ul') || el;
        scrollable.scrollTop = scrollable.scrollTop + pixels;
        return scrollable.scrollTop;
    }"""

    followers = []
    follower_set = set()
    prev_count = -1
    unchanged = 0

    print("[SCRAPING] Starting extraction and scrolling loop...")
    for attempt in range(1000):
        try:
            # try detailed extraction first
            found = await page.eval_on_selector(dialog_selector, extract_details_js)
            if not found:
                # fallback to username-only extraction
                found_usernames = await page.eval_on_selector(dialog_selector, extract_js)
                if found_usernames:
                    for u in found_usernames:
                        if u not in follower_set:
                            follower_set.add(u)
                            followers.append({"username": u, "profile_url": f"https://www.instagram.com/{u}/", "display_name": ""})
                # continue loop
            else:
                for row in found:
                    uname = row.get("username")
                    if not uname:
                        continue
                    if uname not in follower_set:
                        follower_set.add(uname)
                        followers.append({
                            "username": uname,
                            "profile_url": ("https://www.instagram.com" + row.get("url")) if row.get("url") else f"https://www.instagram.com/{uname}/",
                            "display_name": row.get("displayName") or ""
                        })
        except Exception as e:
            print(f"[WARN] extraction attempt failed: {e}")

        print(f"[INFO] Collected {len(followers)} followers so far...")

        if len(followers) >= max_followers:
            print("[INFO] Reached configured max followers limit.")
            break

        if len(followers) == prev_count:
            unchanged += 1
            if unchanged >= 6:
                print("[INFO] No new followers after several scrolls — assuming end or blocked.")
                break
        else:
            unchanged = 0
        prev_count = len(followers)

        # scroll the dialog
        try:
            await page.eval_on_selector(dialog_selector, scroll_js, 2000)
        except Exception:
            await page.mouse.wheel(0, 2000)

        await asyncio.sleep(1.2)

    print(f"[DONE] Finished scraping — total gathered: {len(followers)}")
    return followers

def save_outputs(followers, out_json: Path, out_csv: Path):
    # JSON
    with out_json.open("w", encoding="utf-8") as fh:
        json.dump(followers, fh, indent=2, ensure_ascii=False)
    print(f"[SAVED] JSON -> {out_json}")

    # CSV: username, profile_url, display_name
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["username", "profile_url", "display_name"])
        for r in followers:
            writer.writerow([r.get("username", ""), r.get("profile_url", ""), r.get("display_name", "")])
    print(f"[SAVED] CSV -> {out_csv}")

async def run(args):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        # Try to load saved state; if not present, create context and prompt login
        state_path = Path(args.state)
        if state_path.exists():
            try:
                context = await browser.new_context(storage_state=str(state_path))
                print("[SUCCESS] Loaded saved session.")
            except Exception as e:
                print(f"[WARN] Failed to load storage state ({e}). Will open manual login.")
                context = await browser.new_context()
        else:
            context = await browser.new_context()

        page = await context.new_page()

        # If not logged-in, prompt manual login & save
        if not await ensure_logged_in(page):
            # Offer login flow
            await login_and_save_state(context, str(state_path))
            # Recreate context with saved state
            await context.close()
            context = await browser.new_context(storage_state=str(state_path))
            page = await context.new_page()

        try:
            followers = await scrape_followers(page, args.username, args.max)
            out_json = Path(args.out_json)
            out_csv = Path(args.out_csv)
            save_outputs(followers, out_json, out_csv)

            if len(followers) == 0:
                # dump dialog html for debugging if possible
                try:
                    html = await page.eval_on_selector("div[role='dialog']", "(el) => el.outerHTML")
                    Path("dialog_debug.html").write_text(html, encoding="utf-8")
                    print("[DEBUG] Dialog HTML saved to dialog_debug.html — paste it if you want me to craft a selector.")
                except Exception as e:
                    print(f"[DEBUG] Could not dump dialog HTML: {e}")
        finally:
            await context.close()
            await browser.close()

def main():
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[INFO] Aborted by user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
