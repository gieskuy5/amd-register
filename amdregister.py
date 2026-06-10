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
    # Academic / research
    "protein folding simulations using PyTorch Geometric, currently on A100s but want to test MI300X",
    "Computational fluid dynamics for aerospace. Running OpenFOAM coupled with ML surrogate models.",
    "PhD student here. Doing molecular dynamics with JAX, need to see if ROCm can handle our custom kernels.",
    "Climate modeling ensemble runs. We burn through GPU hours like crazy, exploring all options.",
    "genomics pipeline - whole genome sequencing alignment + variant calling, RAPIDS cudf would save us weeks",
    "Physics-informed neural networks for solving PDEs in porous media. Testing JAX on different hardware.",
    "Training transformer models for drug discovery. Our lab has been CUDA-only and we want to diversify.",
    "Radio astronomy data processing. Think massive FFTs and beamforming, not typical ML stuff.",
    "my research is on neural radiance fields (NeRF) for cultural heritage preservation. need decent GPU for training",
    "Bioinformatics lab doing single-cell RNA-seq analysis at scale. RAPIDS + scanpy pipeline.",
    "Quantum chemistry calculations. We use PyTorch for ML potentials in molecular simulations.",
    "Seismic data processing for oil exploration. Heavy on signal processing and some deep learning.",
    "reinforcement learning for robotic manipulation. MuJoCo + PyTorch, currently limited by our 3090s",
    "Weather prediction using graph neural networks on global atmospheric data. Huge training runs.",
    "doing my masters thesis on 3D object detection for autonomous driving, need more GPU than my laptop lol",
    "Cryo-EM structure determination. The image processing pipeline is extremely GPU-hungry.",
    "Particle physics - training classifiers on LHC collision data. Terabytes of training data.",
    "Computational materials science. Running DFT calculations accelerated with ML interatomic potentials.",
    "NLP for low-resource African languages. Fine-tuning mBERT and XLM-R on custom corpora.",
    "gravitational wave data analysis. Matched filtering + ML anomaly detection on LIGO data.",
    # Startup / product
    "fraud detection system for a fintech startup. Real-time inference, latency matters a lot.",
    "building a video understanding platform. need to run inference on hours of footage daily.",
    "recommendation system for e-commerce, currently training on GCP but costs are killing us",
    "speech synthesis startup. Training custom TTS models, burning through compute credits fast.",
    "we're building an AI copilot for legal document review. lots of long-context inference.",
    "Real-time object detection for warehouse robotics. Need low-latency inference at the edge but also cloud training.",
    "founded a startup doing AI for agriculture - crop disease detection from drone imagery",
    "content moderation at scale. Millions of images/day need classification, looking at ROCm for inference.",
    "Building a platform for synthetic data generation. GANs and diffusion models, very GPU intensive.",
    "health-tech startup using NLP to extract info from clinical notes. HIPAA compliant infra needed.",
    "ad tech company, training CTR prediction models on massive clickstream data. need speed.",
    "autonomous delivery robots. Training perception models in simulation before deploying on hardware.",
    "digital twin platform for manufacturing. PyTorch models for predictive maintenance.",
    "AI tutoring platform - fine-tuning LLMs on educational content. Budget is tight honestly.",
    "building a search engine for scientific papers. Embedding models + vector DB, lots of indexing.",
    # Open source / frameworks
    "contributor to vLLM. Testing paged attention kernels on MI250X, found some issues I want to debug.",
    "maintaining a PyTorch extension library for graph neural networks. Need ROCm CI runners.",
    "working on an open-source alternative to Triton for writing portable GPU kernels",
    "helping port DeepSpeed ZeRO optimization to ROCm. Some ops still missing, working through it.",
    "contributor to Hugging Face transformers. Need to test model compatibility on AMD hardware.",
    "building an open-source ML compiler stack. Want to target both CUDA and ROCm from day one.",
    "developing a distributed training framework similar to Megatron-LM but for smaller labs",
    "porting JAX custom ops from CUDA to HIP. Some tricky memory management stuff.",
    "open-source project for privacy-preserving ML. Using secure enclaves + GPU computation.",
    "contributing to ONNX Runtime. Need to verify AMD EPYC + MI250X perf for large transformer models.",
    # ML engineering / training
    "fine-tuning Llama models on domain-specific data. Currently 70B, need multi-GPU badly.",
    "training a diffusion model from scratch on 50M images. This is gonna take a while.",
    "building a training pipeline for multimodal models. Image + text encoders, contrastive learning.",
    "data preprocessing pipeline. Massive pandas operations that could use RAPIDS cuDF instead.",
    "hyperparameter optimization at scale. Running hundreds of experiments in parallel.",
    "model distillation - compressing a 13B model down to 3B while retaining quality",
    "building an inference serving platform. Need to compare vLLM vs TGI on AMD vs NVIDIA.",
    "RLHF training pipeline for a conversational model. PPO with a reward model, lots of GPU memory.",
    "pre-training a vision transformer from scratch on proprietary medical imaging data",
    "converting PyTorch models to ONNX and then optimizing for inference on various hardware",
    # Domain-specific
    "autonomous vehicle perception stack. LiDAR point cloud processing + camera fusion models.",
    "building AI models for drug-target interaction prediction. Graph neural nets on molecular data.",
    "computational fluid dynamics with ML. Using physics-informed neural networks as PDE solvers.",
    "AI for smart grid optimization. Load forecasting and demand response models.",
    "natural language understanding for a voice assistant. Conformer-based ASR + NLU pipeline.",
    "robotic surgery assistance. Real-time segmentation of surgical instruments from endoscopy video.",
    "satellite imagery analysis for deforestation monitoring. Semantic segmentation at global scale.",
    "music generation using transformers. Training on a large MIDI corpus.",
    "building a deepfake detection system. Lots of video processing and binary classification.",
    "AI-assisted chip design. Using ML for placement and routing optimization in VLSI flows.",
    "stock market prediction, sounds cliché but it's actually for volatility surface modeling",
    "protein design using generative models. Inverse folding + structure prediction.",
    "radiology report generation. Vision-language models that explain what they see in X-rays.",
    "supply chain demand forecasting. Time series models, nothing fancy but we need the compute.",
    "developing AI for real-time strategy game bots. RL with self-play, very sample inefficient.",
    "speech enhancement for hearing aids. Small model, but need to train on tons of noisy audio.",
    "credit scoring models for microfinance in developing countries. Tabular data + some NLP.",
    "building a tool to detect AI-generated text. Irony of ironies, but someone has to do it.",
    "neural architecture search for efficient edge models. AmoebaNet-style evolutionary approach.",
    "AI-powered quality control in semiconductor manufacturing. Anomaly detection on wafer images.",
    # Mixed / casual
    "just trying to run stable diffusion faster honestly. also exploring fine-tuning SDXL.",
    "hobby project - training a language model on all of wikipedia. dont judge me",
    "student doing coursework on parallel computing. need GPU access for class assignments.",
    "evaluating AMD hardware for our university's new HPC cluster. Comparing against A100 baseline.",
    "migrating our inference pipeline from AWS to AMD cloud. We serve 10M requests/day.",
    "testing ROCm support for our custom CUDA kernels. Some use warp-level primitives.",
    "we do video transcoding with AI upscaling. Think ffmpeg + neural super-resolution.",
    "building a RAG pipeline with local LLMs. Need GPU for both embedding and generation.",
    "anomaly detection on IoT sensor data from industrial equipment. Time series + autoencoders.",
    "real-time translation service. Encoder-decoder models serving 50+ language pairs.",
    "training a code generation model on our internal codebase. Need to keep it private obv.",
    "medical image registration using deep learning. Aligning CT and MRI scans.",
    "weather nowcasting using radar data. ConvLSTM models, surprisingly GPU hungry.",
    "developing custom CUDA/HIP kernels for sparse matrix operations in our solver.",
    "building a personal assistant that runs locally. LLaMA + whisper + some TTS model.",
    "large-scale knowledge graph embedding. TransE and RotatE on Wikidata-scale graphs.",
    "autonomous drone navigation in GPS-denied environments. Visual SLAM + learned policies.",
    "text-to-3D generation. DreamFusion-style approach, need lots of GPU hours.",
    "developing a platform for digital pathology. Whole slide images are enormous.",
    "training recommender models for a streaming platform. User-item interaction data, billions of rows.",
    "edge deployment optimization. Quantizing and pruning models for AMD NPUs if available.",
    "molecular generation for drug design. VAEs operating on SMILES representations.",
    "Building a local-first AI assistant. Need efficient inference, exploring ROCm for that.",
    "real-time pose estimation for sports analytics. Multi-person tracking across camera views.",
    "federated learning for healthcare. Training across hospital silos without sharing patient data.",
    "sentiment analysis on financial news for algorithmic trading signals.",
    "we're porting our TensorFlow recommendation model to PyTorch and want to test on AMD",
    "high-energy physics event generation using normalizing flows. Custom CUDA ops that need HIP porting.",
    "3D reconstruction from phone photos. Multi-view stereo + neural implicit surfaces.",
    "developing AI for precision agriculture. Yield prediction from multispectral satellite data.",
]

OUTCOMES = [
    "See if our training pipeline actually works on MI250X without major code changes",
    "benchmark inference throughput against our current A100 setup",
    "we want to move off NVIDIA cloud and AMD credits would help us evaluate the switch",
    "honestly just need free GPU hours, we're a bootstrapped startup",
    "test ROCm compatibility with PyTorch and our custom ops",
    "evaluate whether to invest in AMD hardware for our university cluster",
    "run our existing JAX codebase on AMD and fix any issues",
    "compare total cost of ownership vs our current cloud GPU spend",
    "validate that our whole ML stack works end-to-end on AMD",
    "we need to serve models in production and AMD cloud looks cheaper",
    "port our CUDA kernels to HIP and see what performance we get",
    "testing, if it works well we'll buy MI300X for our on-prem cluster",
    "want to contribute ROCm support to our open-source project",
    "training efficiency comparison, that's the main thing",
    "trying to get off the NVIDIA monopoly tbh",
    "evaluate AMD for our distributed training workloads across multiple nodes",
    "need GPU compute for a research project, exploring all available cloud options",
    "check if vLLM runs properly on AMD hardware for our serving needs",
    "we're building a new product and want to use AMD from the start",
    "migrate from CUDA to ROCm for our inference fleet",
    "performance per dollar analysis for our specific workload",
    "test our data pipeline with RAPIDS on AMD GPUs",
    "proof of concept before we commit to a big hardware purchase",
    "need to run experiments for a paper deadline next month",
    "our CUDA code needs to become portable, AMD access lets us test HIP ports",
    "compare MI300X memory bandwidth advantage for our large model inference",
    "evaluate DeepSpeed training on AMD for our 70B parameter model",
    "just exploring honestly, heard good things about MI300X for LLMs",
    "validate our ONNX runtime optimizations on AMD EPYC + GPU combo",
    "we want to offer AMD as an option to our platform users",
    "testing numerical precision differences between NVIDIA and AMD for scientific computing",
    "get our CI/CD pipeline running tests on AMD hardware too",
    "long-term we want hardware diversity so we're not locked into one vendor",
    "research grant requires us to evaluate multiple hardware platforms",
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
