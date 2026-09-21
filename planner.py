"""Personalized learning plans from real MIT Learn resources.

Pipeline: user request -> Claude decomposes into sub-topics -> MIT Learn vector
search per sub-topic -> Claude builds a plan using ONLY the returned resources.
"""
from __future__ import annotations

import os
from typing import List, Optional

import anthropic
import requests
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

MODEL = "claude-opus-5"
SEARCH_URL = "https://api.learn.mit.edu/api/v0/vector_learning_resources_search/"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------- MIT Learn search ----------

def search(query: str, limit: int = 5) -> list[dict]:
    """Call MIT Learn vector search and return the top `limit` results as compact records.

    Note: the API currently ignores `limit` and can return up to 200 results, so we
    truncate client-side (results come back ordered by relevance).
    """
    r = requests.get(SEARCH_URL, params={"q": query, "limit": limit}, timeout=30)
    r.raise_for_status()
    out = []
    for x in r.json().get("results", [])[:limit]:
        prices = sorted({float(p) for p in (x.get("prices") or [])})
        time = x.get("time_commitment") or x.get("duration") or ""
        ep = x.get("podcast_episode") or {}
        if not time and ep.get("duration"):
            time = ep["duration"]  # ISO 8601, e.g. PT24M33S
        out.append({
            "id": x["id"],
            "title": x.get("title"),
            "resource_type": x.get("resource_type"),
            "offered_by": (x.get("offered_by") or {}).get("name"),
            "platform": (x.get("platform") or {}).get("name"),
            "free": x.get("free"),
            "prices_usd": prices,
            "certificate": (x.get("certification_type") or {}).get("name"),
            "time": time,
            "url": x.get("learn_url") or x.get("url"),
            "description": (x.get("description") or "")[:400],
        })
    return out


# ---------- Structured output schemas ----------

class SubTopic(BaseModel):
    title: str
    search_query: str
    why: str


class SubTopics(BaseModel):
    learner_summary: str
    subtopics: List[SubTopic]


class Step(BaseModel):
    resource_id: int
    subtopic: str
    why: str
    estimated_time: str


class Plan(BaseModel):
    steps: List[Step]
    rationale: str
    gaps: str
    total_time: str


# ---------- Claude calls ----------

DECOMPOSE_SYSTEM = """You design learning paths from MIT's public catalog (courses, videos,
podcasts, programs). Break the learner's request into 3-6 ordered sub-topics, prerequisites
first. Adapt depth and starting point to what the learner says about their background,
goals, and available time: skip prerequisites they already have, keep it short if their time
is short. Each sub-topic needs a concise search query (3-8 words) that would match catalog
titles/descriptions well."""


def decompose(request: str) -> SubTopics:
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=DECOMPOSE_SYSTEM,
        messages=[{"role": "user", "content": request}],
        output_format=SubTopics,
    )
    return resp.parsed_output


PLAN_SYSTEM = """You build a personalized learning plan from a fixed set of candidate
resources returned by the MIT Learn catalog search. Rules:
- Use ONLY resources from the candidate list, referenced by their numeric id. Never invent
  or mention resources that are not in the list.
- Order steps so prerequisites come first. Skip candidates that are off-topic or a poor fit
  for the learner (wrong level, too long for their time budget). It is fine to use fewer
  candidates than provided. Use at most 6 steps (3-6 is typical).
- For each step, give a one-sentence reason tailored to the learner, and a realistic time
  estimate. For long courses, say which part to do, or that it is an optional deep dive.
- In `gaps`, say plainly what the learner asked for that the catalog results do not cover
  well, and what they might look for elsewhere.
- `rationale`: 2-3 sentences on how the plan fits this learner.
- `total_time`: rough total for the recommended (non-optional) steps."""


def build_plan(request: str, subtopics: SubTopics, results: dict[str, list[dict]]) -> Plan:
    lines = [f"LEARNER REQUEST:\n{request}\n", f"LEARNER SUMMARY: {subtopics.learner_summary}\n",
             "CANDIDATE RESOURCES (grouped by sub-topic search):"]
    for st in subtopics.subtopics:
        lines.append(f"\n## {st.title}  (search: \"{st.search_query}\")")
        for r in results.get(st.title, []):
            cost = "free" if r["free"] else (f"paid ${r['prices_usd']}" if r["prices_usd"] else "price unknown")
            if r["free"] and r["prices_usd"] and max(r["prices_usd"]) > 0:
                cost = f"free (certificate ${max(r['prices_usd']):.0f})"
            lines.append(
                f"- id={r['id']} | {r['title']} | {r['resource_type']} | {r['offered_by']} | "
                f"{cost} | time: {r['time'] or 'unknown'} | {r['description']}"
            )
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=PLAN_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(lines)}],
        output_format=Plan,
    )
    return resp.parsed_output


# ---------- Orchestration ----------

def generate(request: str, per_topic: int = 5) -> dict:
    subtopics = decompose(request)
    results: dict[str, list[dict]] = {}
    for st in subtopics.subtopics:
        results[st.title] = search(st.search_query, per_topic)

    plan = build_plan(request, subtopics, results)

    # Hard guarantee: only resources the API actually returned make it into the plan.
    by_id = {r["id"]: r for rs in results.values() for r in rs}
    steps, dropped = [], []
    for s in plan.steps[:6]:  # hard cap at 6 steps
        r = by_id.get(s.resource_id)
        if r is None:
            dropped.append(s.resource_id)
            continue
        steps.append({**r, "subtopic": s.subtopic, "why": s.why, "estimated_time": s.estimated_time})

    return {
        "subtopics": subtopics.model_dump(),
        "results": results,
        "steps": steps,
        "rationale": plan.rationale,
        "gaps": plan.gaps,
        "total_time": plan.total_time,
        "dropped_ids": dropped,
    }


def cost_label(r: dict) -> str:
    if r["free"]:
        paid = [p for p in r["prices_usd"] if p > 0]
        return f"Free (optional certificate ${max(paid):.0f})" if paid else "Free"
    return f"Paid (${min(r['prices_usd']):,.0f})" if r["prices_usd"] else "Paid"


if __name__ == "__main__":
    import json, sys
    req = " ".join(sys.argv[1:]) or "I'm a parent with a basic bio background, I have about an hour, how does the covid vaccine work?"
    out = generate(req)
    print("SUB-TOPICS:")
    for st in out["subtopics"]["subtopics"]:
        print(f"  - {st['title']}  [q: {st['search_query']}]  -> {len(out['results'][st['title']])} results")
    print(f"\nPLAN ({out['total_time']}):")
    for i, s in enumerate(out["steps"], 1):
        print(f"  {i}. {s['title']} ({s['resource_type']}, {cost_label(s)}, ~{s['estimated_time']})\n     {s['url']}\n     {s['why']}")
    print("\nRATIONALE:", out["rationale"])
    print("GAPS:", out["gaps"])
    if out["dropped_ids"]:
        print("DROPPED (not in API results):", out["dropped_ids"])
