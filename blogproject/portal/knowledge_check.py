"""Pre-Masterclass Questions ("Knowledge Check" tab in the portal).

The questions are defined here once: the portal page shows them, the API
validates answers against them, and the admin/CSV export uses them for the
column headings. Answers are stored per user in KnowledgeCheck.answers.

To change a question or an option, edit QUESTIONS below. Keep the "key" values
the same, otherwise answers already saved under the old key will no longer be
shown (they stay in the database).
"""

QUESTIONS = [
    {
        "key": "role",
        "text": "Your current role/function",
        "type": "single",
        "options": [
            "Production", "Maintenance", "Quality", "Automation", "IT/OT",
            "Digital Transformation", "Management", "Other",
        ],
        # Choosing "Other" asks for a short text
        "other": {"key": "role_other", "label": "Please specify your role", "when": "Other"},
    },
    {
        "key": "experience",
        "text": "Your experience in manufacturing/industrial automation",
        "type": "single",
        "options": ["<3 Years", "3–7 Years", "8–15 Years", "15+ Years"],
    },
    {
        "key": "plc_knowledge",
        "text": "How would you rate your PLC/SCADA/Industrial Automation knowledge?",
        "type": "single",
        "options": ["Beginner", "Intermediate", "Advanced"],
    },
    {
        "key": "industrial_data",
        "text": (
            "Have you worked with industrial communication/data technologies such as "
            "OPC UA, MQTT, Modbus, APIs or IIoT Gateways?"
        ),
        "type": "single",
        "options": ["No Exposure", "Basic Understanding", "Hands-on Experience"],
    },
    {
        "key": "ai_ml",
        "text": "How would you rate your understanding of AI/ML?",
        "type": "single",
        "options": ["Beginner", "Basic Understanding", "Intermediate", "Hands-on/Advanced"],
    },
    {
        "key": "genai_tools",
        "text": "Have you used Generative AI tools such as ChatGPT, Copilot or similar tools professionally?",
        "type": "single",
        "options": ["Never", "Occasionally", "Regularly"],
    },
    {
        "key": "rag_agents",
        "text": "Are you familiar with RAG, LLMs, AI Agents or Agentic AI?",
        "type": "single",
        "options": ["Not Familiar", "Basic Understanding", "Working Knowledge", "Hands-on Experience"],
    },
    {
        "key": "ai_usecase",
        "text": "Have you worked on any AI/ML use case in manufacturing?",
        "type": "single",
        "options": ["No", "PoC/Experiment", "Implemented in Production"],
        # Any answer except "No" asks (optionally) for the use case
        "detail": {
            "key": "ai_usecase_details",
            "label": "If yes, please briefly mention the use case",
            "unless": "No",
        },
    },
    {
        "key": "interests",
        "text": "Which areas are you most interested in?",
        "type": "multi",
        "options": [
            "Predictive AI", "Generative AI + RAG", "AI Agents / Agentic AI",
            "AI + PLC/SCADA Integration", "Predictive Maintenance",
            "Quality / Computer Vision", "Autonomous Manufacturing",
        ],
        "hint": "Select all that apply",
    },
    {
        "key": "problem",
        "text": (
            "Please mention one real manufacturing problem/use case you would like to "
            "explore during the Masterclass"
        ),
        "type": "text",
        "required": False,
    },
]

MAX_TEXT = 1000


def _text(value):
    return str(value or "").strip()


def clean_answers(raw):
    """Validates the submitted answers. Returns (answers, error_message)."""
    if not isinstance(raw, dict):
        return None, "Invalid answers."
    answers = {}
    for number, q in enumerate(QUESTIONS, 1):
        key = q["key"]
        if q["type"] == "single":
            value = _text(raw.get(key))
            if value not in q["options"]:
                return None, f"Please answer question {number}."
            answers[key] = value
            extra = q.get("other") or q.get("detail")
            if extra:
                text = _text(raw.get(extra["key"]))[:MAX_TEXT]
                shown = value == extra["when"] if "when" in extra else value != extra["unless"]
                if "when" in extra and shown and not text:
                    return None, f"Question {number}: {extra['label'].lower()}."
                answers[extra["key"]] = text if shown else ""
        elif q["type"] == "multi":
            value = raw.get(key)
            if not isinstance(value, list):
                return None, f"Please answer question {number}."
            picked = [o for o in q["options"] if o in {_text(v) for v in value}]  # keep the listed order
            if not picked:
                return None, f"Please select at least one option in question {number}."
            answers[key] = picked
        else:
            value = _text(raw.get(key))[:MAX_TEXT]
            if q.get("required", True) and not value:
                return None, f"Please answer question {number}."
            answers[key] = value
    return answers, None


def columns():
    """(key, heading) pairs in question order, for the CSV export."""
    cols = []
    for number, q in enumerate(QUESTIONS, 1):
        cols.append((q["key"], f"Q{number}. {q['text']}"))
        extra = q.get("other") or q.get("detail")
        if extra:
            cols.append((extra["key"], f"Q{number}. {extra['label']}"))
    return cols


def display(value):
    return ", ".join(value) if isinstance(value, list) else (value or "")


def participant_name(check):
    profile = getattr(check.user, "portal_profile", None)
    return profile.full_name if profile else (check.user.get_full_name() or check.user.email)


def answer_rows(check):
    """[(question number + text, answer text), ...] for one participant, extras included."""
    rows = []
    for number, q in enumerate(QUESTIONS, 1):
        rows.append((f"Q{number}. {q['text']}", display(check.answers.get(q["key"])) or "-"))
        extra = q.get("other") or q.get("detail")
        if extra and check.answers.get(extra["key"]):
            rows.append((f"Q{number}. {extra['label']}", check.answers[extra["key"]]))
    return rows


def csv_response(checks):
    """CSV download (opens in Excel) with one row per participant, one column per question."""
    import csv

    from django.http import HttpResponse
    from django.utils import timezone

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    name = f"pre-masterclass-answers-{timezone.localdate():%Y-%m-%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response.write("﻿")  # lets Excel open the UTF-8 file correctly
    writer = csv.writer(response)
    cols = columns()
    writer.writerow(["Name", "Email", "Submitted"] + [heading for _, heading in cols])
    for check in checks:
        writer.writerow(
            [participant_name(check), check.user.email,
             f"{timezone.localtime(check.submitted_at):%d %b %Y %H:%M}"]
            + [display(check.answers.get(key)) for key, _ in cols]
        )
    return response
