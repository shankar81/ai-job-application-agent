from typing import Any, TypedDict


class AgentState(TypedDict):
    resume_hash_path: str
    resume_file_path: str
    resume_hash: str
    profile_file_path: str
    candidate_profile: dict
    raw_job_desc: dict
    jobs_file_path: str
    job_url: str
    match_score: int
    application_status: str
    form_fields: dict
    llm_response: Any
    human_answers: dict
    errors: dict
