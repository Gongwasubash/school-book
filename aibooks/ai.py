"""AI resource generation + assistant chat for the AI Books portal.

`generateLearningResource(type, topic)` is the single seam where a real LLM API can
be plugged in later. Today it synthesises content deterministically from the topic's
curriculum data (falling back to a generic template), so the app works offline.
"""

from __future__ import annotations

import random
import re

from .curriculum import curriculum_for

RESOURCE_TYPES = [
    "Slides", "MCQ", "Vocabulary", "Flashcards", "Questions", "Videos",
    "Key Points", "Key Terms", "Real-Life Examples", "Fun Facts",
    "Group Activity", "Summary", "Project Work", "Mind Map", "Points to Remember",
]

TEACHER_RESOURCES = [
    "Lesson Plan", "Teaching Notes", "Classroom Activity", "Assignment",
    "Quiz", "Discussion Questions", "Assessment Rubric",
]


def _topic_data(class_name, subject_name, chapter_name, topic_name):
    """Return the topic dict if found in the curriculum, else a stub."""
    for subject in curriculum_for(class_name):
        if subject["name"] != subject_name:
            continue
        for chapter in subject.get("chapters", []):
            if chapter["name"] != chapter_name:
                continue
            for topic in chapter.get("topics", []):
                if topic["name"] == topic_name:
                    return topic
    return {"name": topic_name}


def _stub_topic(topic_name):
    """Generic content when a topic has no seeded curriculum data."""
    return {
        "name": topic_name,
        "objectives": [
            f"Explain the meaning of {topic_name}.",
            f"Describe the main ideas of {topic_name}.",
            "Apply the concepts to real-life situations.",
        ],
        "flashcards": [
            (f"What is {topic_name}?", f"{topic_name} is an important concept covered in this topic."),
            ("Why is it important?", "It helps connect the theory to everyday life."),
        ],
        "mcq": [
            {
                "q": f"Which statement best describes {topic_name}?",
                "options": ["A key concept in this unit", "An unrelated idea", "A simple definition", "A random fact"],
                "answer": "A key concept in this unit",
                "explanation": f"{topic_name} is central to understanding this unit.",
            }
        ],
        "vocabulary": [
            ("Term", "Definition of the key term.", "Example sentence using the term."),
        ],
        "key_points": [
            f"{topic_name} is the central idea of this topic.",
            "Related concepts build on this foundation.",
            "Practice helps reinforce understanding.",
        ],
        "summary": (
            f"{topic_name} introduces the core ideas of this chapter. By studying it you will "
            "understand how the concept connects to the wider subject and to daily life."
        ),
        "fun_facts": ["Learning in small steps makes it easier to remember."],
        "real_life": [
            ("Example 1", f"Where you can see {topic_name} in action."),
            ("Example 2", "Another everyday situation that uses this idea."),
        ],
        "project": {
            "title": f"{topic_name} Project",
            "objective": f"Explore {topic_name} through hands-on work.",
            "activities": ["Research", "Collect examples", "Prepare a report"],
        },
        "mind_map": {
            "center": topic_name,
            "branches": ["Concept 1", "Concept 2", "Example", "Practice", "Application", "Review"],
        },
    }


def generate_learning_resource(resource_type: str, class_name: str, subject_name: str,
                               chapter_name: str, topic_name: str, seed=None):
    """Return a JSON-serialisable structure for a learning resource.

    Replace the body of this function with a real LLM call later — the signature is
    the stable contract the UI depends on.
    """
    topic = seed or _topic_data(class_name, subject_name, chapter_name, topic_name)
    name = topic["name"]

    if resource_type == "Flashcards":
        cards = topic.get("flashcards") or []
        if not cards:
            cards = _stub_topic(name)["flashcards"]
        return {"type": "Flashcards", "topic": name, "cards": [
            {"front": f, "back": b} for f, b in cards]}

    if resource_type == "MCQ":
        items = topic.get("mcq") or []
        if not items:
            items = _stub_topic(name)["mcq"]
        return {"type": "MCQ", "topic": name, "questions": items}

    if resource_type == "Vocabulary":
        vocab = topic.get("vocabulary") or []
        if not vocab:
            vocab = _stub_topic(name)["vocabulary"]
        return {"type": "Vocabulary", "topic": name, "items": [
            {"term": t, "meaning": m, "example": e} for t, m, e in vocab]}

    if resource_type == "Questions":
        return {"type": "Questions", "topic": name, "questions": [
            {"q": f"Explain the main idea of {name}.", "a": topic.get("summary", "")},
            {"q": f"Why is {name} important?", "a": "It builds the foundation for the rest of the unit."},
            {"q": "Give an example from daily life.", "a": "Look at the real-life examples in this topic."},
        ]}

    if resource_type == "Key Points":
        points = topic.get("key_points") or _stub_topic(name)["key_points"]
        return {"type": "Key Points", "topic": name, "points": points}

    if resource_type == "Key Terms":
        vocab = topic.get("vocabulary") or _stub_topic(name)["vocabulary"]
        return {"type": "Key Terms", "topic": name, "terms": [
            {"term": t, "definition": m} for t, m, e in vocab]}

    if resource_type == "Real-Life Examples":
        ex = topic.get("real_life") or _stub_topic(name)["real_life"]
        return {"type": "Real-Life Examples", "topic": name, "examples": [
            {"title": t, "description": d} for t, d in ex]}

    if resource_type == "Fun Facts":
        facts = topic.get("fun_facts") or _stub_topic(name)["fun_facts"]
        return {"type": "Fun Facts", "topic": name, "facts": facts}

    if resource_type == "Group Activity":
        return {"type": "Group Activity", "topic": name,
                "activity": {
                    "title": f"Explore {name} Together",
                    "description": f"Work in groups to understand {name} and share your findings.",
                    "steps": ["Form groups of 4-5 students", "Discuss the key ideas",
                              "Prepare a short presentation", "Present to the class"],
                }}

    if resource_type == "Summary":
        return {"type": "Summary", "topic": name,
                "overview": topic.get("summary", _stub_topic(name)["summary"]),
                "concepts": topic.get("key_points", _stub_topic(name)["key_points"]),
                "takeaways": [
                    "You can now explain the main idea of the topic.",
                    "You can relate it to real-life situations.",
                    "You are ready for the practice questions.",
                ]}

    if resource_type == "Project Work":
        proj = topic.get("project") or _stub_topic(name)["project"]
        return {"type": "Project Work", "topic": name, "project": {
            "title": proj["title"], "objective": proj["objective"],
            "activities": proj.get("activities", [])}}

    if resource_type == "Mind Map":
        mm = topic.get("mind_map") or _stub_topic(name)["mind_map"]
        return {"type": "Mind Map", "topic": name, "center": mm["center"], "branches": mm["branches"]}

    if resource_type == "Slides":
        points = topic.get("key_points") or _stub_topic(name)["key_points"]
        slides = [{"title": name, "subtitle": "Main Concepts", "bullets": points[:4]}]
        slides += [
            {"title": f"Learning Objectives - {name}",
             "subtitle": "What you will learn", "bullets": (topic.get("objectives") or _stub_topic(name)["objectives"])},
            {"title": "Real-Life Application",
             "subtitle": "Where it shows up", "bullets": [d for _, d in (topic.get("real_life") or [])]},
            {"title": "Quick Recap",
             "subtitle": "Points to remember", "bullets": points},
        ]
        return {"type": "Slides", "topic": name, "slides": slides}

    if resource_type == "Videos":
        return {"type": "Videos", "topic": name, "videos": [
            {"title": f"Video: {name} - Introduction", "url": "", "desc": "Animated introduction to the topic."},
            {"title": f"Video: {name} - Examples", "url": "", "desc": "Worked examples with narration."},
        ]}

    if resource_type == "Points to Remember":
        points = topic.get("key_points") or _stub_topic(name)["key_points"]
        return {"type": "Points to Remember", "topic": name, "points": points}

    # Teacher resources
    if resource_type in TEACHER_RESOURCES:
        return {"type": resource_type, "topic": name, "content": [
            {"heading": resource_type, "text": (
                f"Teacher guide for {name}. Adapt this to your classroom needs, "
                "differentiate by student level, and connect to the learning objectives."
            )},
        ]}

    return {"type": resource_type, "topic": name, "note": "Not implemented yet."}


def generate_chat_reply(topic_name, question, lang="ne"):
    """Deterministic assistant reply. Swap for a real LLM call later."""
    q = (question or "").strip().lower()
    if any(w in q for w in ["what", "के", "को", "why", "किन", "how", "कसरी"]):
        base = (
            f"'{topic_name}' is an important topic in this chapter. "
            "Start with the Flashcards to learn the key definitions, then try the Summary "
            "and Key Points to solidify your understanding. If you want, I can generate "
            "MCQ questions for you to practice!"
        )
    else:
        base = (
            f"I'm here to help you learn about '{topic_name}'. "
            "Try opening the Summary, Key Points, or generate MCQ questions to test yourself. "
            "Ask me about any part you find difficult."
        )
    if lang == "ne":
        return (
            f"'{topic_name}' यस पाठको महत्त्वपूर्ण विषय हो। Flashcard बाट मुख्य परिभाषा सिक्नुहोस्, "
            "त्यसपछि Summary र Key Points ले तपाईंको बुझाइ मजबुत बनाउँछ। चाहनुहुन्छ भने म MCQ "
            "प्रश्नहरू पनि उत्पन्न गरिदिन्छु।"
        )
    return base


def generation_phrases(lang):
    if lang == "ne":
        return ["विषय विश्लेषण गर्दै...", "शैक्षिक सामग्री बनाउँदै...", "उदाहरण तयार गर्दै...", "स्रोत तयार पार्दै...", "लगभग तयार..."]
    return ["Analyzing topic...", "Creating educational content...", "Generating examples...", "Preparing learning resources...", "Almost ready..."]