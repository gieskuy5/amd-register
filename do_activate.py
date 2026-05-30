#!/usr/bin/env python3
"""
DigitalOcean Auto Activate — Step 6
=====================================
Register DO accounts via devcloud.amd.com/registrations/email.
Uses CloakBrowser + 2Captcha for FunCaptcha.

Usage:
  python3 do_activate.py --input do_pending.json
  python3 do_activate.py --email user@richardsheingold.com
  python3 do_activate.py --all
"""

import asyncio
import imaplib
import email as em_mod
import re
import json
import time
import random
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

# ============ CONFIG (from config.json) ============
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
with open(CONFIG_FILE) as f:
    CFG = json.load(f)

IMAP_HOST = CFG["imap_host"]
IMAP_USER = CFG["imap_user"]
IMAP_PW = CFG["imap_password"]

SUCCESS_FILE = SCRIPT_DIR / "success.txt"
RESULTS_FILE = SCRIPT_DIR / "do_activate_results.json"
PASSWORD = CFG["password"]

REGISTER_URL = "https://devcloud.amd.com/registrations/email"
CAPTCHA_KEY = CFG["captcha_key"]
FUNCAPTCHA_SURL = "eb15f.digitalocean.com"


def log(msg, icon="•"):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def load_results():
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except:
        return {}


def save_results(results):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2)


def email_to_name(email):
    local = email.split('@')[0]
    clean = re.sub(r'\d+', '', local).strip('.')
    parts = [p.capitalize() for p in clean.split('.') if p]
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"
    elif parts:
        return f"{parts[0]} User"
    return "User Account"


# ============ 2CAPTCHA SOLVER ============
def solve_funcaptcha(pageurl, sitekey):
    """Solve Arkose/FunCaptcha via 2Captcha. sitekey = UUID from iframe hash."""
    log("Solving FunCaptcha...", "🔐")
    try:
        r = requests.post("https://api.2captcha.com/createTask", json={
            "clientKey": CAPTCHA_KEY,
            "task": {
                "type": "FunCaptchaTaskProxyless",
                "websitePublicKey": sitekey,
                "websiteURL": pageurl,
                "funcaptchaApiJSSubdomain": FUNCAPTCHA_SURL,
                "data": {"s_url": f"https://{FUNCAPTCHA_SURL}"},
            }
        }, timeout=30)
        result = r.json()
        if result.get("errorId", 0) != 0:
            log(f"2Captcha error: {result.get('errorDescription')}", "❌")
            return None
        task_id = result["taskId"]
        log(f"Task: {task_id}")
    except Exception as e:
        log(f"2Captcha create error: {e}", "❌")
        return None

    for i in range(60):
        time.sleep(5)
        try:
            r = requests.post("https://api.2captcha.com/getTaskResult", json={
                "clientKey": CAPTCHA_KEY,
                "taskId": task_id,
            }, timeout=15)
            result = r.json()
            if result.get("status") == "ready":
                token = result["solution"]["token"]
                log(f"Solved! ({(i+1)*5}s, {len(token)} chars)", "✅")
                return token
            if result.get("errorId", 0) != 0:
                log(f"Error: {result.get('errorDescription')}", "❌")
                return None
            if i > 0 and i % 6 == 0:
                log(f"Solving... ({(i+1)*5}s)")
        except:
            pass

    log("CAPTCHA timeout (5min)", "❌")
    return None


# ============ FETCH DO LINK FROM EMAIL ============
def fetch_do_link(email_addr, timeout=180):
    """Poll IMAP for DigitalOcean activation email and extract link."""
    log(f"Waiting for DO email ({timeout}s)...", "📧")
    start = time.time()
    seen = set()

    while time.time() - start < timeout:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(IMAP_USER, IMAP_PW)
            mail.select('INBOX')
            _, nums = mail.search(None, 'TO', f'"{email_addr}"', 'SUBJECT', '"Welcome to the AMD developer cloud"')
            if nums[0]:
                for n in nums[0].split():
                    if n in seen:
                        continue
                    seen.add(n)
                    _, d = mail.fetch(n, '(RFC822)')
                    msg = em_mod.message_from_bytes(d[0][1])
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                            elif part.get_content_type() == 'text/html' and not body:
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                    link_match = re.search(r'(https?://waves\.digitalocean\.com/[A-Za-z0-9_\-/=+]+)', body)
                    if link_match:
                        link = link_match.group(1)
                        log(f"DO link: {link[:60]}...", "✅")
                        mail.logout()
                        return link
            mail.logout()
        except Exception as e:
            log(f"IMAP error: {e}", "⚠️")
        time.sleep(15)

    log("DO link timeout", "❌")
    return None


# ============ CONFIRM EMAIL ============
def confirm_email(email_addr, timeout=120):
    """Poll IMAP for confirmation email and visit the link."""
    log(f"Waiting for confirm email ({timeout}s)...", "📧")
    start = time.time()
    seen = set()

    while time.time() - start < timeout:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(IMAP_USER, IMAP_PW)
            mail.select('INBOX')
            _, nums = mail.search(None, 'TO', f'"{email_addr}"', 'SUBJECT', '"Confirm your AMD Developer Cloud account"')
            if nums[0]:
                for n in nums[0].split():
                    if n in seen:
                        continue
                    seen.add(n)
                    _, d = mail.fetch(n, '(RFC822)')
                    msg = em_mod.message_from_bytes(d[0][1])
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                            elif part.get_content_type() == 'text/html' and not body:
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                    link_match = re.search(r'(https?://devcloud\.amd\.com/account_verification/email/[A-Za-z0-9_/=+?&]+)', body)
                    if link_match:
                        link = link_match.group(1)
                        log(f"Confirm link: {link[:60]}...", "✅")
                        mail.logout()
                        return link
            mail.logout()
        except Exception as e:
            log(f"IMAP error: {e}", "⚠️")
        time.sleep(10)

    log("Confirm email timeout", "❌")
    return None


def fetch_verification_code(email_addr, timeout=90):
    """Fetch LATEST 6-digit verification code from email."""
    log(f"Waiting for verification code ({timeout}s)...", "📧")
    start = time.time()
    last_code = None
    seen = set()

    while time.time() - start < timeout:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(IMAP_USER, IMAP_PW)
            mail.select('INBOX')
            _, nums = mail.search(None, 'TO', f'"{email_addr}"', 'SUBJECT', '"AMD Developer Cloud Verification Code"')
            if nums[0]:
                # Get ALL codes, keep latest
                for n in nums[0].split():
                    if n in seen:
                        continue
                    seen.add(n)
                    _, d = mail.fetch(n, '(RFC822)')
                    msg = em_mod.message_from_bytes(d[0][1])
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                    code_match = re.search(r'(\d{6})', body)
                    if code_match:
                        last_code = code_match.group(1)
                        log(f"Found code: {last_code}", "📧")
            mail.logout()

            # Wait a bit more for latest code if just triggered
            if last_code and (time.time() - start) > 15:
                log(f"Using latest code: {last_code}", "✅")
                return last_code
        except Exception as e:
            log(f"IMAP error: {e}", "⚠️")
        time.sleep(5)

    if last_code:
        log(f"Using last code: {last_code}", "✅")
        return last_code
    log("Verification code timeout", "❌")
    return None


async def visit_confirm(page, confirm_link):
    """Visit the confirmation link to verify the account."""
    log(f"Visiting confirm link...", "🔗")
    try:
        await page.goto(confirm_link, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(5000)
        url = page.url
        text = (await page.inner_text('body')).lower()
        log(f"Confirm result: {url}")
        if any(s in text for s in ['confirmed', 'verified', 'success', 'welcome', 'dashboard', 'projects']):
            log("Email confirmed!", "✅")
            return True
        elif 'already' in text:
            log("Already confirmed!", "✅")
            return True
        else:
            log(f"Confirm page: {text[:100]}", "⚠️")
            return True  # Assume OK
    except Exception as e:
        log(f"Confirm error: {e}", "❌")
        return False


async def login_and_verify(page, email_addr):
    """Login to devcloud.amd.com and enter verification code."""
    log("Logging in...", "🔐")
    try:
        await page.goto('https://devcloud.amd.com/login', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # Fill login
        email_input = await page.query_selector('input[placeholder*="email"]')
        pass_input = await page.query_selector('input[type="password"]')
        if not (email_input and pass_input):
            log("Login fields not found", "❌")
            return False

        await email_input.fill(email_addr)
        await pass_input.fill(PASSWORD)
        await page.wait_for_timeout(500)

        btn = await page.query_selector('button:has-text("Log In")')
        await btn.click()
        await page.wait_for_timeout(8000)

        # Check if verification needed
        page_text = (await page.inner_text('body')).lower()
        if 'verification code' in page_text or 'verify' in page_text:
            log("Verification code needed!", "⚠️")
            code = fetch_verification_code(email_addr, timeout=90)
            if not code:
                log("No verification code", "❌")
                return False

            # Enter code
            code_input = await page.query_selector('#code, input[placeholder*="6-digit"]')
            if not code_input:
                # Try finding any input that's not email/password
                all_inputs = await page.query_selector_all('input:not([type="hidden"]):not([type="checkbox"])')
                for inp in all_inputs:
                    ph = await inp.get_attribute('placeholder') or ''
                    if 'email' not in ph.lower() and 'password' not in ph.lower():
                        code_input = inp
                        break

            if code_input:
                await code_input.fill(code)
                await page.wait_for_timeout(500)
                verify_btn = await page.query_selector('button:has-text("Verify Code")')
                if verify_btn:
                    await verify_btn.click()
                    await page.wait_for_timeout(8000)

                    final_url = page.url
                    final_text = (await page.inner_text('body')).lower()
                    log(f"After verify: {final_url}")
                    if any(s in final_text for s in ['dashboard', 'projects', 'welcome', 'droplet']):
                        log("Login + verify success!", "✅")
                        return True
                    elif 'error' in final_text or 'invalid' in final_text:
                        log("Verification failed", "❌")
                        return False
                    else:
                        log(f"Verify result: {final_text[:100]}", "⚠️")
                        return True
            else:
                log("No code input found", "❌")
                return False
        elif 'dashboard' in page_text or 'projects' in page_text:
            log("Already logged in!", "✅")
            return True
        else:
            log(f"Login result: {page_text[:100]}", "⚠️")
            return True

    except Exception as e:
        log(f"Login error: {e}", "❌")
        return False


# ============ REGISTER DO ACCOUNT ============
async def register_do(page, email_addr, link=None):
    """Register DigitalOcean account at devcloud.amd.com."""
    name = email_to_name(email_addr)
    log(f"Registering: {name} ({email_addr})", "🚀")

    try:
        # Navigate to signup (use DO waves link if available)
        target_url = link if link else REGISTER_URL
        log(f"Using: {target_url[:80]}...", "🌐")
        await page.goto(target_url, wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_timeout(3000)

        # Fill form directly (name, email, password)
        name_input = await page.query_selector('#name')
        email_input = await page.query_selector('#email')
        pass_input = await page.query_selector('#password')

        if not (name_input and email_input and pass_input):
            log("Form fields not found", "❌")
            text = await page.inner_text('body')
            log(f"Page: {text[:200]}", "⚠️")
            return False

        await name_input.fill(name)
        await email_input.fill(email_addr)
        await pass_input.fill(PASSWORD)
        await page.wait_for_timeout(500)

        # Submit
        sign_btn = await page.query_selector('button:has-text("Sign Up")')
        if not sign_btn:
            log("No Sign Up button", "❌")
            return False

        await sign_btn.click()
        await page.wait_for_timeout(8000)

        # Check for "already registered" before CAPTCHA
        page_url = page.url
        page_text = (await page.inner_text('body')).lower()
        if 'already' in page_text and ('registered' in page_text or 'exists' in page_text or 'account' in page_text):
            log("Account already registered!", "⚠️")
            return True  # Count as success
        if '/login' in page_url and 'security' not in page_url:
            log("Redirected to login — account exists!", "⚠️")
            return True

        # Check for CAPTCHA
        captcha_iframe = await page.query_selector('iframe[src*="enforcement"], iframe[title*="Verification"]')
        if captcha_iframe:
            log("FunCaptcha detected!", "⚠️")
            src = await captcha_iframe.get_attribute('src') or ''
            log(f"Iframe: {src[:80]}")

            # Extract UUID from iframe hash (the actual public key for 2Captcha)
            uuid_match = re.search(r'#([A-F0-9-]{36})', src)
            if not uuid_match:
                log("No UUID in iframe", "❌")
                return False
            sitekey = uuid_match.group(1)
            log(f"Sitekey: {sitekey}")

            # Solve CAPTCHA
            token = solve_funcaptcha(page.url, sitekey)
            if not token:
                log("CAPTCHA solve failed", "❌")
                return False

            # Inject token via HTTP API (same as setup-enforcement.js flow)
            log("Injecting token via API...", "💉")

            # Get session data from page
            session_data = await page.evaluate('''() => {
                const el = document.getElementById('setup-enforcement');
                if (!el) return null;
                return {
                    sessionId: el.getAttribute('data-sessionId'),
                    securityData: el.getAttribute('data-securityData'),
                    resultEndpoint: el.getAttribute('data-resultEndpoint'),
                    registrationEndpoint: el.getAttribute('data-registrationEndpoint'),
                    defaultRedirect: el.getAttribute('data-defaultRedirect'),
                };
            }''')
            log(f"Session: {session_data}")

            if not session_data:
                log("No session data found", "❌")
                return False

            # Step 1: POST token to result endpoint
            result_url = f"https://devcloud.amd.com{session_data['resultEndpoint']}"
            result_resp = await page.evaluate(f'''async () => {{
                const resp = await fetch("{result_url}", {{
                    method: 'POST',
                    body: JSON.stringify({{
                        arkose_session_token: "{token}",
                        session_id: "{session_data['sessionId']}"
                    }}),
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }},
                    credentials: 'same-origin'
                }});
                return await resp.json();
            }}''')
            log(f"Result response: {result_resp}")

            if not result_resp.get('solved'):
                # Check if "already registered" in error
                err_str = json.dumps(result_resp).lower()
                if 'already' in err_str or 'exists' in err_str or 'taken' in err_str:
                    log("Account already registered!", "⚠️")
                    return True
                log("Token not accepted", "❌")
                return False

            # Step 2: Complete registration
            reg_url = f"https://devcloud.amd.com{session_data['registrationEndpoint']}"
            reg_resp = await page.evaluate(f'''async () => {{
                const resp = await fetch("{reg_url}", {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }},
                    credentials: 'include'
                }});
                return await resp.json();
            }}''')
            log(f"Registration response: {reg_resp}")

            if reg_resp.get('id'):
                redirect = reg_resp.get('redirect_url') or session_data.get('defaultRedirect', '/projects')
                log(f"Registration success! Redirect: {redirect}", "✅")
                await page.goto(f"https://devcloud.amd.com{redirect}", wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                return True
            else:
                # Check if "already registered"
                errors = reg_resp.get('errors', [])
                err_str = json.dumps(reg_resp).lower()
                if 'already' in err_str or 'exists' in err_str or 'taken' in err_str:
                    log("Account already registered!", "⚠️")
                    return True  # Count as success
                log(f"Registration failed: {reg_resp}", "❌")
                return False

        # Check result
        final_url = page.url
        page_text = (await page.inner_text('body')).lower()
        log(f"URL: {final_url}")

        if any(s in page_text for s in ['check your email', 'verify', 'success', 'registered', 'welcome', 'dashboard']):
            log("Account created!", "✅")
            return True
        elif 'already' in page_text:
            log("Account already exists", "⚠️")
            return True  # Count as success
        elif 'error' in page_text:
            log(f"Error on page", "❌")
            return False
        else:
            log(f"Unknown state", "⚠️")
            await page.screenshot(path=f"/tmp/do_result_{email_addr.split('@')[0]}.png")
            return False

    except Exception as e:
        log(f"Error: {str(e)[:120]}", "❌")
        return False


# ============ PIPELINE ============
async def process_one(email_addr, results, page, link=None, timeout=180):
    """Full pipeline: fetch email links → register DO → verify."""
    if email_addr in results and results[email_addr].get('status') == 'success':
        log(f"Already done, skipping", "⏭️")
        return True

    print(f"\n{'='*50}")
    print(f"  {email_addr}")
    print(f"{'='*50}")

    # Step 0: Fetch "Confirm your AMD Developer Cloud account" link
    confirm_link = confirm_email(email_addr, timeout=timeout)
    if confirm_link:
        log("Visiting confirm link...", "🔗")
        confirmed = await visit_confirm(page, confirm_link)
        if confirmed:
            log("AMD account confirmed!", "✅")
        else:
            log("Confirm visit failed, continuing...", "⚠️")
        await asyncio.sleep(5)
    else:
        log("No confirm email found, maybe already confirmed", "⚠️")

    # Step 1: Fetch "Welcome to the AMD developer cloud" → DO waves link
    if not link:
        link = fetch_do_link(email_addr, timeout=timeout)
    if link:
        log(f"DO link ready: {link[:60]}...", "🔗")
    else:
        log("No DO link found, will try direct registration", "⚠️")

    # Step 2: Register DO account (with link if available)
    ok = await register_do(page, email_addr, link)

    if ok:
        results[email_addr] = {
            'status': 'success',
            'password': PASSWORD,
            'name': email_to_name(email_addr),
            'time': datetime.now().isoformat(),
        }
        save_results(results)

        # Save to success.txt with date
        with open(SUCCESS_FILE, "a") as f:
            f.write(f"{email_addr}:{PASSWORD}:{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    else:
        results[email_addr] = {'status': 'register_failed'}
        save_results(results)
    return ok


async def main():
    import argparse
    p = argparse.ArgumentParser(description="DigitalOcean Auto Activate")
    p.add_argument('--input', type=str, help='JSON file with [{email, link}]')
    p.add_argument('--email', type=str, help='Process single email')
    p.add_argument('--all', action='store_true', help='Process all in success.txt')
    p.add_argument('--timeout', type=int, default=180, help='Email wait timeout (s)')
    args = p.parse_args()

    results = load_results()

    # Collect emails
    email_links = {}
    emails = []
    if args.input:
        with open(args.input) as f:
            items = json.load(f)
        for item in items:
            email_links[item['email']] = item.get('link')
        emails = list(email_links.keys())
        print(f"Loaded {len(emails)} from {args.input}")
    elif args.email:
        emails = [args.email]
    elif args.all:
        if SUCCESS_FILE.exists():
            with open(SUCCESS_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        email = line.split(':')[0].strip()
                        if email:
                            emails.append(email)
        print(f"Found {len(emails)} emails in success.txt")
    else:
        print("Use --input, --email, or --all")
        return

    # Filter already done
    todo = [e for e in emails if e not in results or results[e].get('status') != 'success']

    if not todo:
        print("\nAll done! Nothing to process.")
        return

    print(f"\n{'='*50}")
    print(f"  DigitalOcean Auto Activate")
    print(f"  Total: {len(todo)} | Already done: {len(emails) - len(todo)}")
    print(f"{'='*50}\n")

    # Launch browser
    import cloakbrowser
    browser = await cloakbrowser.launch_async(
        headless=True,
        args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage']
    )

    ok_count = 0
    fail_count = 0

    for idx, email_addr in enumerate(todo):
        print(f"\n[{idx+1}/{len(todo)}]", end="")
        link = email_links.get(email_addr)

        page = await browser.new_page()
        ok = await process_one(email_addr, results, page, link=link, timeout=args.timeout)
        await page.close()

        if ok:
            ok_count += 1
        else:
            fail_count += 1

        if idx < len(todo) - 1:
            delay = random.uniform(8, 15)
            log(f"Waiting {delay:.0f}s...", "⏳")
            await asyncio.sleep(delay)

    await browser.close()

    print(f"\n{'='*50}")
    print(f"  DONE")
    print(f"  ✅ Success: {ok_count}")
    print(f"  ❌ Failed: {fail_count}")
    print(f"  Results: {RESULTS_FILE}")
    print(f"{'='*50}")


if __name__ == '__main__':
    asyncio.run(main())
