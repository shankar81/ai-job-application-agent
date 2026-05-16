from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
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

    # Set by ``fill_form`` when the user did not provide an answer (Telegram
    # timeout, Telegram not configured, or any other reason ``ask_user``
    # failed). Easy Apply checks this and bails out of the modal cleanly.
    #
    #   application_aborted: short machine-readable reason
    #                        (e.g. ``"no_human_answer"``)
    #   aborted_reason:      longer human-readable detail recorded in jobs.xlsx
    application_aborted: str
    aborted_reason: str
