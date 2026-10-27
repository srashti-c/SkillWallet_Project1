"""
Multimodal Construction Intelligence Platform
Skill Wallet Capstone Project 1

Single-file Streamlit app. No database. Deploys on Streamlit Community Cloud.
Gemini key: paste in sidebar, or set GEMINI_API_KEY in .streamlit/secrets.toml.
Without a key the app runs in Demonstration Mode with realistic sample output.
"""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import zlib
from datetime import datetime

import streamlit as st
from PIL import Image

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:  # app still runs in demo mode
    GENAI_AVAILABLE = False

# ----------------------------------------------------------------------------
# Page config & styling
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Multimodal Construction Intelligence Platform",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
:root {
  --brand: #f59e0b; --brand-dark: #b45309; --ink: #0f172a; --muted: #64748b;
  --ok: #16a34a; --warn: #d97706; --bad: #dc2626; --crit: #7f1d1d; --card: #ffffff;
}
.hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #b45309 130%);
  padding: 1.6rem 2rem; border-radius: 16px; color: #fff; margin-bottom: 1.2rem;
}
.hero h1 { margin: 0; font-size: 1.9rem; color: #fff; }
.hero p { margin: .35rem 0 0; color: #cbd5e1; font-size: .98rem; }
.metric-card {
  background: var(--card); border: 1px solid #e2e8f0; border-left: 5px solid var(--brand);
  border-radius: 12px; padding: 1rem 1.2rem; box-shadow: 0 1px 3px rgba(15,23,42,.06);
  height: 100%;
}
.metric-card .label { font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.metric-card .value { font-size: 1.65rem; font-weight: 700; color: var(--ink); line-height: 1.25; }
.metric-card .sub { font-size: .8rem; color: var(--muted); }
.pill {
  display: inline-block; padding: .2rem .75rem; border-radius: 999px;
  font-size: .78rem; font-weight: 600; color: #fff; white-space: nowrap;
}
.pill.ok { background: var(--ok); } .pill.low { background: #0891b2; }
.pill.medium { background: var(--warn); } .pill.high { background: var(--bad); }
.pill.critical { background: var(--crit); } .pill.neutral { background: #475569; }
.hazard {
  border: 1px solid #e2e8f0; border-radius: 12px; padding: .85rem 1rem; margin-bottom: .6rem;
  background: #fff; color: #0f172a;
}
.hazard b { color: #0f172a; }
.alert-box { border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: .7rem; border-left: 6px solid; color: #0f172a; }
.alert-high { background: #fef2f2; border-color: var(--bad); }
.alert-med { background: #fffbeb; border-color: var(--warn); }
.alert-ok { background: #f0fdf4; border-color: var(--ok); }
.footer { text-align: center; color: var(--muted); font-size: .8rem; margin-top: 2rem; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
DEFAULT_MODEL = "gemini-2.5-flash"
MAX_IMAGE_SIDE = 1600
SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]

SAFETY_PROMPT = """You are a certified construction safety officer (OSHA 29 CFR 1926 and Indian
IS 456:2000 / BOCW Act aware). Analyse the attached construction site photograph.

Assess PPE for every visible worker: helmet (hard hat), high-visibility vest,
steel-toe safety boots, safety harness (when working at height). Also identify site hazards
(fall exposure, unprotected edges, poor scaffolding, housekeeping, electrical, formwork or
shoring issues, material storage, concrete quality concerns visible against IS 456).

Return ONLY valid JSON, no markdown, matching exactly:
{
  "safety_score": <integer 0-100>,
  "overall_status": "<Compliant | Needs Improvement | Non-Compliant | Critical Risk>",
  "workers_detected": <integer>,
  "summary": "<2-3 sentence summary>",
  "ppe_detection": {
    "helmet": {"detected": <bool>, "note": "<short>"},
    "high_vis_vest": {"detected": <bool>, "note": "<short>"},
    "steel_toe_boots": {"detected": <bool>, "note": "<short>"},
    "safety_harness": {"detected": <bool>, "note": "<short>"}
  },
  "hazards": [
    {"hazard": "<title>", "severity": "<Low|Medium|High|Critical>",
     "standard_reference": "<OSHA / IS code clause>", "remedy": "<corrective action>"}
  ]
}
If something cannot be determined from the image, say so in the note rather than guessing."""

CRACK_PROMPT = """You are a senior structural engineer (IS 456:2000, IS 13935, IS 15988 aware).
Analyse the attached concrete / masonry / wall surface photograph for defects.

Classify the dominant defect as exactly one of:
Hairline, Settlement, Structural Shear, Thermal Expansion, Spalling.
Estimate crack width in millimetres from visual cues (state your uncertainty).

Return ONLY valid JSON, no markdown, matching exactly:
{
  "defect_type": "<one of the five classes>",
  "confidence": <integer 0-100>,
  "estimated_crack_width_mm": <number>,
  "crack_pattern": "<e.g. diagonal / vertical / map-cracking / horizontal>",
  "structural_risk": "<Low | Moderate | High | Severe>",
  "urgency": "<Monitor | Routine (within 3 months) | Priority (within 2 weeks) | Immediate>",
  "root_causes": ["<cause>", "..."],
  "recommended_repairs": [
    {"method": "<e.g. Epoxy injection>", "detail": "<specification>", "applies_when": "<condition>"}
  ],
  "monitoring_plan": "<crack gauge / tell-tale / frequency>",
  "engineer_note": "<caution, limits of photo-based assessment>"
}"""

ASSISTANT_SYSTEM = """You are an experienced Indian construction engineering assistant for a site team.
Give practical, safety-first, concise answers referencing IS codes (IS 456, IS 800, IS 875, IS 1893,
IS 4326), NBC 2016 and OSHA where relevant. Use bullet points for procedures. For anything structural
or life-safety critical, state that a licensed engineer must verify on site. Do not invent clause
numbers; if unsure say so."""

STRUCTURE_TYPES = {
    # cost INR/sqft (Tier-2 baseline), market value INR/sqft (Tier-2), steel kg/sqft, cement bags/sqft
    "Residential (RCC Frame)":      {"cost": 1900, "market": 4200,  "steel": 4.0, "cement": 0.42},
    "Premium Villa":                {"cost": 2900, "market": 7000,  "steel": 4.4, "cement": 0.46},
    "Commercial Complex":           {"cost": 2500, "market": 6500,  "steel": 4.8, "cement": 0.45},
    "High-Rise Apartment":          {"cost": 3300, "market": 7500,  "steel": 5.5, "cement": 0.50},
    "Industrial Shed (PEB/Steel)":  {"cost": 1600, "market": 2600,  "steel": 8.0, "cement": 0.18},
    "Institutional (School/Hospital)": {"cost": 2700, "market": 5200, "steel": 4.6, "cement": 0.44},
}
TIER_FACTORS = {
    "Tier 1 (Mumbai, Delhi NCR, Bengaluru, Chennai, Hyderabad)": {"cost": 1.25, "market": 1.85},
    "Tier 2 (Indore, Jaipur, Pune, Lucknow, Surat)":             {"cost": 1.00, "market": 1.00},
    "Tier 3 (Udaipur, Bhopal outskirts, small towns)":           {"cost": 0.85, "market": 0.65},
}
MILESTONES = [
    ("Site Prep & Foundation", 15),
    ("Plinth & Substructure", 30),
    ("Superstructure (Columns/Slabs)", 60),
    ("Masonry, MEP & Services", 80),
    ("Finishing & Fixtures", 95),
    ("Handover & Occupancy", 100),
]

WEATHER_ADVISORIES = {
    "High Wind": {
        "level": "high", "icon": "🌬️",
        "headline": "High wind: elevated fall and dropped-load risk",
        "alerts": [
            "SUSPEND crane and hoist operations when sustained wind exceeds the manufacturer limit (typically 36 km/h / 10 m/s), and always when gusts are unpredictable.",
            "Stop all work on exposed scaffolds, tower platforms and roof edges; evacuate and lash down loose sheeting, formwork and materials.",
            "Re-check scaffold ties, bracing and safety nets before resuming; inspect tower crane slew brakes set to 'free-slew'.",
            "Secure hoardings, shuttering panels and stacked bricks; keep people clear of the drop zone.",
        ],
        "checklist": ["Wind speed logged hourly", "Crane in weather-vane mode", "Loose material secured", "Scaffold inspection tagged"],
    },
    "Heavy Rain": {
        "level": "high", "icon": "🌧️",
        "headline": "Heavy rain: electrical, excavation and concrete quality risks",
        "alerts": [
            "ELECTRICAL: de-energise temporary distribution where wet; use ELCB/RCCB-protected circuits only, keep joints off the ground and in IP65 enclosures.",
            "EXCAVATIONS: stop work, check shoring and dewatering; keep spoil at least 1 m from the edge and watch for slope failure.",
            "CONCRETE: do not pour in heavy rain. Cover fresh concrete with tarpaulin, protect against wash-out, and review any pour affected for cement-paste loss.",
            "Slip hazard: add anti-skid walkways and re-inspect ladders, ramps and scaffold boards.",
        ],
        "checklist": ["ELCB tested", "Pumps running in pits", "Tarpaulins on fresh pours", "Access ways cleared"],
    },
    "Extreme Heat": {
        "level": "med", "icon": "🔥",
        "headline": "Extreme heat: worker heat stress and concrete curing protocol",
        "alerts": [
            "WORKERS: enforce shaded rest breaks, ORS / drinking water at every floor, shift heavy work to early morning and late afternoon; watch for heat exhaustion signs.",
            "CONCRETE: keep mix temperature below 35 °C at placing (IS 456 hot-weather guidance); use chilled water or ice, retarding admixture, and wet burlap or curing compound.",
            "Start curing immediately after finishing and keep surfaces continuously moist for at least 7 days (10 days for blended cement or exposed work).",
            "Protect steel and formwork from direct sun before contact; avoid pours in the midday window.",
        ],
        "checklist": ["Water and ORS stations stocked", "Work-rest schedule posted", "Curing crew assigned", "Concrete temperature recorded"],
    },
    "Normal": {
        "level": "ok", "icon": "☀️",
        "headline": "Normal conditions: standard safety protocols apply",
        "alerts": [
            "Hold the daily toolbox talk; verify PPE (helmet, vest, boots, harness at height) before entry.",
            "Complete scaffold, lifting-gear and electrical pre-use checks and sign the daily permit-to-work register.",
            "Maintain good housekeeping: clear walkways, store materials, cover openings.",
        ],
        "checklist": ["Toolbox talk done", "PPE check complete", "Permits issued", "Housekeeping walk done"],
    },
}

# ----------------------------------------------------------------------------
# Demo-mode sample outputs
# ----------------------------------------------------------------------------
DEMO_SAFETY = {
    "safety_score": 58,
    "overall_status": "Needs Improvement",
    "workers_detected": 4,
    "summary": "DEMO DATA. Most workers wear helmets but high-visibility vests and safety harnesses are inconsistent. Edge protection on the upper slab appears incomplete.",
    "ppe_detection": {
        "helmet": {"detected": True, "note": "3 of 4 workers wearing hard hats."},
        "high_vis_vest": {"detected": False, "note": "Vests missing on at least two workers."},
        "steel_toe_boots": {"detected": True, "note": "Safety footwear visible on most workers."},
        "safety_harness": {"detected": False, "note": "No harness visible on worker at slab edge."},
    },
    "hazards": [
        {"hazard": "Unprotected slab edge / fall from height", "severity": "Critical",
         "standard_reference": "OSHA 1926.501; BOCW Rules 1998",
         "remedy": "Install double-rail edge protection with toe boards; mandate harness with anchor points above 1.8 m."},
        {"hazard": "Cluttered walkway with rebar offcuts", "severity": "Medium",
         "standard_reference": "OSHA 1926.25",
         "remedy": "Daily housekeeping; designate offcut bins and keep a 1 m clear route."},
        {"hazard": "Scaffold lacks visible tie-ins and inspection tag", "severity": "High",
         "standard_reference": "OSHA 1926.451; IS 4014",
         "remedy": "Tie scaffold to structure at specified intervals and tag only after competent-person inspection."},
        {"hazard": "Temporary cables laid on wet ground", "severity": "Low",
         "standard_reference": "OSHA 1926.405",
         "remedy": "Elevate cables, use RCCB-protected distribution boards."},
    ],
}

DEMO_CRACK = {
    "defect_type": "Structural Shear",
    "confidence": 72,
    "estimated_crack_width_mm": 1.8,
    "crack_pattern": "Diagonal (approx. 45°) near the beam-column joint",
    "structural_risk": "High",
    "urgency": "Priority (within 2 weeks)",
    "root_causes": [
        "Inadequate shear reinforcement / stirrup spacing at the support",
        "Overloading or unexpected differential loading on the member",
        "Possible differential settlement of the adjacent footing",
    ],
    "recommended_repairs": [
        {"method": "Epoxy injection", "detail": "Low-viscosity structural epoxy under pressure after sealing the surface and installing ports at ~150 mm c/c.",
         "applies_when": "Crack is dormant and width is 0.2 to 3 mm."},
        {"method": "Structural re-grouting / jacketing", "detail": "Non-shrink cementitious grout with supplementary stirrups, or FRP wrap for shear strengthening.",
         "applies_when": "Shear capacity loss is confirmed by structural analysis."},
    ],
    "monitoring_plan": "Fix tell-tale gauges and record width weekly for 8 weeks; conduct rebound hammer and UPV tests.",
    "engineer_note": "DEMO DATA. Photo-based assessment cannot replace on-site structural evaluation by a licensed engineer.",
}

DEMO_CHAT_RULES = [
    (("curing", "cure"), "Curing: keep concrete continuously moist for at least 7 days (10 days for PPC/blended cement or hot/windy weather), starting right after final set. Use wet burlap, ponding or curing compound. Per IS 456 cl. 13.5."),
    (("slump", "workability"), "Typical slump ranges (IS 456 cl. 7.1): ~25-75 mm for beams and slabs in lightly reinforced sections, 50-100 mm for normal RCC, 75-100+ mm for columns/heavily reinforced sections, with admixtures for higher workability."),
    (("cover", "clear cover"), "Nominal cover (IS 456 cl. 26.4, Table 16): for mild exposure about 20 mm for slabs/beams/columns (40 mm for columns is the usual minimum in practice) and 50 mm for footings; increase for moderate to extreme exposure. Confirm against the structural drawings."),
    (("crane", "lifting"), "Lifting safety: verify load chart and rated capacity, inspect slings and shackles, set exclusion zone, appoint a signaller, and suspend lifts in high wind (typically above ~36 km/h)."),
    (("scaffold",), "Scaffolds: competent-person inspection before use, base plates and sole boards, ties at specified spacing, full decking, guardrails and toe boards, and a visible inspection tag."),
    (("crack",), "For cracks: record width and pattern first. Hairline (<0.3 mm) often cosmetic; wider or diagonal cracks near supports need engineer review. Use crack gauges and monitor before repair."),
    (("steel", "rebar"), "Rebar: use Fe500/Fe500D per IS 1786, check lap lengths (typically 40-50 d), keep cover blocks in place, and ensure bars are free of loose rust and oil."),
    (("ppe", "helmet", "harness"), "PPE baseline: helmet, high-vis vest, safety boots, gloves and eye protection; add full-body harness above 1.8 m (OSHA 6 ft) with anchor points rated for fall arrest."),
]

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def format_inr(amount: float) -> str:
    """Format a rupee amount in Lakhs / Crores."""
    if amount >= 1e7:
        return f"₹{amount / 1e7:,.2f} Cr"
    if amount >= 1e5:
        return f"₹{amount / 1e5:,.2f} Lakhs"
    return f"₹{amount:,.0f}"


def metric_card(label: str, value: str, sub: str = "", color: str | None = None) -> str:
    style = f' style="border-left-color:{color}"' if color else ""
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="metric-card"{style}><div class="label">{label}</div>'
            f'<div class="value">{value}</div>{sub_html}</div>')


def pill(text: str, kind: str) -> str:
    return f'<span class="pill {kind}">{text}</span>'


def severity_kind(sev: str) -> str:
    return {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}.get(str(sev).lower(), "neutral")


def score_color(score: int) -> str:
    return "#16a34a" if score >= 80 else "#d97706" if score >= 55 else "#dc2626"


def prepare_image(uploaded) -> Image.Image:
    img = Image.open(uploaded)
    img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return img


def get_api_key_from_secrets() -> str:
    try:
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        return ""


def demo_mode() -> bool:
    return not (st.session_state.get("api_key") and GENAI_AVAILABLE)


@st.cache_resource(show_spinner=False)
def get_client(api_key: str):
    return genai.Client(api_key=api_key)


def extract_json(text: str) -> dict:
    """Robustly parse JSON from a model response (handles ```json fences)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def analyze_image(prompt: str, image: Image.Image, demo_payload: dict) -> tuple[dict, bool]:
    """Returns (result, used_demo). Falls back to demo on any failure."""
    if demo_mode():
        return demo_payload, True
    try:
        client = get_client(st.session_state["api_key"])
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        response = client.models.generate_content(
            model=st.session_state.get("model", DEFAULT_MODEL),
            contents=[
                types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.2
            ),
        )
        return extract_json(response.text), False
    except Exception as exc:  # network, quota, auth, parse
        st.warning(f"Gemini request failed ({type(exc).__name__}: {str(exc)[:180]}). Showing demonstration output instead.")
        return demo_payload, True


def chat_reply(history: list[dict], weather: str) -> str:
    last = history[-1]["content"]
    if demo_mode():
        low = last.lower()
        for keys, answer in DEMO_CHAT_RULES:
            if any(k in low for k in keys):
                return answer + "\n\n*(Demo mode: add a Gemini API key for full conversational answers.)*"
        return ("I'm running in demonstration mode with a small built-in knowledge base. "
                "Try asking about curing, slump, cover, cranes, scaffolds, cracks, rebar or PPE. "
                "Add a Gemini API key in the sidebar for open-ended engineering help.")
    try:
        client = get_client(st.session_state["api_key"])
        transcript = "\n".join(
            f"{'Engineer' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history[-12:]
        )
        prompt = f"Current site weather condition: {weather}.\n\nConversation so far:\n{transcript}\n\nAssistant:"
        response = client.models.generate_content(
            model=st.session_state.get("model", DEFAULT_MODEL),
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=ASSISTANT_SYSTEM, temperature=0.4),
        )
        return response.text or "I couldn't generate a response. Please rephrase."
    except Exception as exc:
        return f"⚠️ The Gemini request failed ({type(exc).__name__}). Please check your key and quota, then retry."


def json_download(label: str, data: dict, filename: str, key: str):
    st.download_button(
        label, data=json.dumps(data, indent=2, ensure_ascii=False),
        file_name=filename, mime="application/json", key=key, use_container_width=True,
    )


# ----------------------------------------------------------------------------
# Result renderers
# ----------------------------------------------------------------------------
def render_safety(result: dict, used_demo: bool):
    score = int(result.get("safety_score", 0) or 0)
    score = max(0, min(100, score))
    status = str(result.get("overall_status", "Unknown"))
    hazards = result.get("hazards", []) or []
    ppe = result.get("ppe_detection", {}) or {}
    status_kind = {"compliant": "ok", "needs improvement": "medium",
                   "non-compliant": "high", "critical risk": "critical"}.get(status.lower(), "neutral")
    critical_n = sum(1 for h in hazards if str(h.get("severity", "")).lower() in ("high", "critical"))

    if used_demo:
        st.info("Demonstration output: add a Gemini API key in the sidebar for real image analysis.")

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(metric_card("Safety Score", f"{score}/100", "Higher is safer", score_color(score)), unsafe_allow_html=True)
    c2.markdown(metric_card("Overall Status", pill(status, status_kind)), unsafe_allow_html=True)
    c3.markdown(metric_card("Workers Detected", str(result.get("workers_detected", "n/a"))), unsafe_allow_html=True)
    c4.markdown(metric_card("High / Critical Hazards", str(critical_n), f"of {len(hazards)} identified",
                            "#dc2626" if critical_n else "#16a34a"), unsafe_allow_html=True)
    st.progress(score / 100)
    if result.get("summary"):
        st.write(result["summary"])

    st.subheader("PPE Compliance Checklist")
    labels = {"helmet": "⛑️ Helmet", "high_vis_vest": "🦺 High-Vis Vest",
              "steel_toe_boots": "🥾 Steel-Toe Boots", "safety_harness": "🪢 Safety Harness"}
    cols = st.columns(4)
    for col, (key, label) in zip(cols, labels.items()):
        item = ppe.get(key, {}) or {}
        ok = bool(item.get("detected", False))
        col.markdown(
            f'<div class="metric-card" style="border-left-color:{"#16a34a" if ok else "#dc2626"}">'
            f'<div class="label">{label}</div>'
            f'<div style="margin:.3rem 0">{pill("Detected" if ok else "Not detected", "ok" if ok else "high")}</div>'
            f'<div class="sub">{item.get("note", "")}</div></div>', unsafe_allow_html=True)

    st.subheader("Identified Hazards & Corrective Actions")
    if not hazards:
        st.success("No hazards identified in this image.")
    for h in sorted(hazards, key=lambda x: SEVERITY_ORDER.index(x["severity"]) if x.get("severity") in SEVERITY_ORDER else 0, reverse=True):
        sev = h.get("severity", "Low")
        st.markdown(
            f'<div class="hazard">{pill(sev, severity_kind(sev))} &nbsp;<b>{h.get("hazard", "Hazard")}</b>'
            f'<div class="sub" style="color:#64748b;font-size:.82rem;margin:.3rem 0">Ref: {h.get("standard_reference", "n/a")}</div>'
            f'<div>🔧 <b>Remedy:</b> {h.get("remedy", "n/a")}</div></div>', unsafe_allow_html=True)

    report = {"report_type": "site_safety_ppe_audit", "generated_at": datetime.now().isoformat(timespec="seconds"),
              "demo_mode": used_demo, **result}
    json_download("⬇️ Download JSON Safety Report", report,
                  f"safety_report_{datetime.now():%Y%m%d_%H%M%S}.json", "dl_safety")


def render_crack(result: dict, used_demo: bool):
    if used_demo:
        st.info("Demonstration output: add a Gemini API key in the sidebar for real image analysis.")
    risk = str(result.get("structural_risk", "Unknown"))
    risk_kind = {"low": "ok", "moderate": "medium", "high": "high", "severe": "critical"}.get(risk.lower(), "neutral")
    width = result.get("estimated_crack_width_mm", "n/a")

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(metric_card("Defect Type", str(result.get("defect_type", "n/a")),
                            f"Confidence {result.get('confidence', 'n/a')}%"), unsafe_allow_html=True)
    c2.markdown(metric_card("Est. Crack Width", f"{width} mm", str(result.get("crack_pattern", ""))), unsafe_allow_html=True)
    c3.markdown(metric_card("Structural Risk", pill(risk, risk_kind)), unsafe_allow_html=True)
    c4.markdown(metric_card("Urgency", str(result.get("urgency", "n/a"))), unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Probable Root Causes")
        for cause in result.get("root_causes", []) or []:
            st.markdown(f"- {cause}")
    with right:
        st.subheader("Monitoring Plan")
        st.write(result.get("monitoring_plan", "n/a"))

    st.subheader("Recommended Engineering Repairs")
    for r in result.get("recommended_repairs", []) or []:
        st.markdown(
            f'<div class="hazard"><b>🛠️ {r.get("method", "Repair")}</b><br>{r.get("detail", "")}'
            f'<div style="color:#64748b;font-size:.82rem;margin-top:.3rem">Applies when: {r.get("applies_when", "n/a")}</div></div>',
            unsafe_allow_html=True)
    if result.get("engineer_note"):
        st.caption(f"⚠️ {result['engineer_note']}")

    report = {"report_type": "crack_diagnostics", "generated_at": datetime.now().isoformat(timespec="seconds"),
              "demo_mode": used_demo, **result}
    json_download("⬇️ Download JSON Diagnostic Report", report,
                  f"crack_report_{datetime.now():%Y%m%d_%H%M%S}.json", "dl_crack")


# ----------------------------------------------------------------------------
# Valuation engine
# ----------------------------------------------------------------------------
def compute_valuation(structure: str, sqft: float, tier: str, completion: int) -> dict:
    base, tf = STRUCTURE_TYPES[structure], TIER_FACTORS[tier]
    frac = completion / 100
    budget = sqft * base["cost"] * tf["cost"]
    capex = budget * frac
    full_value = sqft * base["market"] * tf["market"]
    # Under-construction assets are discounted for completion risk (10%) until handover.
    current_value = full_value * frac * (1.0 if completion >= 100 else 0.9)
    return {
        "budget": budget, "capex": capex, "remaining": budget - capex,
        "full_market_value": full_value, "current_value": current_value,
        "steel_total_t": sqft * base["steel"] / 1000,
        "steel_used_t": sqft * base["steel"] / 1000 * frac,
        "cement_total_bags": sqft * base["cement"],
        "cement_used_bags": sqft * base["cement"] * frac,
        "roi_pct": ((full_value - budget) / budget * 100) if budget else 0,
    }


def build_render_prompt(structure: str, sqft: float, tier: str, completion: int, style: str) -> str:
    stage = "architectural 3D render of the completed building" if completion >= 95 else \
            f"architectural 3D render of the building at {completion}% construction stage with scaffolding and cranes"
    city = tier.split("(")[0].strip()
    return (f"{stage}, {structure.split('(')[0].strip()}, approx {int(sqft)} sq ft, Indian {city} city context, "
            f"{style} style, photorealistic, golden hour lighting, wide angle, high detail")


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("## 🏗️ Control Panel")
        default_key = get_api_key_from_secrets()
        key = st.text_input("Google Gemini API Key", type="password", value=default_key,
                            placeholder="AIza...", help="Kept in session memory only. Never stored or logged.")
        st.session_state["api_key"] = key.strip()
        st.session_state["model"] = st.selectbox(
            "Gemini model", [DEFAULT_MODEL, "gemini-2.5-pro", "gemini-2.0-flash"], index=0)

        if st.session_state["api_key"] and GENAI_AVAILABLE:
            st.success("Live mode: Gemini connected")
        elif st.session_state["api_key"] and not GENAI_AVAILABLE:
            st.error("`google-genai` is not installed. Running in demo mode.")
        else:
            st.warning("Demonstration mode: sample outputs only. Get a free key at aistudio.google.com")

        st.divider()
        st.markdown("### 🧭 Modules")
        st.markdown(
            "- 🦺 **Safety & PPE Audit** (Epic 2)\n- 🧱 **Crack Diagnostics** (Epic 2)\n"
            "- 💰 **Planning & Valuation** (Epic 3)\n- 🌦️ **Site Assistant** (Epic 5)")

        with st.expander("🏛️ Architecture overview"):
            st.markdown(
                "```\nStreamlit UI (tabs)\n   │\n   ├─ Image modules ──► Pillow ► Gemini Vision (JSON mode)\n"
                "   │                       └─► schema normaliser ► metric cards / JSON export\n"
                "   ├─ Valuation engine ─► pure-Python cost model ► Pollinations render URL\n"
                "   └─ Assistant ───────► Gemini chat (weather-aware system context)\n"
                "\nState: st.session_state only\nDB: none\n```")
        st.caption("Standards referenced: OSHA 29 CFR 1926, IS 456:2000, NBC 2016. AI output is advisory and must be verified by a licensed engineer.")


# ----------------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------------
def tab_safety():
    st.markdown("Upload a site photo to audit worker PPE and identify hazards against OSHA and IS standards.")
    up = st.file_uploader("Construction site photo", type=["jpg", "jpeg", "png"], key="safety_up")
    if not up:
        return
    try:
        img = prepare_image(up)
    except Exception:
        st.error("Could not read that image. Please upload a valid JPG or PNG.")
        return
    col_img, col_btn = st.columns([2, 1])
    col_img.image(img, caption="Uploaded site photo", use_container_width=True)
    with col_btn:
        run = st.button("🔍 Run Safety Audit", type="primary", use_container_width=True, key="run_safety")
    if run:
        with st.spinner("Analysing PPE compliance and site hazards..."):
            st.session_state["safety_result"] = analyze_image(SAFETY_PROMPT, img, DEMO_SAFETY)
    if "safety_result" in st.session_state:
        st.divider()
        render_safety(*st.session_state["safety_result"])


def tab_crack():
    st.markdown("Upload a photo of a concrete or wall surface for defect classification and repair guidance.")
    up = st.file_uploader("Concrete / wall surface photo", type=["jpg", "jpeg", "png"], key="crack_up")
    if not up:
        return
    try:
        img = prepare_image(up)
    except Exception:
        st.error("Could not read that image. Please upload a valid JPG or PNG.")
        return
    col_img, col_btn = st.columns([2, 1])
    col_img.image(img, caption="Uploaded surface photo", use_container_width=True)
    with col_btn:
        st.caption("Tip: include a coin or ruler for scale to improve width estimates.")
        run = st.button("🧪 Diagnose Defect", type="primary", use_container_width=True, key="run_crack")
    if run:
        with st.spinner("Classifying defect and estimating crack width..."):
            st.session_state["crack_result"] = analyze_image(CRACK_PROMPT, img, DEMO_CRACK)
    if "crack_result" in st.session_state:
        st.divider()
        render_crack(*st.session_state["crack_result"])


def tab_planning():
    st.markdown("Estimate project budget, capital deployed, current asset value and material requirements.")
    c1, c2 = st.columns(2)
    structure = c1.selectbox("Structure type", list(STRUCTURE_TYPES), key="p_struct")
    tier = c2.selectbox("Location tier", list(TIER_FACTORS), index=1, key="p_tier")
    c3, c4 = st.columns([1, 2])
    sqft = c3.number_input("Built-up area (sq ft)", min_value=100, max_value=1_000_000, value=2500, step=100, key="p_sqft")
    completion = c4.slider("Completion (%)", 0, 100, 40, key="p_comp")

    v = compute_valuation(structure, float(sqft), tier, completion)

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(metric_card("Total Project Budget", format_inr(v["budget"]), "Estimated construction cost"), unsafe_allow_html=True)
    m2.markdown(metric_card("CapEx Incurred", format_inr(v["capex"]), f"Remaining {format_inr(v['remaining'])}", "#0891b2"), unsafe_allow_html=True)
    m3.markdown(metric_card("Current Asset Valuation", format_inr(v["current_value"]), "Market basis, risk-adjusted", "#16a34a"), unsafe_allow_html=True)
    m4.markdown(metric_card("Value on Completion", format_inr(v["full_market_value"]), f"Indicative margin {v['roi_pct']:.0f}%", "#7c3aed"), unsafe_allow_html=True)

    st.subheader("Material Requirements")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Steel (total)", f"{v['steel_total_t']:.1f} tonnes")
    s2.metric("Steel consumed", f"{v['steel_used_t']:.1f} t", f"{completion}% of plan")
    s3.metric("Cement (total)", f"{v['cement_total_bags']:,.0f} bags", "50 kg bags")
    s4.metric("Cement consumed", f"{v['cement_used_bags']:,.0f} bags", f"{completion}% of plan")

    st.subheader("Milestone Progress")
    st.progress(completion / 100, text=f"Overall completion: {completion}%")
    prev = 0
    for name, upper in MILESTONES:
        span = upper - prev
        done = max(0.0, min(1.0, (completion - prev) / span))
        icon = "✅" if done >= 1 else "🔨" if done > 0 else "⏳"
        st.progress(done, text=f"{icon} {name} ({prev}-{upper}%)")
        prev = upper
    st.caption("Estimates use indicative benchmark rates and are not a registered valuation. Obtain a certified valuer's report for lending or sale.")

    st.subheader("🎨 Conceptual 3D Architectural Rendering")
    style = st.selectbox("Architectural style", ["Modern minimalist", "Contemporary Indian", "Neo-classical", "Sustainable green building", "Industrial"], key="p_style")
    prompt = st.text_area("Render prompt (editable)", build_render_prompt(structure, sqft, tier, completion, style), height=100, key="p_prompt")
    if st.button("Generate Concept Render", type="primary", key="gen_render"):
        seed = zlib.crc32(prompt.encode()) % 100000
        url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
               f"?width=1024&height=640&nologo=true&seed={seed}")
        st.session_state["render_url"] = url
    if st.session_state.get("render_url"):
        st.image(st.session_state["render_url"], caption="AI concept render via Pollinations (illustrative only)", use_container_width=True)
        st.caption("If the image does not load, the free Pollinations service may be busy. Try again in a moment.")


def tab_assistant():
    st.markdown("Select today's weather to see dynamic safety protocols, then ask the engineering assistant.")
    weather = st.radio("Site weather condition", list(WEATHER_ADVISORIES), horizontal=True, key="weather")
    adv = WEATHER_ADVISORIES[weather]
    st.markdown(f'<div class="alert-box alert-{adv["level"]}"><b>{adv["icon"]} {adv["headline"]}</b></div>', unsafe_allow_html=True)
    for a in adv["alerts"]:
        st.markdown(f"- {a}")
    with st.expander("✅ Daily checklist"):
        for item in adv["checklist"]:
            st.checkbox(item, key=f"chk_{weather}_{item}")

    st.divider()
    st.subheader("💬 Construction Engineering Assistant")
    if "chat" not in st.session_state:
        st.session_state["chat"] = [{"role": "assistant", "content":
            "Hello! I'm your site engineering assistant. Ask about concrete, rebar, scaffolds, lifting, crack repair, IS codes or today's weather precautions."}]
    for m in st.session_state["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if st.button("🗑️ Clear chat", key="clear_chat"):
        st.session_state.pop("chat")
        st.rerun()

    prompt = st.chat_input("Ask a construction question...")
    if prompt:
        st.session_state["chat"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = chat_reply(st.session_state["chat"], weather)
            st.markdown(reply)
        st.session_state["chat"].append({"role": "assistant", "content": reply})


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    render_sidebar()
    st.markdown(
        '<div class="hero"><h1>🏗️ Multimodal Construction Intelligence Platform</h1>'
        '<p>AI-powered site safety, structural diagnostics, project valuation and field assistance · Skill Wallet Capstone Project 1</p></div>',
        unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["🦺 Site Safety & PPE Audit", "🧱 Crack Diagnostics",
                              "💰 Planning & Valuation", "🌦️ Daily Site Assistant"])
    with t1:
        tab_safety()
    with t2:
        tab_crack()
    with t3:
        tab_planning()
    with t4:
        tab_assistant()
    st.markdown('<div class="footer">AI output is advisory. Safety-critical and structural decisions must be verified by qualified professionals.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
