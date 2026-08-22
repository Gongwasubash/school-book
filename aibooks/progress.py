"""Learning-progress tracking for the AI Books portal.

Activity recorded from every resource tab is persisted to a small JSON file so it
survives app restarts. Metrics feed the Progress dashboard and the AI study coach.
"""

from __future__ import annotations

import datetime
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "progress.json")


def _load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "topics": [],
        "cards": 0,
        "mcq_answered": 0,
        "mcq_correct": 0,
        "quizzes": [],
        "projects": [],
        "days": [],
    }


def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _record_day(data):
    day = datetime.date.today().isoformat()
    if day not in data["days"]:
        data["days"].append(day)


def record_topic_viewed(uid):
    data = _load()
    if uid not in data["topics"]:
        data["topics"].append(uid)
    _record_day(data)
    _save(data)


def record_cards_completed(n):
    data = _load()
    data["cards"] += n
    _record_day(data)
    _save(data)


def record_mcq_answered(correct):
    data = _load()
    data["mcq_answered"] += 1
    if correct:
        data["mcq_correct"] += 1
    _record_day(data)
    _save(data)


def record_quiz(score, total):
    data = _load()
    data["quizzes"].append(
        {"score": score, "total": total, "ts": datetime.date.today().isoformat()}
    )
    _record_day(data)
    _save(data)


def record_project(title):
    data = _load()
    data["projects"].append(
        {"title": title, "ts": datetime.date.today().isoformat()}
    )
    _record_day(data)
    _save(data)


def _streak(days):
    ds = sorted(set(days))
    if not ds:
        return 0
    today = datetime.date.today()
    last = datetime.date.fromisoformat(ds[-1])
    if last not in (today, today - datetime.timedelta(days=1)):
        return 0
    streak = 1
    prev = last
    for d in reversed(ds[:-1]):
        if d == (prev - datetime.timedelta(days=1)).isoformat():
            streak += 1
            prev = datetime.date.fromisoformat(d)
        else:
            break
    return streak


def get_progress():
    """Compute the metrics shown on the Progress dashboard."""
    data = _load()
    topics = len(data["topics"])
    cards = data["cards"]
    mcq = data["mcq_answered"]
    quizzes = data["quizzes"]
    projects = len(data["projects"])
    streak = _streak(data["days"])
    quiz_avg = (
        round(sum(q["score"] / q["total"] for q in quizzes) / len(quizzes) * 100)
        if quizzes
        else 0
    )
    overall = round(
        min(topics / 20, 1) * 25
        + min(cards / 50, 1) * 15
        + min(mcq / 30, 1) * 20
        + (quiz_avg / 100) * 20
        + min(projects / 5, 1) * 10
        + min(streak / 7, 1) * 10
    )
    return {
        "topics_viewed": topics,
        "flashcards_completed": cards,
        "mcqs_completed": mcq,
        "quiz_avg": quiz_avg,
        "projects": projects,
        "streak": streak,
        "activity_days": len(data["days"]),
        "overall": overall,
    }


def reset_progress():
    if os.path.exists(DATA_FILE):
        try:
            os.remove(DATA_FILE)
        except OSError:
            pass
