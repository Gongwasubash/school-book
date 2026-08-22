"""Official Nepal school curriculum book list, sourced from the Curriculum
Development Centre (CDC), Ministry of Education, Science and Technology
(https://moecdc.gov.np). Maps every subject taught from Nursery (pre-primary)
to Class 10 onto the CDC PDFs available on disk.

School structure (Nepal Education Fact Sheet / CDC):
  - Pre-Primary (ECED): Nursery, LKG, UKG — play-based, no standard gov books
  - Basic education: grades 1-8
  - Secondary education: grades 9-10 (SEE)
"""

from __future__ import annotations

import os
import re

PRE_PRIMARY = [
    {
        "id": "N0",
        "label": "Nursery",
        "level": "Pre-Primary (ECED)",
        "subjects": [
            "English (Rhymes & Phonics)",
            "Nepali (Swar Varna)",
            "Mathematics (Numbers & Shapes)",
            "Science & Environment",
            "Social Studies (My School)",
            "Art & Craft",
        ],
    },
    {
        "id": "N1",
        "label": "LKG",
        "level": "Pre-Primary (ECED)",
        "subjects": [
            "English (Alphabets A-Z)",
            "Nepali (Swar Varna)",
            "Mathematics (Counting 1-20)",
            "Science & Environment",
            "Social Studies",
            "Rhymes & Art",
        ],
    },
    {
        "id": "N2",
        "label": "UKG",
        "level": "Pre-Primary (ECED)",
        "subjects": [
            "English (Reading & Writing)",
            "Nepali (Vyanjan Varna)",
            "Mathematics (Counting 1-100)",
            "Science & Environment",
            "Social Studies",
            "Rhymes & Art",
        ],
    },
]

# display order within a class
_SUBJECT_ORDER = [
    "Nepali",
    "English",
    "Mathematics",
    "Science",
    "Social Studies",
    "Health",
    "Moral Education",
    "Serofero",
    "Computer Science",
    "Optional Mathematics",
    "Accountancy",
    "Economics",
    "History",
    "Vocational",
    "Yoga",
    "Naturopathy",
]


def _classify(fname: str):
    """Return (subject, medium) for an on-disk CDC textbook filename."""
    base = re.sub(r"\.(pdf|md)$", "", fname, flags=re.I).lower()
    nepali_medium = "(nepali" in base
    english_medium = "(english" in base

    if "serofero" in base:
        return "Serofero (Our Surroundings)", "Bilingual"
    if "computer" in base:
        return "Computer Science", "Nepali" if nepali_medium else "English"
    if "accountancy" in base:
        return "Accountancy", "Nepali" if nepali_medium else "English"
    if "economics" in base:
        return "Economics", "Nepali" if nepali_medium else "English"
    if "vocational" in base:
        return "Vocational & Technical Education", "Nepali" if nepali_medium else "English"
    if "naturopath" in base:
        return "Naturopathy", "Nepali" if nepali_medium else "English"
    if "yoga" in base:
        return "Yoga Education", "Nepali" if nepali_medium else "English"
    if "optional mathematics" in base or "optional math" in base:
        return "Optional Mathematics", "Nepali" if nepali_medium else "English"
    if "science" in base and "health" in base and "physical" in base:
        return "Science, Health & Physical Education", "Nepali" if nepali_medium else "English"
    if "health" in base and ("creative" in base or "arts" in base):
        return "Health, Physical & Creative Arts", "Nepali" if nepali_medium else "English"
    if "health" in base:
        return "Health & Physical Education", "Nepali" if nepali_medium else "English"
    if "math" in base:
        return "Mathematics", "Nepali" if nepali_medium else "English"
    if "science" in base:
        return "Science & Technology", "Nepali" if nepali_medium else "English"
    if "social" in base:
        return "Social Studies & Human Value Education", "Nepali" if nepali_medium else "English"
    if "moral" in base:
        return "Moral Education", "Nepali" if nepali_medium else "English"
    if "english" in base:
        return "English", "English"
    if "nepali" in base:
        return "Nepali", "Nepali"
    return re.sub(r"\.(pdf|md)$", "", fname, flags=re.I), "English"


def _sort_key(item):
    subj = item["subject"]
    try:
        idx = _SUBJECT_ORDER.index(next(s for s in _SUBJECT_ORDER if subj.startswith(s)))
    except StopIteration:
        idx = len(_SUBJECT_ORDER)
    return (idx, item["medium"])


def build_curriculum(books):
    """Build the full Nursery->Class 10 curriculum, attaching on-disk files.

    books: list from scan_library() -> {"class", "file", "path", "size"}.
    Returns a list of groups, each {"id", "label", "level", "books"} where
    every book is {"subject", "medium", "available", "file", "size"}.
    """
    groups = []
    for pp in PRE_PRIMARY:
        groups.append(
            {
                "id": pp["id"],
                "label": pp["label"],
                "level": pp["level"],
                "books": [
                    {"subject": s, "medium": "Bilingual", "available": False, "file": None, "size": 0}
                    for s in pp["subjects"]
                ],
            }
        )

    by_class: dict = {}
    for b in books:
        by_class.setdefault(b["class"], []).append(b)

    # Subjects not shown for specific classes (user-curated overrides).
    _HIDE_SUBJECTS_BY_CLASS = {9: {"Yoga Education", "Naturopathy"}}
    # Specific files to hide for specific classes (scanned books with poor OCR etc.)
    _HIDE_FILES_BY_CLASS = {
        8: {"Class 8 Health Physical Creative Arts (English).pdf"},
    }

    for cls in sorted(by_class):
        items = []
        for b in by_class[cls]:
            if re.search(r"\bopen\s*ended\b", b["file"], re.I):
                continue  # "Mathematics Open Ended" duplicates the (Nepali) math book
            subject, medium = _classify(b["file"])
            if subject in _HIDE_SUBJECTS_BY_CLASS.get(cls, set()):
                continue  # hidden from this class's curriculum by request
            if b["file"] in _HIDE_FILES_BY_CLASS.get(cls, set()):
                continue  # hide specific files for this class
            items.append(
                {
                    "subject": subject,
                    "medium": medium,
                    "available": True,
                    "file": b["file"],
                    "size": b["size"],
                }
            )
        items.sort(key=_sort_key)
        groups.append(
            {
                "id": str(cls),
                "label": f"Class {cls}",
                "level": "Basic" if cls <= 8 else "Secondary",
                "books": items,
            }
        )
    return groups


def group_by_id(groups, group_id: str):
    for g in groups:
        if g["id"] == group_id:
            return g
    return None