#!/usr/bin/env python3
"""
follow_fixed.py

Fixed follow-then-unfollow-on-followback script:
 - navigates to instagram.com before checking login
 - accepts followers.json either as ["user1","user2"] or [{"username":"user1"},...]
 - exits early with a clear message if list is empty
 - uses timezone-aware timestamps
"""

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ---------- Defaults & safety ----------
DEFAULT_STATE = "state.json"
DEFAULT_LIST = "followers.json"
DEFAULT_LOG = "follow_unfollow_log.jsonl"
DEFAULT_INTERVAL = 3600
DEFAULT_HEADLESS = False
DEFAULT_BATCH_SIZE = 10
MIN_DELAY_BETWEEN_ACTIONS = 5
MAX_DELAY_BETWEEN_ACTIONS = 12
BATCH_PAUSE = 60
# ---------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log_action(logfile: Path, entry: dict):
    entry["ts"] = now_iso()
    with logfile.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

async def navigate_home_and_check_login(page) -> bool:
    """Navigate to instagram.com and check login state heuristically."""
    try:
        await page.goto("https://www.instagram.com/", timeout=45000)
    except Exception as e:
        print(f"[WARN] Couldn't reach instagram.com to check login: {e}")
        # still attempt heuristic
    await page.wait_for_timeout(800)
    if await page.query_selector("svg[aria-label='Profile']"):
        return True
    if await page.query_selector("nav") and not await page.query_selector("text=Log in"):
        return True
    return False

async def login_flow(context, state_file):
    page = await context.new_page()
    print("[ACTION] Opening browser for manual login.")
    await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
    print("Please log in manually in the opened browser. Complete any 2FA/captcha if prompted, then press Enter here.")
    input("Press Enter after login is complete...")
    await context.storage_state(path=state_file)
    print(f"[SUCCESS] Saved storage state to {state_file}")
    await page.close()

# Profile actions (unchanged logic, slightly tightened)
async def follow_profile(page, uname: str) -> bool:
    url = f"https://www.instagram.com/{uname}/"
    try:
        await page.goto(url, timeout=60000)
    except Exception as e:
        print(f"[ERROR] Couldn't load profile {uname}: {e}")
        return False
    try:
        await page.wait_for_selector("header", timeout=20000)
    except PlaywrightTimeoutError:
        print(f"[WARN] Profile header did not load for {uname}")
        return False

    try:
        follow_btn = page.locator("button:has-text('Follow'), button:has-text('Follow back')")
        count = await follow_btn.count()
        for i in range(count):
            btn = follow_btn.nth(i)
            if await btn.is_visible():
                text = (await btn.inner_text()).strip()
                if "Follow" in text and "Following" not in text and "Requested" not in text:
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    print(f"[ACTION] Followed {uname}")
                    return True
        return False
    except Exception as e:
        print(f"[ERROR] Exception trying to follow {uname}: {e}")
        return False

async def is_user_following_me(page, uname: str) -> bool:
    url = f"https://www.instagram.com/{uname}/"
    try:
        await page.goto(url, timeout=60000)
    except Exception as e:
        print(f"[ERROR] Couldn't load profile {uname} for follow-back check: {e}")
        return False
    try:
        await page.wait_for_selector("header", timeout=15000)
    except PlaywrightTimeoutError:
        return False
    try:
        if await page.query_selector("text=Follows you"):
            return True
        if await page.query_selector("header div:has-text('Follows you')"):
            return True
    except Exception:
        pass
    return False

async def unfollow_profile(page, uname: str) -> bool:
    url = f"https://www.instagram.com/{uname}/"
    try:
        await page.goto(url, timeout=60000)
    except Exception as e:
        print(f"[ERROR] Couldn't load profile {uname} for unfollow: {e}")
        return False
    try:
        await page.wait_for_selector("header", timeout=15000)
    except PlaywrightTimeoutError:
        print(f"[WARN] Header didn't load for unfollowing {uname}")
        return False
    try:
        btn = page.locator("button:has-text('Following'), button:has-text('Requested')")
        cnt = await btn.count()
        for i in range(cnt):
            b = btn.nth(i)
            if await b.is_visible():
                await b.scroll_into_view_if_needed()
                await b.click()
                try:
                    await page.wait_for_selector("button:has-text('Unfollow')", timeout=8000)
                    confirm = page.locator("button:has-text('Unfollow')").first
                    if await confirm.is_visible():
                        await confirm.click()
                        print(f"[ACTION] Unfollowed {uname} (confirmed)")
                        return True
                except PlaywrightTimeoutError:
                    print(f"[ACTION] Clicked following/requested button for {uname} (no confirm found).")
                    return True
        return False
    except Exception as e:
        print(f"[ERROR] Exception while trying to unfollow {uname}: {e}")
        return False

async def follow_then_unfollow_loop(state_file: str, my_username: str, list_file: str, interval: int,
                                   log_file: str, headless: bool, batch_size: int):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        state_path = Path(state_file)
        if state_path.exists():
            try:
                context = await browser.new_context(storage_state=str(state_path))
                print("[SUCCESS] Loaded saved state.")
            except Exception as e:
                print(f"[WARN] Could not load state: {e}. Starting fresh context.")
                context = await browser.new_context()
        else:
            context = await browser.new_context()

        page = await context.new_page()

        # Navigate home and check login (fix)
        logged_in = await navigate_home_and_check_login(page)
        if not logged_in:
            await login_flow(context, state_file)
            await context.close()
            context = await browser.new_context(storage_state=str(state_path))
            page = await context.new_page()
            # confirm login after login flow
            logged_in = await navigate_home_and_check_login(page)
            if not logged_in:
                print("[WARN] Login still not detected after manual login. Continuing, but actions may fail.")

        # Load follower list
        followers_list_path = Path(list_file)
        if not followers_list_path.exists():
            print(f"[ERROR] Followers list file not found: {list_file}")
            await context.close()
            await browser.close()
            return

        try:
            with followers_list_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            # accept either simple list of strings or list of objects with 'username'
            if isinstance(data, list):
                if len(data) == 0:
                    print("[INFO] The follower list is empty (0 entries). Exiting.")
                    await context.close()
                    await browser.close()
                    return
                if all(isinstance(x, str) for x in data):
                    usernames = [u.strip().lstrip("@") for u in data if u.strip()]
                elif all(isinstance(x, dict) for x in data):
                    # extract username field
                    usernames = []
                    for obj in data:
                        if "username" in obj and isinstance(obj["username"], str):
                            usernames.append(obj["username"].strip().lstrip("@"))
                    usernames = [u for u in usernames if u]
                    if len(usernames) == 0:
                        print("[ERROR] followers.json contains objects but none had a 'username' string field. Exiting.")
                        await context.close()
                        await browser.close()
                        return
                else:
                    # mixed or unexpected format
                    # try to coerce strings and dicts
                    usernames = []
                    for it in data:
                        if isinstance(it, str):
                            usernames.append(it.strip().lstrip("@"))
                        elif isinstance(it, dict) and "username" in it and isinstance(it["username"], str):
                            usernames.append(it["username"].strip().lstrip("@"))
                    usernames = list(dict.fromkeys([u for u in usernames if u]))
                    if len(usernames) == 0:
                        print("[ERROR] Could not parse any usernames from followers.json. Exiting.")
                        await context.close()
                        await browser.close()
                        return
            else:
                print("[ERROR] followers.json is not an array. It must be a JSON array of strings or objects. Exiting.")
                await context.close()
                await browser.close()
                return
        except Exception as e:
            print(f"[ERROR] Failed to load/parse list file: {e}")
            await context.close()
            await browser.close()
            return

        # dedupe & summary
        usernames = list(dict.fromkeys(usernames))
        print(f"[INFO] Loaded {len(usernames)} usernames to follow/monitor.")

        log_path = Path(log_file)

        # Initial follow pass
        print(f"[INFO] Starting follow pass for {len(usernames)} users (batch size {batch_size})...")
        for idx, uname in enumerate(usernames, start=1):
            performed = await follow_profile(page, uname)
            log_action(log_path, {"action": "follow_attempt", "username": uname, "performed": bool(performed), "index": idx, "total": len(usernames)})
            await asyncio.sleep(random.uniform(MIN_DELAY_BETWEEN_ACTIONS, MAX_DELAY_BETWEEN_ACTIONS))
            if idx % batch_size == 0:
                print(f"[INFO] Completed {idx} follows; pausing {BATCH_PAUSE}s before next batch...")
                await asyncio.sleep(BATCH_PAUSE + random.uniform(1, 10))

        print("[INFO] Initial follow pass finished.")

        # Monitoring loop
        followed_set = set(usernames)
        print(f"[INFO] Entering monitoring loop. Will check every {interval} seconds.")
        try:
            while True:
                if not followed_set:
                    print("[INFO] No more users left to monitor. Exiting.")
                    break
                print(f"[CHECK] Monitoring pass started (checking {len(followed_set)} users)...")
                for uname in list(followed_set):
                    try:
                        follows_me = await is_user_following_me(page, uname)
                        if follows_me:
                            unfollowed = await unfollow_profile(page, uname)
                            log_action(log_path, {"action": "unfollow_on_followback", "username": uname, "unfollowed": bool(unfollowed)})
                            if unfollowed:
                                followed_set.discard(uname)
                        else:
                            log_action(log_path, {"action": "check_followback", "username": uname, "follows_me": False})
                    except Exception as e:
                        print(f"[WARN] Error checking/unfollowing {uname}: {e}")
                        log_action(log_path, {"action": "error", "username": uname, "error": str(e)})
                    await asyncio.sleep(random.uniform(8, 18))

                print(f"[CHECK] Monitoring pass complete at {now_iso()}. Sleeping {interval}s before next pass.")
                await asyncio.sleep(interval + random.uniform(0, 60))

        except KeyboardInterrupt:
            print("[INFO] Interrupted by user. Exiting monitoring loop.")
        finally:
            await context.close()
            await browser.close()

def parse_args():
    p = argparse.ArgumentParser(description="Follow users from list, then unfollow when they follow you back.")
    p.add_argument("--username", "-u", required=True, help="Your Instagram username (for logs).")
    p.add_argument("--state", "-s", default=DEFAULT_STATE, help="Playwright storage state file path.")
    p.add_argument("--list", "-l", default=DEFAULT_LIST, help="JSON file with list of usernames to follow (array).")
    p.add_argument("--interval", "-i", type=int, default=DEFAULT_INTERVAL, help="Seconds between followback checks.")
    p.add_argument("--log", default=DEFAULT_LOG, help="Append-only log file (jsonl).")
    p.add_argument("--headless", action="store_true", help="Run browser headless (not recommended for manual login).")
    p.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="How many follows to perform before pausing.")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(follow_then_unfollow_loop(args.state, args.username, args.list, args.interval, args.log, args.headless, args.batch))
    except KeyboardInterrupt:
        print("\n[INFO] Aborted by user.")
        sys.exit(0)
