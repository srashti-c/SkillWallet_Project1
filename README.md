# SkillWallet_Project1
# 🏗️ Multimodal Construction Intelligence Platform
## Skill Wallet Capstone Project 1

An AI-powered Streamlit application that brings site safety auditing, structural defect diagnostics, project valuation and field assistance into one dashboard. It uses Google Gemini for multimodal analysis, runs with zero external database dependencies, and deploys to Streamlit Community Cloud in one click.

⚠️ **Disclaimer:** All AI output is advisory. Safety-critical and structural decisions must be verified by a licensed engineer or qualified safety officer. Valuation figures are indicative estimates, not a certified valuation.

## ✨ Features

| Tab | Epic | What it does |
|---|---|---|
| 🦺 Site Safety & PPE Audit | Epic 2 | Upload a site photo. Gemini checks helmets, high-vis vests, steel-toe boots and safety harnesses, and identifies hazards against OSHA and IS 456 references. Returns a safety score (0–100), overall status, a PPE checklist and hazards with severity (Low / Medium / High / Critical) and corrective remedies. Downloadable JSON report. |
| 🧱 Crack Diagnostics | Epic 2 | Upload a concrete or wall photo. Classifies the defect (Hairline, Settlement, Structural Shear, Thermal Expansion, Spalling), estimates crack width in mm, and lists root causes, repairs (epoxy injection, structural re-grouting, etc.), urgency and a monitoring plan. Downloadable JSON report. |
| 💰 Planning & Valuation | Epic 3 | Choose structure type, built-up sq ft, location tier (1/2/3) and completion %. Calculates total budget, CapEx incurred, current asset valuation (₹ Lakhs / Crores), steel and cement requirements, and milestone progress. Generates a conceptual 3D render via Pollinations AI. |
| 🌦️ Daily Site Assistant | Epic 5 | Weather selector (High Wind, Heavy Rain, Extreme Heat, Normal) with dynamic safety alerts such as crane suspension, electrical hazard mitigation and concrete curing protocol. Includes a multi-turn construction engineering chatbot. |

**Sidebar:** Secure Gemini API key input (masked), model selector, live/demo status indicator, module navigation and an architecture overview.

**Demonstration mode:** With no API key (or if a Gemini call fails), the app falls back to realistic sample output so every feature can still be explored.

## 🏛️ Architecture

```text
Streamlit UI (tabs)
   │
   ├─ Image modules ──► Pillow ► Gemini Vision (JSON mode)
   │                       └─► schema normaliser ► metric cards / JSON export
   ├─ Valuation engine ─► pure-Python cost model ► Pollinations render URL
   └─ Assistant ───────► Gemini chat (weather-aware system context)

State: st.session_state only
DB:    none
```

## 🚀 Quick Start

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run

```bash
streamlit run app.py
```

### 3. Add your Gemini key

Paste your key into the sidebar field, or create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-key-here"
```

Get a free key from [Google AI Studio](https://aistudio.google.com/). Never commit your key; add `.streamlit/secrets.toml` to `.gitignore`.

## ☁️ Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/) and click **New app**.
3. Select the repository, branch, and set the main file to `app.py`.
4. (Optional) Under **Advanced settings → Secrets**, add:

```toml
GEMINI_API_KEY = "your-key-here"
```

5. Click **Deploy**.

## 📁 Project Structure

```text
.
├── app.py             # Complete Streamlit application
├── requirements.txt   # streamlit, google-genai, Pillow
└── README.md
```

## 🧮 Valuation Model (Tab 3)

| Quantity | Formula |
|---|---|
| Budget | sq ft × base cost/sq ft × tier cost factor |
| CapEx incurred | budget × completion % |
| Value on completion | sq ft × base market rate × tier market factor |
| Current asset valuation | value on completion × completion % (10% risk discount until handover) |
| Steel / cement | Per-sq-ft benchmark by structure type, scaled by completion % |

Rates are indicative benchmarks defined in `STRUCTURE_TYPES` and `TIER_FACTORS` in `app.py`. Edit them to match current local market data.

## 🧰 Tech Stack

- **UI:** Streamlit with custom CSS
- **AI:** Google Gemini via the `google-genai` SDK (vision + JSON output + chat)
- **Imaging:** Pillow
- **Concept renders:** Pollinations AI (URL-based, no key needed)
- **Standards referenced:** OSHA 29 CFR 1926, IS 456:2000, NBC 2016

## 🔒 Privacy & Security

- The API key is held in session memory only and is never stored or logged.
- Uploaded images are processed in memory and sent to the Gemini API only when you run an analysis.
- There is no database and no persistent storage.

## ⚠️ Known Limitations

- Photo-based crack width estimates are approximate; including a coin or ruler for scale improves results.
- Model output can be wrong or incomplete; verify clause references and findings before relying on them.
- Pollinations is a free third-party service and may be slow or unavailable at times.
- The Gemini model names in the sidebar may need updating as Google releases new versions.

## 🗺️ Roadmap

- Video and multi-image site walk-through analysis
- PDF report export
- Bill-of-quantities (BOQ) estimator
- Multilingual (Hindi) assistant and alerts
- Live weather API integration

## 👤 Author

**Srashti Chouhan:** Skill Wallet Capstone Project 1

## 📄 License

Released under the MIT License. Add a `LICENSE` file to your repository if you choose to publish under it.
