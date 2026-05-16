"""LangGraph node functions.

Each public function in this module is a graph node.
The LLM, tool, and routing logic all live here.
agent.py imports these and wires them into the StateGraph.
"""

import json
import os
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agentic.memory import _load_human_answers, _save_human_answer
from agentic.prompts import build_fill_form_prompt, build_match_prompt, build_profile_prompt
from agentic.state import AgentState
from agentic.tools import create_hash, read_file, read_pdf, write_file, write_jobs_to_csv

load_dotenv()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(content: str) -> str:
    """Strip markdown code fences from an LLM response and return raw JSON.

    GPT models occasionally wrap their JSON output in ```json ... ``` blocks
    despite being told not to. This strips the fences as a safety net.
    If no fences are found the content is returned as-is (stripped).
    """
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    return match.group(1).strip() if match else content.strip()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@tool
def request_missing_required_information(field: str, question: str) -> dict:
    """
        Use ONLY when a REQUIRED field cannot be determined from:
        - candidate profile
        - personal details
        - HUMAN ANSWERS (session state)
        - HUMAN ANSWER MEMORY (persisted across all runs)
        - deterministic inference

        ALWAYS check HUMAN ANSWER MEMORY first before calling this tool.
        If a semantically similar key exists in memory, use that answer directly.
        Never use for already known personal details (name, email, phone, location, etc.).
    """
    answer = input(f"\nQUESTION FOR USER: {question}\n> ")
    _save_human_answer(field, question, answer)

    return {
        "field": field,
        "answer": answer,
    }


tools = [request_missing_required_information]
llm = ChatOpenAI(model="gpt-4.1", temperature=0).bind_tools(tools)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def init(state: AgentState) -> AgentState:
    """Set file paths, load resume hash and candidate profile from disk."""
    # Load persisted human answers from disk so they survive across runs
    state["human_answers"] = _load_human_answers()
    state["resume_hash_path"] = "./storage/resume_hash.txt"
    state["resume_file_path"] = "./storage/resume.pdf"
    state["profile_file_path"] = "./storage/candidate_profile.json"
    state["jobs_file_path"] = "./storage/jobs.xlsx"
    state["match_score"] = 0

    if os.path.exists(state["resume_hash_path"]):
        state["resume_hash"] = read_file(state["resume_hash_path"])

    if os.path.exists(state["profile_file_path"]):
        state["candidate_profile"] = json.loads(
            read_file(state["profile_file_path"])
        )

    return state


def should_create_profile(state: AgentState) -> str:
    """Routing: decide which node to visit after init."""
    if not os.path.exists(state["resume_file_path"]):
        print("Please upload resume to the storage folder first")
        return "exit"

    if not state.get("candidate_profile") or not state.get("resume_hash"):
        return "create_profile"

    if state["resume_hash"] != create_hash(state["resume_file_path"]):
        return "create_profile"

    if state.get("form_fields"):
        return "fill_form"

    return "match_jobs"


def create_candidate_profile(state: AgentState) -> AgentState:
    """Parse the resume PDF via LLM and persist candidate_profile.json."""
    print("[agent] Creating candidate profile from resume.")

    state["resume_hash"] = create_hash(state["resume_file_path"])
    write_file(state["resume_hash_path"], state["resume_hash"])

    pdf_text = read_pdf(state["resume_file_path"])
    prompt = build_profile_prompt(pdf_text)

    response = llm.invoke([HumanMessage(content=prompt)])
    profile = json.loads(response.content)
    write_file(state["profile_file_path"], json.dumps(profile, indent=2))
    state["candidate_profile"] = profile
    print("[agent] Candidate profile saved.")

    return state


def match_jobs(state: AgentState) -> AgentState:
    """Score the current job against the candidate profile and save to jobs.xlsx."""
    print("[agent] Scoring job match.")

    prompt = build_match_prompt(state["candidate_profile"], state["raw_job_desc"])

    response = llm.invoke([HumanMessage(content=prompt)])
    result = json.loads(response.content)
    result["job_url"] = state["job_url"]
    state["match_score"] = result["match_score"]
    state["application_status"] = result.get("application_status", "not_applied")
    write_jobs_to_csv([result], state["jobs_file_path"])
    print(f"[agent] Match score saved: {state['match_score']}")

    return state


def fill_form(state: AgentState) -> AgentState:
    """Ask the LLM to fill form fields; recurse if the tool is called for missing info."""
    print(f"[agent] Filling {len(state.get('form_fields') or [])} form fields.")

    prompt = build_fill_form_prompt(state)

    response = llm.invoke([HumanMessage(content=prompt)])

    if response.tool_calls:
        print("[agent] Missing required information requested.")
        for tool_call in response.tool_calls:
            if tool_call["name"] == "request_missing_required_information":
                tool_result = request_missing_required_information.invoke({
                    "field": tool_call["args"]["field"],
                    "question": tool_call["args"]["question"],
                })
                field = tool_result["field"]
                answer = tool_result["answer"]
                # _save_human_answer is called inside the tool itself;
                # only update the in-session state here.
                state["human_answers"][field] = answer

        return fill_form(state)

    state["form_fields"] = json.loads(_extract_json(response.content))
    print("[agent] Form fields prepared.")

    return state
