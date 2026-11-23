"""Nonprofit Grant-Matcher & Summarizer Bot (v1).

Streamlit app that compares an organization profile against grant guidelines,
returns a fit/eligibility assessment, and drafts a 7-part application outline.
"""

import json

import anthropic
import streamlit as st
from pypdf import PdfReader

MODEL = "claude-opus-5-5"
MAX_GUIDELINE_CHARS = 25_000
LARGE_PDF_PAGES = 15
PLACEHOLDER = "[TO FILL IN — verify local data/numbers]"

SECTION_TITLES = [
    "1. Executive Summary & Mission Fit",
    "2. Statement of Need",
    "3. Project / Program Description & Activities",
    "4. Goals, Objectives & Outcomes",
    "5. Organizational Capacity & Readiness",
    "6. Budget & Sustainability Snapshot",
    "7. Required Attachments & Compliance Checklist",
]
SECTION_KEYS = [f"section_{i}" for i in range(1, 8)]

# ---------------------------------------------------------------------------
# Sample preset
# ---------------------------------------------------------------------------
SAMPLE = {
    "org_name": "Riverside Community Food Pantry",
    "org_mission": (
        "Mission: Reduce food insecurity for families in the Riverside and East Hollow "
        "neighborhoods.\n"
        "Core programs: weekly client-choice pantry (Tue/Sat), a weekend backpack program "
        "for elementary students, and monthly mobile distributions to two senior housing sites.\n"
        "Target population: low-income households, seniors on fixed incomes, and families "
        "with school-age children."
    ),
    "org_capacity": (
        "Team: 2 part-time staff (executive director, volunteer coordinator) and ~60 active "
        "volunteers.\n"
        "Service area: Riverside County (urban core + two rural townships).\n"
        "Status: 501(c)(3), founded 2014, annual operating budget roughly $280,000.\n"
        "Constraints: limited cold storage (one walk-in cooler); no dedicated grant writer; "
        "seeking $25,000–$50,000 to add refrigerated capacity and expand fresh produce."
    ),
    "guidelines": (
        "HARVEST HOPE FOUNDATION — 2026 Community Nutrition Access Grant\n\n"
        "Purpose: Support nonprofits that increase access to fresh, healthy food for "
        "food-insecure residents.\n"
        "Eligibility: 501(c)(3) organizations operating at least 3 years and serving "
        "residents of Riverside, Clark, or Monroe counties. Organizations with annual "
        "budgets over $2 million are not eligible.\n"
        "Award range: $10,000–$40,000 for a 12-month grant period.\n"
        "Match: A 25% cash or in-kind match is required.\n"
        "Priorities: fresh produce distribution, cold-chain/storage improvements, "
        "partnerships with local farms, and programs reaching seniors or children.\n"
        "Deadline: Applications due March 14, 2026 at 5:00 PM via the online portal. "
        "Awards announced May 2026.\n"
        "Reporting: Interim report at 6 months; final narrative and financial report "
        "within 30 days of grant end.\n"
        "Required attachments: IRS determination letter, current board list, most recent "
        "audited financials or Form 990, project budget with match detail, and one letter "
        "of support from a community partner."
    ),
}


def load_sample() -> None:
    """Populate widget state with the sample pantry + grant (on_click callback)."""
    for key, value in SAMPLE.items():
        st.session_state[key] = value
    st.session_state.pop("result", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_api_key() -> str:
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:  # no secrets.toml present
        key = ""
    if key:
        st.sidebar.success("API key loaded from secrets.")
        return key
    return st.sidebar.text_input("Anthropic API Key", type="password")


def extract_pdf_text(uploaded_file) -> tuple[str, int]:
    """Return (text, page_count) for an uploaded PDF."""
    reader = PdfReader(uploaded_file)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip(), len(reader.pages)


def build_schema() -> dict:
    section = {
        "type": "object",
        "properties": {
            "what_to_cover": {"type": "string"},
            "draft_starter_points": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["what_to_cover", "draft_starter_points"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "fit_rating": {"type": "string", "enum": ["High Fit", "Moderate Fit", "Low Fit"]},
            "fit_rationale": {"type": "string"},
            "eligibility_flags": {"type": "array", "items": {"type": "string"}},
            "key_dates_requirements": {"type": "array", "items": {"type": "string"}},
            "outline": {
                "type": "object",
                "properties": {k: section for k in SECTION_KEYS},
                "required": SECTION_KEYS,
                "additionalProperties": False,
            },
        },
        "required": [
            "fit_rating",
            "fit_rationale",
            "eligibility_flags",
            "key_dates_requirements",
            "outline",
        ],
        "additionalProperties": False,
    }


SYSTEM_PROMPT = f"""You are an experienced nonprofit grant strategist. You assess how well an \
organization fits a grant opportunity and draft a practical application outline.

Rules:
- Base every statement only on the organization profile and grant guidelines provided.
- Do NOT invent local statistics, exact grant dollar figures, dates, deadlines, budgets, or \
other financial numbers that are not present in the inputs. Wherever specific local data or \
numbers must be supplied by the applicant, write exactly "{PLACEHOLDER}".
- If the guidelines omit something important (deadline, award range, eligibility, match, \
reporting, attachments), say so in the eligibility flags rather than guessing.
- fit_rating must be "High Fit", "Moderate Fit", or "Low Fit".
- fit_rationale: 2-3 concise sentences on alignment.
- eligibility_flags: short bullets on eligibility mismatches, geographic or award-size \
constraints, capacity concerns, and missing information.
- key_dates_requirements: short bullets on deadlines, award range, match rules, reporting \
rules, and required attachments that appear in the guidelines.
- outline: section_1..section_7 correspond, in order, to:
{chr(10).join(SECTION_TITLES)}
  For each, give a 1-2 sentence what_to_cover and 3-5 actionable draft_starter_points \
(bullets or questions the applicant should answer), tailored to this organization and grant."""


def call_claude(api_key: str, org: dict, guidelines: str) -> dict:
    """Request a structured assessment from Claude and return the parsed dict."""
    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        "<organization_profile>\n"
        f"Organization Name: {org['name']}\n\n"
        f"Mission / Core Programs / Target Population:\n{org['mission']}\n\n"
        f"Capacity / Geography / Funding Constraints:\n{org['capacity']}\n"
        "</organization_profile>\n\n"
        f"<grant_guidelines>\n{guidelines}\n</grant_guidelines>\n\n"
        "Assess fit and eligibility, then produce the 7-part application outline."
    )
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": build_schema()},
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise ValueError("The model declined this request. Please review your inputs and try again.")
    if response.stop_reason == "max_tokens":
        raise ValueError("The response was cut off before completion. Try shortening the guidelines.")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    data = json.loads(text)
    if not isinstance(data, dict) or not all(k in data.get("outline", {}) for k in SECTION_KEYS):
        raise ValueError("The response was missing expected fields.")
    return data


def to_markdown(org_name: str, data: dict) -> str:
    lines = [f"# Grant Fit Assessment & Application Outline — {org_name or 'Organization'}", ""]
    lines += ["## Fit Assessment", f"**Fit Rating:** {data['fit_rating']}", "", data["fit_rationale"], ""]
    lines += ["## Eligibility Flags & Missing Info"]
    lines += [f"- {f}" for f in data["eligibility_flags"]] or ["- None identified"]
    lines += ["", "## Key Dates & Requirements"]
    lines += [f"- {r}" for r in data["key_dates_requirements"]] or ["- None found in guidelines"]
    lines += ["", "## Application Outline", ""]
    for key, title in zip(SECTION_KEYS, SECTION_TITLES):
        sec = data["outline"][key]
        lines += [f"### {title}", f"**What to cover:** {sec['what_to_cover']}", "", "**Draft starter points:**"]
        lines += [f"- {p}" for p in sec["draft_starter_points"]]
        lines.append("")
    return "\n".join(lines)


def render_result(org_name: str, data: dict) -> None:
    st.header("Fit & Eligibility Gatekeeper")
    rating = data["fit_rating"]
    badge = {"High Fit": st.success, "Moderate Fit": st.warning, "Low Fit": st.error}.get(rating, st.info)
    badge(f"**Fit Rating:** {rating}")
    st.markdown(f"**Fit Rationale:** {data['fit_rationale']}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Eligibility Flags & Missing Info")
        st.markdown("\n".join(f"- {f}" for f in data["eligibility_flags"]) or "_None identified._")
    with col2:
        st.subheader("Key Dates & Requirements")
        st.markdown("\n".join(f"- {r}" for r in data["key_dates_requirements"]) or "_None found._")

    st.header("7-Part Application Outline")
    for key, title in zip(SECTION_KEYS, SECTION_TITLES):
        sec = data["outline"][key]
        st.subheader(title)
        st.markdown(f"**What to cover:** {sec['what_to_cover']}")
        st.markdown("\n".join(f"- {p}" for p in sec["draft_starter_points"]))

    md = to_markdown(org_name, data)
    st.divider()
    st.download_button("Download Outline (.md)", md, file_name="grant_outline.md", mime="text/markdown")
    with st.expander("Raw Markdown (copy)"):
        st.code(md, language="markdown")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Grant-Matcher & Summarizer", page_icon="📝", layout="wide")
    st.title("📝 Nonprofit Grant-Matcher & Summarizer")
    st.caption("Check fit against a grant's guidelines and get a structured application outline.")

    api_key = get_api_key()
    st.sidebar.caption("Your key is used only for this session and never stored.")

    st.button("Load Sample Pantry + Grant", on_click=load_sample)

    st.header("Organization Profile")
    org_name = st.text_input("Organization Name", key="org_name")
    org_mission = st.text_area("Mission / Core Programs / Target Population", key="org_mission", height=150)
    org_capacity = st.text_area(
        "Capacity / Geography / Funding Constraints",
        key="org_capacity",
        height=150,
        help="e.g., team size, volunteer base, service area, award range or budget constraints",
    )

    st.header("Grant Guidelines")
    pasted = st.text_area("Paste grant guidelines", key="guidelines", height=220)
    pdf = st.file_uploader("…and/or upload guidelines PDF", type=["pdf"])

    pdf_text = ""
    if pdf is not None:
        try:
            pdf_text, n_pages = extract_pdf_text(pdf)
            if n_pages > LARGE_PDF_PAGES or len(pdf_text) > MAX_GUIDELINE_CHARS:
                st.warning(
                    f"Large PDF detected ({n_pages} pages, {len(pdf_text):,} characters). "
                    f"Guidelines will be capped at {MAX_GUIDELINE_CHARS:,} characters to control "
                    "token usage — consider pasting only the relevant sections."
                )
            if not pdf_text:
                st.warning("No extractable text found in this PDF (it may be scanned). Please paste the text instead.")
        except Exception as exc:
            st.error(f"Could not read the PDF: {exc}")

    combined = "\n\n".join(t for t in (pasted.strip(), pdf_text) if t)
    if len(combined) > MAX_GUIDELINE_CHARS:
        st.info(
            f"Combined guidelines are {len(combined):,} characters; only the first "
            f"{MAX_GUIDELINE_CHARS:,} will be sent to the model."
        )
        combined = combined[:MAX_GUIDELINE_CHARS]

    if st.button("Analyze Fit & Generate Outline", type="primary"):
        if not api_key:
            st.error("Please provide an Anthropic API key in the sidebar.")
        elif not (org_name.strip() and org_mission.strip()):
            st.error("Please enter at least the Organization Name and Mission.")
        elif not combined:
            st.error("Please paste grant guidelines or upload a PDF.")
        else:
            org = {"name": org_name, "mission": org_mission, "capacity": org_capacity or "Not provided."}
            try:
                with st.spinner("Analyzing fit and drafting outline…"):
                    st.session_state["result"] = (org_name, call_claude(api_key, org, combined))
            except anthropic.AuthenticationError:
                st.error("Authentication failed — please check your Anthropic API key.")
            except anthropic.RateLimitError:
                st.error("Rate limit reached. Please wait a moment and try again.")
            except anthropic.APIConnectionError:
                st.error("Could not reach the Anthropic API. Check your internet connection.")
            except anthropic.APIStatusError as exc:
                st.error(f"The Anthropic API returned an error ({exc.status_code}). Please try again.")
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                st.error(f"Could not parse the model's response: {exc}")

    if "result" in st.session_state:
        render_result(*st.session_state["result"])


if __name__ == "__main__":
    main()
