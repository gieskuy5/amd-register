#!/usr/bin/env python3
"""
AMD Cloud Credit — Full Pipeline
=================================
1. Register account at www.amd.com (CloakBrowser)
2. Fetch activation token from email (IMAP)
3. Activate account with token + password (CloakBrowser)
4. Login via Okta → Bearer token (HTTP)
5. Submit credit request (Marketo form)

Usage:
  python3 amdregister.py --count 3
  python3 amdregister.py --email user@domain.com --name "Erik Hansen" --company "MIT" --country US
"""

import asyncio, json, re, time, random, string, hashlib, base64, codecs, os, sys
import imaplib, email as em_mod, urllib.parse, requests as req
from pathlib import Path
from datetime import datetime
import cloakbrowser

# ═══════════════════════════════════════════════════════════════
# CONFIG (from config.json)
# ═══════════════════════════════════════════════════════════════
CONFIG_FILE = Path(__file__).parent / "config.json"
with open(CONFIG_FILE) as f:
    CFG = json.load(f)

PASSWORD = CFG["password"]
IMAP_HOST = CFG["imap_host"]
IMAP_USER = CFG["imap_user"]
IMAP_PW = CFG["imap_password"]

REGISTER_URL = "https://www.amd.com/en/registration/ai-dev-program-sign-up-form.html"
CUSTTARG = "aHR0cHM6Ly9kZXZlbG9wZXIuYW1kLmNvbT9SZWxheVN0YXRlPQ=="
ACTIVATE_URL = "https://www.amd.com/en/registration/activate-account.html"

OKTA = "https://login.amd.com"
DEV_AMD = "https://developer.amd.com"
CID = "0oa10nnl4wplbzM16698"
REDIR = "https://developer.amd.com/auth/callback"
EMAIL_AUTH = "aut1uh73i3v040uEU697"
CREDIT_FORM_URL = "https://anchor.digitalocean.com/amd-cloud-free-credit.html"

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
SUCCESS_FILE = Path(__file__).parent / "success.txt"

FINGERPRINTS = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36", "platform": "macOS"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36", "platform": "Linux"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15", "platform": "macOS"},
]


def log(msg, icon="•"):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def gen_cv(n=64):
    return ''.join(random.choices(string.ascii_letters + string.digits + "-._~", k=n))


def gen_cc(cv):
    return base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).rstrip(b'=').decode()


def gen_rd(n=16):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def find_st(html):
    idx = html.find('"stateToken":"')
    if idx < 0: return None
    start = html.index('"', html.index(':', idx)) + 1
    i = start
    while i < len(html):
        if html[i] == '\\': i += 2; continue
        if html[i] == '"': break
        i += 1
    return codecs.decode(html[start:i], 'unicode_escape')


# ═══════════════════════════════════════════════════════════════
# REALISTIC DATA
# ═══════════════════════════════════════════════════════════════
EMAIL_DOMAINS = ["richardsheingold.com"]

NAMES = [
    # Asia
    ("Hiroshi", "Tanaka", "JP", "University of Tokyo"),
    ("Yuki", "Watanabe", "JP", "Kyoto University"),
    ("Wei", "Chen", "CN", "Tsinghua University"),
    ("Li", "Zhang", "CN", "Peking University"),
    ("Priya", "Sharma", "IN", "IIT Bombay"),
    ("Ravi", "Kumar", "IN", "IISc Bangalore"),
    ("Min-Jun", "Kim", "KR", "KAIST"),
    ("Ji-Hoon", "Lee", "KR", "Seoul National University"),
    ("Putu", "Wijaya", "ID", "ITB Bandung"),
    ("Made", "Suryana", "ID", "Universitas Indonesia"),
    ("Budi", "Santoso", "ID", "UGM Yogyakarta"),
    ("Rizki", "Pratama", "ID", "ITS Surabaya"),
    ("Dewi", "Lestari", "ID", "Universitas Gadjah Mada"),
    ("Siti", "Rahmawati", "ID", "UI Jakarta"),
    ("Ahmad", "Hidayat", "ID", "ITB Bandung"),
    ("Thanh", "Nguyen", "VN", "VNU Hanoi"),
    # Europe
    ("Erik", "Hansen", "DK", "Technical University of Denmark"),
    ("Lars", "Eriksson", "SE", "KTH Royal Institute"),
    ("Henrik", "Johansson", "SE", "Uppsala University"),
    ("Sophie", "Dubois", "FR", "Sorbonne University"),
    ("Marco", "Bianchi", "IT", "Politecnico di Milano"),
    ("Lena", "Muller", "DE", "TU Munich"),
    ("Felix", "Schmidt", "DE", "RWTH Aachen"),
    ("Pablo", "Garcia", "ES", "Universidad Complutense"),
    ("Emma", "Wilson", "GB", "University of Oxford"),
    ("James", "Thompson", "GB", "Imperial College London"),
    ("Isabella", "De Jong", "NL", "TU Delft"),
    ("Viktor", "Petrov", "RU", "Skoltech"),
    ("Stefan", "Kowalski", "PL", "University of Warsaw"),
    ("Nikolai", "Andersen", "FI", "Aalto University"),
    # Africa
    ("Ahmed", "Mansour", "EG", "Cairo University"),
    ("Fatima", "Zahra", "EG", "AUC"),
    ("Ali", "Reza", "SA", "KAUST"),
    ("Aisha", "Okafor", "NG", "University of Lagos"),
    ("Lerato", "Ndlovu", "ZA", "University of Cape Town"),
    ("Samir", "Benali", "MA", "Mohammed V University"),
    # Americas
    ("Michael", "Johnson", "US", "MIT"),
    ("Sarah", "Williams", "US", "Stanford University"),
    ("David", "Martinez", "US", "Carnegie Mellon University"),
    ("Roberto", "Ferreira", "BR", "UNICAMP"),
    ("Sofia", "Mendez", "MX", "UNAM"),
    ("Chloe", "Tremblay", "CA", "University of Toronto"),
]

COUNTRY_LABELS = {
    "JP": "Japan", "CN": "China", "IN": "India", "KR": "Korea, Republic of",
    "ID": "Indonesia", "VN": "Vietnam", "DK": "Denmark", "SE": "Sweden",
    "FR": "France", "IT": "Italy", "DE": "Germany", "ES": "Spain",
    "GB": "United Kingdom", "NL": "Netherlands", "RU": "Russian Federation",
    "PL": "Poland", "FI": "Finland", "EG": "Egypt", "SA": "Saudi Arabia",
    "NG": "Nigeria", "ZA": "South Africa", "MA": "Morocco", "US": "United States",
    "BR": "Brazil", "MX": "Mexico", "CA": "Canada",
}

USE_CASES = [
    "fine-tuning LLaMA models for medical Q&A, need to test if our PyTorch code works on ROCm without too much pain",
    "we're building a fraud detection pipeline for a fintech startup. currently on AWS but looking at alternatives, the cost savings on AMD could be significant",
    "PhD research in protein folding. using JAX for molecular dynamics simulations and the MI300X memory is really attractive for our workloads",
    "migrating our recommendation system from nvidia. we use tensorflow and need to verify compatibility before commiting",
    "Working on real-time video analytics for security cameras. Need to benchmark inference latency on AMD GPUs vs what we currently get",
    "open source contributer to huggingface transformers. want to make sure ROCm support stays up to date and test new model architectures",
    "My team at a biotech company is training diffusion models for drug discovery. We need serious GPU memory for our batch sizes",
    "indie game dev here. exploring GPU-accelerated physics simulation for procedural terrain generation, vulkan compute shaders",
    "climate modeling research group. we run massive ensemble simulations and need cost-effective GPU compute. Currently evaluating MI250X",
    "building a RAG pipeline for legal document analysis at a law firm. using vLLM for serving and need to test it on AMD",
    "startup CTO - we do automated video editing with ML. our inference costs are killing us, exploring AMD cloud as alternative",
    "genomics pipeline using RAPIDS/cuDF. need to check if similar perf is achievable on ROCm for our ETL workloads",
    "Working on autonomous drone navigation. The neural net runs on Jetson for deployment but we train on cloud GPUs",
    "we have a custom transformer architecture for time-series forecasting in energy markets. pytorch + deepspeed for distributed training",
    "contributing to the Triton compiler project and need AMD hardware to test generated HIP kernels",
    "Computational fluid dynamics for aerospace applications. Currently using CUDA but interested in porting to HIP/ROCm",
    "my lab does NLP research on low-resource African languages. we need to fine-tune models and compute budget is tight",
    "Building a voice cloning system. Training is super memory intensive and we keep running out of VRAM on our current setup",
    "medical imaging startup - training segmentation models on 3D CT scans. the 192GB on MI300X would be a game changer for us",
    "we're building an AI coding assistant. need to serve a 70B parameter model with acceptable latency for autocomplete",
    "research on graph neural networks for molecular property prediction. need GPU access for hyperparameter sweeps",
    "Working on document OCR for handwritten historical texts. Fine-tuning Florence-2 and need cost-effective training",
    "our team maintains an open-source robotics simulation framework. want to add ROCm support and need hardware to test on",
    "quantitative trading firm. we use ML for signal generation and need fast inference, exploring AMD's inference capabilities",
    "training a multilingual speech recognition model. we use fairseq and need to verify it works on AMD hardware first",
    "Building a customer support chatbot platform. We serve multiple fine-tuned models per customer, need efficient multi-tenant inference",
    "PhD student working on neural architecture search. burning through GPU hours like crazy, AMD credits would help a lot",
    "we do video transcoding with ML-enhanced upscaling for a streaming platform. looking at ROCm for our encoding pipeline",
    "developing an anomaly detection system for manufacturing quality control. cameras on the factory floor, models in the cloud",
    "I contribute to the DeepSpeed library and need AMD GPUs to test ZeRO-3 optimizations and mixed precision training",
    "autonomous vehicle perception stack. training BEV transformers on huge datasets, need serious compute and memory bandwidth",
    "building tools for synthetic data generation using GANs. our current cloud bill is insane and exploring AMD alternatives",
    "research in computational neuroscience, simulating large-scale brain networks. considering ROCm for our simulation code",
    "we have an e-commerce platform and our product search uses embeddings. need to retrain the model quarterly on fresh data",
    "Working on a project that does real-time style transfer for live video. Need low-latency inference on GPU",
    "Fine-tuning stable diffusion for a design tool product. Training is expensive so any cost reduction helps",
    "my team builds ML infrastructure at a large bank. evaluating AMD as a second GPU vendor for model training",
    "doing thesis work on efficient attention mechanisms. need to benchmark on different GPU architectures including MI300",
    "We are developing a platform for automated pathology slide analysis. Whole slide images are enormous so memory matters a lot",
    "startup doing AI for agriculture - crop disease detection from drone imagery. we train custom YOLO models",
    "porting our CUDA-based molecular visualization tool to work with HIP. Need AMD hardware for testing and debugging",
    "working on text-to-3D generation using score distillation. the training loop is brutal on VRAM",
    "building an internal search engine for our company's knowledge base. using sentence transformers and need inference infra",
    "research on continual learning - models that learn new tasks without forgetting. long training runs need reliable GPU access",
    "we make a mobile app that does real-time translation. Server-side inference for the heavy models, need to optimize for AMD",
    "developing a framework for privacy-preserving ML using secure enclaves and GPU acceleration. testing on ROCm",
    "training RL agents for warehouse robotics. simulation2real pipeline, heavy compute for the sim phase",
    "Working on knowledge graph completion with graph transformers. Need to run ablation studies across many configurations",
    "I'm a solo developer building an AI writing tool. using open source models and need affordable inference",
    "our lab studies protein-protein interactions using geometric deep learning. PyTorch Geometric on AMD is what we want to test",
    "building a music generation system. transformer-based, trained on MIDI data. the training is sequential so we need fast single GPUs",
    "Working on semantic segmentation for satellite imagery analysis. Large tile sizes mean we need GPUs with lots of memory",
    "we are porting our recommendation model serving stack from TensorRT to something that works on AMD. exploring vLLM and ONNX",
    "computational geometry research, using neural implicit representations for 3D reconstruction. NeRF-style models eat memory",
    "developing a multimodal model that combines text, images and tabular data for financial analysis",
    "training a large TTS model. dataset is 50k hours of audio. we need distributed training that actually works on AMD",
    "We're a healthcare company building clinical NLP models to extract info from unstructured medical records",
    "I work in materials science. using ML potentials for crystal structure prediction. need GPU compute for DFT calculations",
    "building an end-to-end speech processing pipeline: VAD, diarization, ASR, and summarization. All on GPU",
    "my team is evaluating AMD GPUs for our next-gen data center. we run a mix of training and inference workloads",
    "developing a platform for automated ML model debugging and explainability. need GPU for computing SHAP values at scale",
    "research on world models for embodied AI agents. training takes weeks, need reliable and cost-effective GPU access",
    "porting a CUDA raytracer to ROCm for scientific visualization. Some custom kernels need rewriting in HIP",
    "Building a document intelligence platform. Layout analysis, table extraction, OCR - multiple models chained together",
    "training GPT-style models from scratch for a specific domain (legal). need multi-node training with good interconnect",
    "we do predictive maintenance for industrial equipment. sensor data time-series classification with deep learning",
    "working on neural radiance fields for real estate virtual tours. training per-property models, need parallel GPU access",
]

OUTCOMES = [
    "Benchmark our PyTorch training pipeline on AMD GPUs and compare throughput with what we get on NVIDIA",
    "Evaluate ROCm compatibility for our existing CUDA codebase before we commit to migration",
    "Deploy our inference services on AMD cloud to reduce costs",
    "Test if our JAX-based simulations run correctly on MI300X hardware",
    "We want to understand real-world performance of AMD GPUs for our specific workload before buying dedicated hardware",
    "Validate that DeepSpeed distributed training works properly on AMD multi-GPU setups",
    "See if we can get comparable inference latency for our recommendation model on AMD vs our current setup",
    "Port our HIP kernels and verify correctness + performance",
    "cost reduction for our GPU compute spend, thats really the main thing",
    "Testing AMD cloud as a viable alternative to our current NVIDIA-based infrastructure",
    "Need to verify vLLM works on AMD for our LLM serving needs",
    "evaluate memory bandwidth benefits of MI300X for our memory-bound workloads",
    "Run our full training pipeline end-to-end on AMD hardware to identify any compatibility issues",
    "Get our TensorFlow models running on ROCm without major code changes",
    "Benchmark inference throughput for our multi-model serving platform on AMD GPUs",
    "We need to assess whether AMD cloud can handle our distributed training at scale",
    "testing Triton-compiled kernels on AMD hardware for performance validation",
    "Determine if AMD GPUs can meet our latency requirements for real-time inference",
    "Evaluate total cost of ownership for AMD vs alternatives for our ML infrastructure",
    "Prove to my CTO that AMD is a viable option so we can diversify our GPU vendors",
    "Check ROCm support for PyTorch Geometric and our custom GNN layers",
    "Validate our preprocessing pipeline runs correctly on AMD and identify any gaps",
    "We want hands-on experience with AMD hardware before our next infrastructure procurement cycle",
    "Test mixed precision training stability on AMD GPUs with our specific model architecture",
]


def generate_person():
    first, last, country, company = random.choice(NAMES)
    domain = random.choice(EMAIL_DOMAINS)
    num = random.randint(10, 99)
    email = f"{first.lower()}.{last.lower()}{num}@{domain}"
    github = f"{first.lower()}{last.lower()}{num}"
    return {
        "first": first, "last": last, "email": email, "github": github,
        "company": company, "country_code": country,
        "country_label": COUNTRY_LABELS.get(country, "United States"),
        "use_case": random.choice(USE_CASES), "outcome": random.choice(OUTCOMES),
    }


# ═══════════════════════════════════════════════════════════════
# STEP 1: REGISTER (CloakBrowser)
# ═══════════════════════════════════════════════════════════════
async def step1_register(page, person):
    log(f"Registering: {person['email']}")

    await page.goto(f"{REGISTER_URL}?custtarg={CUSTTARG}", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(5000)

    # Dismiss cookie
    await page.evaluate('() => { const b = document.getElementById("onetrust-accept-btn-handler"); if(b) b.click(); }')
    await page.wait_for_timeout(2000)

    # Fill form
    await page.fill('#form-text-1444782869', person['first'])
    await page.fill('#form-text-1891447162', person['last'])
    await page.fill('#form-text-1830320319', person['email'])
    await page.fill('#form-text-417351009', person['company'])
    await page.select_option('#country-dropdown-1299606956', label=person['country_label'])
    try:
        await page.select_option('#language-dropdown-765462299', label='English')
    except: pass

    # Checkboxes
    await page.evaluate('() => { document.querySelectorAll("#new_form input[type=checkbox]").forEach(cb => { if(!cb.checked) cb.click(); }); }')
    await page.wait_for_timeout(1000)

    # Submit
    await page.evaluate('() => document.getElementById("form-button-1857186030").click()')

    # Wait for redirect
    for i in range(8):
        await page.wait_for_timeout(5000)
        url = page.url
        if "activate" in url.lower():
            log("Registered!", "✅")
            return True
        text = ""
        try: text = await page.inner_text("body")
        except: pass
        if "First Name" in text and len(text) > 500:
            # Retry fill
            await page.fill('#form-text-1444782869', person['first'])
            await page.fill('#form-text-1891447162', person['last'])
            await page.fill('#form-text-1830320319', person['email'])
            await page.fill('#form-text-417351009', person['company'])
            await page.select_option('#country-dropdown-1299606956', label=person['country_label'])
            await page.evaluate('() => { document.querySelectorAll("#new_form input[type=checkbox]").forEach(cb => { if(!cb.checked) cb.click(); }); }')
            await page.evaluate('() => document.getElementById("form-button-1857186030").click()')
            await page.wait_for_timeout(15000)
            if "activate" in page.url.lower():
                log("Registered (retry)!", "✅")
                return True
            break

    log("Registration failed", "❌")
    return False


# ═══════════════════════════════════════════════════════════════
# STEP 2: FETCH ACTIVATION TOKEN (IMAP)
# ═══════════════════════════════════════════════════════════════
def step2_fetch_token(email_addr, timeout=120):
    log(f"Waiting for activation email ({timeout}s)...")
    start = time.time()
    seen = set()

    while time.time() - start < timeout:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(IMAP_USER, IMAP_PW)
            mail.select('INBOX')
            _, nums = mail.search(None, 'TO', f'"{email_addr}"', 'SUBJECT', '"activate"')
            if nums[0]:
                for n in nums[0].split():
                    if n in seen: continue
                    seen.add(n)
                    _, d = mail.fetch(n, '(RFC822)')
                    msg = em_mod.message_from_bytes(d[0][1])
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/html':
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                            elif part.get_content_type() == 'text/plain' and not body:
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    import html as htmlmod
                    clean = re.sub(r'<[^>]+>', '|||', htmlmod.unescape(body))
                    m = re.search(r'Access Token is:[\s|]+([A-Za-z0-9_\-]{5,30})', clean)
                    if m:
                        log(f"Token: {m.group(1)}", "✅")
                        mail.logout()
                        return m.group(1)
            mail.logout()
        except: pass
        time.sleep(10)

    log("Token timeout", "❌")
    return None


# ═══════════════════════════════════════════════════════════════
# STEP 3: ACTIVATE (CloakBrowser)
# ═══════════════════════════════════════════════════════════════
async def step3_activate(page, token):
    log("Activating account...")
    await page.goto(ACTIVATE_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(5000)

    await page.evaluate('() => { const b = document.getElementById("onetrust-accept-btn-handler"); if(b) b.click(); }')
    await page.wait_for_timeout(2000)

    await page.fill('#form-text-30246375', token)
    await page.fill('#form-text-766004985', PASSWORD)
    await page.fill('#form-text-766004985_confirm', PASSWORD)
    await page.wait_for_timeout(1000)
    await page.evaluate('() => { const btn = document.getElementById("form-button-531128439"); if(btn) btn.click(); else { const btns = document.querySelectorAll(".cmp-form-button"); for (const b of btns) { if (b.textContent.trim()) { b.click(); break; } } } }')

    for i in range(10):
        await page.wait_for_timeout(5000)
        url = page.url
        if "developer.amd.com" in url:
            log("Activated!", "✅")
            return True
        text = ""
        try: text = await page.inner_text("body")
        except: pass
        if "success" in text.lower() or "activated" in text.lower() or "congratulations" in text.lower():
            log("Activated!", "✅")
            return True
        if "Access Token" in text and len(text) > 500:
            await page.fill('#form-text-30246375', token)
            await page.fill('#form-text-766004985', PASSWORD)
            await page.fill('#form-text-766004985_confirm', PASSWORD)
            await page.evaluate('() => { const btn = document.getElementById("form-button-531128439"); if(btn) btn.click(); else { const btns = document.querySelectorAll(".cmp-form-button"); for (const b of btns) { if (b.textContent.trim()) { b.click(); break; } } } }')
            await page.wait_for_timeout(15000)
            if "developer.amd.com" in page.url:
                log("Activated (retry)!", "✅")
                return True
            break

    log("Activation failed", "❌")
    return False


# ═══════════════════════════════════════════════════════════════
# STEP 4: LOGIN → BEARER TOKEN (HTTP)
# ═══════════════════════════════════════════════════════════════
def step4_login(email_addr):
    log("Logging in via Okta...")
    s = req.Session()
    fp = random.choice(FINGERPRINTS)
    s.headers.update({"user-agent": fp["ua"]})
    verifier = gen_cv()

    r = s.get(f"{OKTA}/oauth2/default/v1/authorize", params={
        "client_id": CID, "redirect_uri": REDIR, "response_type": "code",
        "scope": "openid profile email", "state": gen_rd(), "nonce": gen_rd(),
        "code_challenge": gen_cc(verifier), "code_challenge_method": "S256", "response_mode": "query",
    })
    st = find_st(r.text)
    if not st: log("stateToken not found", "❌"); return None

    r1 = s.post(f"{OKTA}/idp/idx/identify", json={
        "identifier": email_addr, "credentials": {"passcode": PASSWORD}, "stateHandle": st,
    }, headers={"accept": "application/json; okta-version=1.0.0", "content-type": "application/json",
                "x-okta-user-agent-extended": "okta-auth-js/6.9.0 okta-signin-widget-6.9.0 okta-hosted"})
    d1 = r1.json()

    # Check if already authenticated (no OTP needed)
    redir = d1.get("success", {}).get("href", "")
    if redir:
        log("Already authenticated, skipping OTP", "✅")
    else:
        sh = d1.get("stateHandle", "")
        if not sh: log("Login failed", "❌"); return None

        r2 = s.post(f"{OKTA}/idp/idx/challenge", json={
            "authenticator": {"id": EMAIL_AUTH, "methodType": "email"}, "stateHandle": sh,
        }, headers={"accept": "application/json; okta-version=1.0.0", "content-type": "application/json",
                    "x-okta-user-agent-extended": "okta-auth-js/6.9.0 okta-signin-widget-6.9.0 okta-hosted"})
        d2 = r2.json()
        sh2 = d2.get("stateHandle", "")
        if not sh2: log("Challenge failed", "❌"); return None

        log("OTP sent, fetching...")
        otp = None
        start_otp = time.time()
        seen = set()
        while time.time() - start_otp < 120:
            try:
                mail = imaplib.IMAP4_SSL(IMAP_HOST)
                mail.login(IMAP_USER, IMAP_PW)
                mail.select('INBOX')
                _, nums = mail.search(None, 'FROM', '"account.help@amd.com"', 'UNSEEN')
                if nums[0]:
                    for n in nums[0].split():
                        if n in seen: continue
                        seen.add(n)
                        _, d = mail.fetch(n, '(RFC822)')
                        msg = em_mod.message_from_bytes(d[0][1])
                        if email_addr.lower() not in msg.get("To", "").lower(): continue
                        body = ""
                        if msg.is_multipart():
                            for p in msg.walk():
                                if p.get_content_type() == "text/plain":
                                    body = p.get_payload(decode=True).decode("utf-8", errors="replace"); break
                        else:
                            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                        cm = re.search(r"(\d{6})", body)
                        if cm: otp = cm.group(1); mail.logout(); break
                mail.logout()
                if otp: break
            except: pass
            time.sleep(5)

        if not otp: log("No OTP", "❌"); return None
        log(f"OTP: {otp}")

        r3 = s.post(f"{OKTA}/idp/idx/challenge/answer", json={
            "credentials": {"passcode": otp}, "stateHandle": sh2,
        }, headers={"accept": "application/json; okta-version=1.0.0", "content-type": "application/json",
                    "x-okta-user-agent-extended": "okta-auth-js/6.9.0 okta-signin-widget-6.9.0 okta-hosted"})
        redir = r3.json().get("success", {}).get("href", "")
        if not redir: log("No redirect", "❌"); return None

    # Follow redirect → auth code → token
    r4 = s.get(redir, allow_redirects=False)
    loc = r4.headers.get("Location", "")
    code = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("code", [None])[0]
    if not code: log("No auth code", "❌"); return None

    r5 = req.post(f"{OKTA}/oauth2/default/v1/token", data={
        "grant_type": "authorization_code", "redirect_uri": REDIR,
        "code": code, "code_verifier": verifier, "client_id": CID,
    }, headers={"accept": "application/json", "content-type": "application/x-www-form-urlencoded"})
    bearer = r5.json().get("access_token", "")
    if bearer: log(f"Bearer OK", "✅"); return bearer
    log("Token failed", "❌"); return None


# ═══════════════════════════════════════════════════════════════
# STEP 5: SUBMIT CREDIT REQUEST (CloakBrowser)
# ═══════════════════════════════════════════════════════════════
async def step5_credit(page, person):
    log("Submitting credit request...")
    await page.goto(CREDIT_FORM_URL, wait_until="networkidle", timeout=60000)
    await page.wait_for_function('typeof MktoForms2 !== "undefined" && MktoForms2.allForms().length > 0', timeout=30000)
    await page.wait_for_timeout(2000)

    form_values = {
        "FirstName": person["first"],
        "Email": person["email"],
        "githubHandle": person["github"],
        "company_linkedin_handle__c_lead": "",
        "Country": person["country_code"],
        "PostalCode": str(random.randint(10000, 99999)),
        "Type__c": random.choice(["Independent developer", "Member of opensource project", "Member of a corporation"]),
        "Company": person["company"],
        "Company__c": person["company"],
        "DaScoopComposer__Email_2__c": person["email"],
        "Contact_Sales_Use_Case__c_lead": person["use_case"],
        "technicalteam": random.choice(["No", "Yes, I am a beginner", "Yes, I am an advanced user"]),
        "h100sUseCase": random.choice(["Inference end point only", "Inference", "Finetuning", "Training"]),
        "Desired_Outcome__c": person["outcome"],
        "Marketing_Comments__c": person["use_case"],
    }

    dev_type = form_values["Type__c"]
    if dev_type == "Member of opensource project":
        form_values["openText"] = f"Contributing to {person['company']} open-source projects. Working on GPU optimization and ROCm compatibility."
    if dev_type == "Member of a corporation":
        form_values["Company__c"] = person["company"]
        form_values["DaScoopComposer__Email_2__c"] = person["email"]

    # Set Type first to trigger conditional fields
    await page.evaluate('(vals) => { MktoForms2.allForms()[0].setValues({"Type__c": vals.Type__c}); }', form_values)
    await page.evaluate('''(val) => {
        const el = document.getElementById("Type__c");
        if (el) { el.value = val; el.dispatchEvent(new Event("change", {bubbles: true})); }
    }''', form_values["Type__c"])
    await page.wait_for_timeout(1500)

    # Set all values via Marketo API
    await page.evaluate('(vals) => { MktoForms2.allForms()[0].setValues(vals); }', form_values)
    await page.wait_for_timeout(1000)

    # Set DOM selects explicitly
    for sel_id in ["Country", "Type__c", "technicalteam", "h100sUseCase"]:
        await page.evaluate(f'''(val) => {{
            const el = document.getElementById("{sel_id}");
            if (el) {{ el.value = val; el.dispatchEvent(new Event("change", {{bubbles: true}})); }}
        }}''', form_values[sel_id])

    await page.wait_for_timeout(500)

    # Validate and fix errors
    is_valid = await page.evaluate('() => MktoForms2.allForms()[0].validate()')
    if not is_valid:
        invalid = await page.evaluate('''() => {
            const els = document.querySelectorAll(".mktoInvalid");
            return Array.from(els).map(e => e.id || e.name);
        }''')
        log(f"Fixing invalid: {invalid}", "⚠️")
        for field_id in invalid:
            if field_id in form_values:
                tag = await page.evaluate(f'() => document.getElementById("{field_id}")?.tagName')
                if tag == "SELECT":
                    await page.select_option(f"#{field_id}", form_values[field_id])
                else:
                    await page.fill(f"#{field_id}", form_values[field_id])
        await page.wait_for_timeout(500)
        await page.evaluate('(vals) => { MktoForms2.allForms()[0].setValues(vals); }', form_values)

    # Submit via Marketo API
    await page.evaluate('() => MktoForms2.allForms()[0].submit()')

    # Wait for redirect
    try:
        await page.wait_for_url("**/devcloud.amd.com/**", timeout=30000)
        log("Credit request submitted!", "✅")
        return True
    except:
        if "devcloud" in page.url:
            log("Credit request submitted!", "✅")
            return True

    log("Credit may have failed", "⚠️")
    return False


# ═══════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════
async def run_pipeline(person):
    email = person["email"]
    print(f"\n{'='*60}")
    print(f"  {person['first']} {person['last']} | {email}")
    print(f"  {person['company']} | {person['country_label']}")
    print(f"{'='*60}")

    # Launch CloakBrowser
    browser = await cloakbrowser.launch_async(headless=True, args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    page = await browser.new_page()

    try:
        # Step 1: Register
        if not await step1_register(page, person):
            return {"email": email, "status": "REGISTER_FAILED"}

        # Step 2: Fetch token
        await asyncio.sleep(15)
        token = step2_fetch_token(email, timeout=90)
        if not token:
            return {"email": email, "status": "NO_TOKEN"}

        # Step 3: Activate
        if not await step3_activate(page, token):
            return {"email": email, "status": "ACTIVATE_FAILED"}

        # Step 4: Login (HTTP)
        await asyncio.sleep(5)
        bearer = step4_login(email)
        if not bearer:
            return {"email": email, "status": "LOGIN_FAILED"}

        # Step 5: Credit request
        if not await step5_credit(page, person):
            return {"email": email, "status": "CREDIT_FAILED"}

        with open(SUCCESS_FILE, "a") as f:
            f.write(f"{email}:{PASSWORD}:{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        return {"email": email, "status": "SUCCESS"}
    finally:
        await browser.close()


async def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--email")
    p.add_argument("--name")
    p.add_argument("--company", default="MIT")
    p.add_argument("--country", default="US")
    args = p.parse_args()

    if args.email:
        parts = (args.name or args.email.split("@")[0]).split()
        person = {
            "first": parts[0], "last": parts[-1] if len(parts) > 1 else "User",
            "email": args.email, "github": args.email.split("@")[0].replace(".", ""),
            "company": args.company, "country_code": args.country,
            "country_label": COUNTRY_LABELS.get(args.country, "United States"),
            "use_case": random.choice(USE_CASES), "outcome": random.choice(OUTCOMES),
        }
        result = await run_pipeline(person)
        print(f"\n  {result['status']}: {result['email']}")
    else:
        print(f"\n🚀 AMD Full Pipeline — {args.count} accounts\n")
        results = []
        for i in range(args.count):
            person = generate_person()
            result = await run_pipeline(person)
            results.append(result)
            await asyncio.sleep(random.uniform(3, 7))

        print(f"\n{'='*60}")
        ok = sum(1 for r in results if r["status"] == "SUCCESS")
        for r in results:
            icon = "✅" if r["status"] == "SUCCESS" else "❌"
            print(f"  {icon} {r['email']:45s} → {r['status']}")
        print(f"\n  Success: {ok}/{len(results)}")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
