"""LLM prompt builders.

Each function assembles one prompt string from its inputs.
No LLM calls happen here — pure string construction only.
"""

import json

from agentic.memory import _load_human_answers


def build_profile_prompt(pdf_text: str) -> str:
    """Prompt that asks the LLM to parse a resume PDF into structured JSON."""
    return f"""
    You are an ATS resume parser.

    Convert the resume into structured JSON.
    Return only raw json do not wrap in markdown

    Resume - {pdf_text}
    """


def build_match_prompt(candidate_profile: dict, raw_job_desc: dict) -> str:
    """Prompt that asks the LLM to score a candidate against a job description."""
    return f"""
    You are an expert ATS and technical recruiter.

    Your task is to analyze how well a candidate matches a job description.

    You will be given:

    1. Candidate profile JSON
    2. Job description text

    You must:
    - evaluate technical skill alignment
    - evaluate experience alignment
    - evaluate domain alignment
    - evaluate seniority alignment
    - identify strengths
    - identify gaps
    - generate realistic match score

    IMPORTANT:
    - Be strict and realistic.
    - Do NOT inflate scores.
    - Missing critical skills should reduce score significantly.
    - Consider transferable skills where appropriate.
    - Return ONLY valid raw JSON.
    - Do NOT wrap response in markdown.

    Candidate Profile:
    {candidate_profile}

    Job Description:
    {raw_job_desc}


    Return JSON in this exact schema:
    class MatchReason(TypedDict):
        strong_matches: List[str]
        missing_or_weaker_areas: List[str]

    class CompanyInsights(TypedDict):
        total_employees: int
        median_employee_tenure: str
        focus_areas: List[str]


    class JobDescription(TypedDict):
        summary: str
        skills_required: List[str]
        responsibilities: List[str]
        company_insights: CompanyInsights

    slug: str
    title: str
    company: str
    location: str
    work_mode: str
    easy_apply: bool
    required_experience_years: int
    job_url: str
    match_score: float
    match_reason: MatchReason
    description: JobDescription

    Scoring Guidelines:
    - 9-10 = Excellent fit
    - 7-8 = Strong fit
    - 5-6 = Partial fit
    - 3-4 = Weak fit
    - 0-2 = Poor fit

    Important:
    - Prioritize actual experience over keyword overlap.
    - Backend experience should partially transfer across stacks.
    - React Native experience partially transfers to React roles.
    - System design and scalability experience are valuable.
    - AI tooling familiarity is a bonus but not core backend expertise unless explicitly required.
    """


def build_fill_form_prompt(state: dict) -> str:
    """Prompt that asks the LLM to fill LinkedIn Easy Apply form fields."""
    return f"""
    You are an AI assistant helping fill LinkedIn Easy Apply forms.
    Your task:
    - Analyze the candidate profile carefully
    - Update ONLY:
    - "value"
    - "checked"
    - "shouldChecked"
    - Keep ALL other fields unchanged
    - Preserve the exact JSON structure
    - Do not remove fields
    - Do not rename keys
    - Do not add new keys
    - Choose answers conservatively and realistically
    - Never exaggerate experience
    - For select/radio fields, choose ONLY from the provided options
    - Return valid JSON only
    - Do NOT wrap response in markdown
    - Do NOT include explanations
    - Do NOT include extra text before or after JSON

    Rules:
    - For radio options:
    - ONLY ONE option should have:
        "shouldChecked": true
    - All others must be:
        "shouldChecked": false

    - For checkbox fields:
    - Set:
        "checked": true/false

    - For select/text/combobox fields:
    - Update ONLY:
        "value"

    - For combobox fields:
    - Update ONLY:
        "value"
    - The browser will type this value and select the first suggestion using keyboard.
    - For Location (city) combobox fields, use Mumbai unless HUMAN ANSWERS provide a different city.

    - If there are required questions where the answer cannot be inferred from:
    - candidate profile
    - personal details
    - provided context
    - human answers
    then:
    - ask the user for clarification
    - clearly mention which field/question needs input
    - wait for user response before continuing
    - do NOT guess unknown required answers

    IMP - If a required form field cannot be answered,
    call the request_missing_required_information tool instead of guessing.
    Human answers are final and authoritative.
    Never ask again for fields already present in HUMAN ANSWERS.
    If a field exists in HUMAN ANSWERS, use it directly even if confidence is low.
    Only call request_missing_required_information as a LAST RESORT.

    Before calling request_missing_required_information:
    1. Check PERSONAL DETAILS
    2. Check NAME DETAILS
    3. Check LOCATION DETAILS
    4. Check PROFESSIONAL DETAILS
    5. Check HUMAN ANSWERS
    6. Infer obvious mappings conservatively

    Do NOT call request_missing_required_information for:
    - Gender
    - Race/Ethnicity
    - Veteran status
    - Disability
    - Name
    - City
    - State
    - Postal code
    - LinkedIn profile
    - Phone number
    - Email

    These values are already confirmed and authoritative.

    Only call request_missing_required_information if:
    1. field is required
    2. answer does not exist anywhere in:
    - personal details
    - candidate profile
    - HUMAN ANSWERS
    3. no deterministic mapping can be inferred

    --------------------------------------------------
    PERSONAL DETAILS
    --------------------------------------------------

    Use CANDIDATE PROFILE and HUMAN ANSWER MEMORY for personal details.
    Do not invent private details that are not present there.

    --------------------------------------------------
    WORK AUTHORIZATION
    --------------------------------------------------

    If the role is remote from India or located in India:
    - Authorized to work: Yes
    - Visa sponsorship required: No

    If the role requires relocation outside India:
    - Visa sponsorship required: Yes

    --------------------------------------------------
    PROFESSIONAL DETAILS
    --------------------------------------------------

    - How do hear about job? - LinkedIn

    --------------------------------------------------
    APPLICATION DETAILS
    --------------------------------------------------

    - How did you hear about us: LinkedIn
    - Use HUMAN ANSWER MEMORY for notice period, salary, work mode, and similar preferences.

    --------------------------------------------------
    CANDIDATE PROFILE
    --------------------------------------------------

    {state['candidate_profile']}

    --------------------------------------------------
    HUMAN ANSWER MEMORY (persisted across all jobs/runs)
    --------------------------------------------------

    These answers were saved from previous runs. Use them directly for
    semantically matching questions — do NOT call request_missing_required_information
    if a relevant key already exists here.

    {json.dumps(_load_human_answers(), indent=2)}

    --------------------------------------------------
    HUMAN ANSWERS (this session)
    --------------------------------------------------

    Answers collected during the current run (override memory if keys conflict).

    {json.dumps(state['human_answers'], indent=2)}

    --------------------------------------------------
    FORM FIELDS
    --------------------------------------------------

    {json.dumps(state['form_fields'], indent=2)}

    FORM FIELD ERRORS
    {json.dumps(state['errors'], indent=2)}

    """
