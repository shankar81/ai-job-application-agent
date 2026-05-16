from urllib.parse import parse_qs, urlparse
from pypdf import PdfReader
import pandas as pd
import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import List, TypedDict

class FileItem(TypedDict):
    name: str
    path: str
    isFile: bool

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


class Job(TypedDict):
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
    application_status: str
    applied_on: str
    application_error: str
    updated_on: str


APPLICATION_COLUMNS = {
    "application_status": "not_applied",
    "applied_on": "",
    "application_error": "",
    "updated_on": "",
}

def list_files(path: str) -> List[FileItem]:
    """This will return list of files/folder available at the path from the argument"""
    path = os.path.abspath(path)
    result: List[FileItem] = []
    for item in os.listdir(path):
        full_path = os.path.join(path, item)
        result.append({ "name": item, "path": full_path, "isFile": os.path.isfile(full_path)})

    return result

def create_hash(filepath: str) -> str:
    """This will create SHA256 has for given file on filepath"""
    sha256 = hashlib.sha256()

    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)

    return sha256.hexdigest()

def compare_hash(filepath: str, hash: str) -> bool:
    """This will compare the hash of file on filepath with given hash"""
    return create_hash(filepath) == hash

def read_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text

def create_file(path: str, filename: str):
    """Create file at given path with given filename"""
    directory = Path(path)

    # create directory if not exists
    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = directory / filename

    # create empty file
    file_path.touch(exist_ok=True)

    return file_path

def read_file(file_path: str) -> str:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return f.read()

def write_file(file_path: str, content: str):
    path = Path(file_path)

    # create parent folders if missing
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(content)

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _job_key(url: str | None) -> str | None:
    return get_linkedin_job_id(url) or url


def _job_row(job: dict) -> dict:
    description = job.get("description", {}) or {}
    match_reason = job.get("match_reason", {}) or {}
    company_insights = description.get("company_insights", {}) or {}

    return {
        "slug": job.get("slug"),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "work_mode": job.get("work_mode"),
        "easy_apply": job.get("easy_apply"),
        "required_experience_years": job.get("required_experience_years"),
        "job_url": job.get("job_url"),
        "match_score": job.get("match_score"),
        "strong_matches": "|".join(match_reason.get("strong_matches", [])),
        "missing_or_weaker_areas": "|".join(
            match_reason.get("missing_or_weaker_areas", [])
        ),
        "summary": description.get("summary"),
        "skills_required": "|".join(description.get("skills_required", [])),
        "responsibilities": "|".join(description.get("responsibilities", [])),
        "total_employees": company_insights.get("total_employees"),
        "median_employee_tenure": company_insights.get("median_employee_tenure"),
        "focus_areas": "|".join(company_insights.get("focus_areas", [])),
        "application_status": job.get("application_status") or "not_applied",
        "applied_on": job.get("applied_on") or "",
        "application_error": job.get("application_error") or "",
        "updated_on": job.get("updated_on") or _now_iso(),
    }


def _ensure_application_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column, default in APPLICATION_COLUMNS.items():
        if column not in df.columns:
            df[column] = default
    return df


def _merge_job_rows(existing: dict, incoming: dict) -> dict:
    merged = {**existing, **incoming}

    # Scoring should not clear application state that was set after a submit.
    if existing.get("application_status") == "applied" and incoming.get("application_status") == "not_applied":
        merged["application_status"] = existing.get("application_status")
        merged["applied_on"] = existing.get("applied_on", "")
        merged["application_error"] = existing.get("application_error", "")

    return merged


def _write_job_records(records: list[dict], excel_path: str) -> None:
    df = pd.DataFrame(records)
    df = _ensure_application_columns(df)

    if "match_score" in df.columns:
        df = df.sort_values(
            by="match_score",
            ascending=False,
            na_position="last"
        )

    df = df.reset_index(drop=True)
    df.to_excel(
        excel_path,
        index=False,
        engine="openpyxl"
    )

    print(f"Saved {len(df)} jobs to {excel_path}")


def find_job_record(excel_path: str, job_url: str) -> dict | None:
    if not os.path.exists(excel_path):
        return None

    target_key = _job_key(job_url)
    for job in read_jobs_excel(excel_path):
        if _job_key(job.get("job_url")) == target_key:
            return job

    return None


def update_job_application_status(
    excel_path: str,
    job_url: str,
    status: str,
    error: str = "",
) -> None:
    if not os.path.exists(excel_path):
        return

    target_key = _job_key(job_url)
    records = read_jobs_excel(excel_path)
    now = _now_iso()

    for record in records:
        if _job_key(record.get("job_url")) != target_key:
            continue

        record["application_status"] = status
        record["updated_on"] = now
        record["application_error"] = error
        if status == "applied":
            record["applied_on"] = now
        elif "applied_on" not in record:
            record["applied_on"] = ""
        break

    _write_job_records(records, excel_path)


def write_jobs_to_csv(jobs: list[Job], excel_path: str):
    """Write job to csv file at excel_path with Job Type List"""
    rows = []

    for job in jobs:
        rows.append(_job_row(job))


    # create parent folder if missing
    Path(excel_path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    records = []

    if os.path.exists(excel_path):
        records = read_jobs_excel(excel_path)

    for row in rows:
        row_key = _job_key(row.get("job_url"))
        existing_index = next(
            (
                index
                for index, record in enumerate(records)
                if _job_key(record.get("job_url")) == row_key
            ),
            None,
        )

        if existing_index is None:
            records.append(row)
        else:
            records[existing_index] = _merge_job_rows(records[existing_index], row)

    _write_job_records(records, excel_path)

def read_jobs_excel(excel_path: str):
    df = pd.read_excel(
        excel_path,
        engine="openpyxl"
    )
    df = _ensure_application_columns(df)
    df = df.where(pd.notna(df), "")

    return df.to_dict(orient='records')


def get_linkedin_job_id(
    url: str
) -> str | None:

    parsed = urlparse(url)

    params = parse_qs(parsed.query)

    return params.get(
        "currentJobId",
        [None]
    )[0]
