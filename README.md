# AMD Developer Cloud — Auto Registration & Credit

Automated pipeline for AMD Developer Cloud account registration, email verification, and GPU credit requests.

## Features

- **Full AMD Pipeline** — Register → Activate → Login → Credit Request
- **DigitalOcean Account** — Auto register + email verification
- **FunCaptcha Solver** — 2Captcha integration
- **Email Automation** — IMAP polling for tokens & verification codes
- **Anti-Detection** — CloakBrowser with fingerprint rotation
- **Realistic Data** — Names, companies, use cases per region

## Scripts

### `amdregister.py`
Full AMD Cloud Credit pipeline:
1. Register at www.amd.com (CloakBrowser)
2. Fetch activation token from email (IMAP)
3. Activate account with token + password
4. Login via Okta → Bearer token (HTTP)
5. Submit credit request (Marketo form)

```bash
python3 amdregister.py --count 3
python3 amdregister.py --email user@domain.com --name "Erik Hansen" --company "MIT" --country US
```

### `do_activate.py`
DigitalOcean account registration:
1. Fetch "Confirm your AMD Developer Cloud account" email → visit link
2. Fetch "Welcome to the AMD developer cloud" email → get DO waves link
3. Register at devcloud.amd.com (using waves link if available)
4. Solve FunCaptcha via 2Captcha
5. Inject token via Arkose API
6. If already registered → auto skip

```bash
python3 do_activate.py --input do_pending.json
python3 do_activate.py --email user@domain.com
python3 do_activate.py --all
```

## Setup

1. Clone repo:
```bash
git clone https://github.com/gieskuy5/amd-register.git
cd amd-register
```

2. Install dependencies:
```bash
pip install cloakbrowser requests
```

3. Create config:
```bash
cp config.example.json config.json
```

4. Edit `config.json` with your credentials:
```json
{
  "password": "your_password",
  "imap_host": "imap.gmail.com",
  "imap_user": "your_email@gmail.com",
  "imap_password": "your_app_password",
  "captcha_key": "your_2captcha_api_key",
  "email_domain": "your_domain.com"
}
```

## Config Fields

| Field | Description |
|-------|-------------|
| `password` | Password for all registered accounts |
| `imap_host` | IMAP server (e.g., imap.gmail.com) |
| `imap_user` | Email address for receiving verification emails |
| `imap_password` | App password for IMAP access |
| `captcha_key` | 2Captcha API key |
| `email_domain` | Domain for catch-all email (e.g., richardsheingold.com) |

## Output Files

- `success.txt` — Successfully registered accounts (`email:password:date`)
- `do_activate_results.json` — DO registration results
- `data/` — Screenshots and debug files

## Requirements

- Python 3.8+
- [CloakBrowser](https://github.com/nicepkg/cloakbrowser) — Stealth browser
- [2Captcha](https://2captcha.com/) — CAPTCHA solving service
- Catch-all email domain — For receiving verification emails

## How It Works

### AMD Registration Flow
```
www.amd.com/register → Fill form → CAPTCHA → Email activation
     ↓
Fetch token from IMAP → Activate account → Okta login
     ↓
Marketo credit form → Set values → Submit → Credits approved
```

### DigitalOcean Registration Flow
```
devcloud.amd.com/register → Fill form → FunCaptcha appears
     ↓
Extract UUID from iframe → 2Captcha solves → Token injected
     ↓
POST to /shield-service/arkose/v1/result → Account created
     ↓
Login → 6-digit code from email → Verify → Dashboard access
```

## Anti-Detection

- CloakBrowser with stealth mode
- User-Agent rotation (8 fingerprints)
- Indonesian SOCKS proxy (optional)
- Random delays between operations
- Unique browser context per account

## Troubleshooting

**CAPTCHA fails:**
- Check 2Captcha balance
- Try again (intermittent failures)

**Email not received:**
- Verify IMAP credentials
- Check spam folder
- Wait longer (up to 3 minutes)

**"Already registered":**
- Script auto-detects and skips to verification
- Account still gets processed

## License

MIT

## Author

[@DezmonDzhino](https://twitter.com/DezmonDzhino)
