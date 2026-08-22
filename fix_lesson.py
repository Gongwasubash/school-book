# -*- coding: utf-8 -*-
import re

with open(r"E:\rag sys\medical-chatbot-refactored\textbook_indexer.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the end of _clean_deva_title function
idx = content.find("def _clean_deva_title")
if idx >= 0:
    return_idx = content.find("\n    return t\n", content.find("def _clean_deva_title"))
    if return_idx >= 0:
        end_idx = return_idx + len("\n    return t\n")
        while end_idx < len(content) and content[end_idx] == "\n":
            end_idx += 1

        new_func = '''

def _fix_lesson_numbers(title):
    """Fix lesson numbers that were converted to Preeti digits by _clean_deva_title.

    _clean_deva_title converts ASCII digits 1-9 to Preeti equivalents (1->ज्ञ, 2->द्द, etc.)
    when they appear in lesson titles like "Lesson 1: Title". This function reverses
    that for the lesson number part only.
    """
    # Match "Lesson N:" where N is a Preeti digit, convert back to ASCII
    # Preeti digit mappings (what _clean_deva_title produces):
    preeti_to_ascii = {
        "ज्ञ": "1", "द्द": "2", "घ": "3", "द्ध": "4", "छ": "5",
        "ट": "6", "ठ": "7", "ड": "8", "ढ": "9",
    }
    # Pattern: "Lesson N:" where N is a Preeti digit
    import re
    def replace_lesson_num(match):
        preeti_digit = match.group(1)
        ascii_digit = preeti_to_ascii.get(preeti_digit, preeti_digit)
        return f"Lesson {ascii_digit}:"
    return re.sub(r"(Lesson\s+)([ज्ञद्दघद्धछटठडढ])(?=\s*:)",
                  lambda m: f"Lesson {preeti_to_ascii.get(m.group(2), m.group(2))}:",
                  title)

content = content[:end_idx] + "\n" + new_func + "\n" + content[end_idx:]

with open(r"E:\rag sys\medical-chatbot-refactored\textbook_indexer.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Added _fix_lesson_numbers function")