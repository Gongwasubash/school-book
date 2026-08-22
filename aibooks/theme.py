"""Dark dashboard theme + fixed header + language labels for the AI Books portal."""

import streamlit as st

# Brand palette from the spec
BG = "#080B12"
BG2 = "#111522"
CARD = "#151927"
BORDER = "#252B3A"
BLUE = "#3867FF"
PURPLE = "#7C4DFF"
ORANGE = "#FF7A18"
GREEN = "#19C37D"
WHITE = "#F5F7FA"
MUTED = "#8992A6"

# Resource type -> icon + accent (order matches spec's Contents panel)
RESOURCES = [
    ("Slides", "\u25a3", BLUE),
    ("MCQ", "\u25cf", ORANGE),
    ("Vocabulary", "\u25a3", PURPLE),
    ("Flashcards", "\u25a3", GREEN),
    ("Questions", "?", BLUE),
    ("Videos", "\u25b6", ORANGE),
    ("Key Points", "\u2691", PURPLE),
    ("Key Terms", "\u2315", GREEN),
    ("Real-Life Examples", "\U0001f30e", BLUE),
    ("Fun Facts", "\u26a1", ORANGE),
    ("Group Activity", "\u2637", PURPLE),
    ("Summary", "\u25a3", GREEN),
    ("Project Work", "\u2321", BLUE),
    ("Mind Map", "\u2713", PURPLE),
    ("Points to Remember", "\u2605", ORANGE),
    ("Progress", "\U0001f4ca", GREEN),
]
RESOURCE_TYPES = [r[0] for r in RESOURCES]

TEACHER_RESOURCES = [
    "Lesson Plan",
    "Teaching Notes",
    "Classroom Activity",
    "Assignment",
    "Quiz",
    "Discussion Questions",
    "Assessment Rubric",
]

L = {
    "ai_books": {"en": "AI Books", "ne": "AI Books"},
    "tagline": {"en": "AI Learning Portal", "ne": "AI सिकाइ पोर्टल"},
    "raise_ticket": {"en": "Raise Ticket", "ne": "टिकट उठाउनुहोस्"},
    "classes": {"en": "CLASSES", "ne": "कक्षाहरू"},
    "contents": {"en": "Contents", "ne": "विषयवस्तु"},
    "select_a_topic": {"en": "Select a Topic", "ne": "एउटा विषय छान्नुहोस्"},
    "empty_desc": {
        "en": "Choose a class, subject, chapter, and topic from the sidebar to start learning.",
        "ne": "सिक्न सुरु गर्न साइडबारबाट कक्षा, विषय, पाठ र विषयवस्तु छान्नुहोस्।",
    },
    "topic_content": {"en": "Topic Content", "ne": "विषयवस्तु"},
    "teacher_resources": {"en": "Teacher Resources", "ne": "शिक्षक स्रोतहरू"},
    "learning_objectives": {"en": "Learning Objectives", "ne": "सिकाइ उद्देश्यहरू"},
    "regenerate": {"en": "Regenerate", "ne": "पुनः उत्पन्न गर्नुहोस्"},
    "ai_generate": {"en": "AI Generate", "ne": "AI उत्पन्न गर्नुहोस्"},
    "resources": {"en": "Resources", "ne": "स्रोतहरू"},
    "student_resources": {"en": "Student Resources", "ne": "विद्यार्थी स्रोतहरू"},
    "flip_card": {"en": "Flip Card", "ne": "कार्ड पल्टाउनुहोस्"},
    "previous": {"en": "Previous", "ne": "अघिल्लो"},
    "next": {"en": "Next", "ne": "पछिल्लो"},
    "try_again": {"en": "Try Again", "ne": "फेरि प्रयास गर्नुहोस्"},
    "review_answers": {"en": "Review Answers", "ne": "उत्तरहरू हेर्नुहोस्"},
    "your_score": {"en": "Your Score", "ne": "तपाईंको स्कोर"},
    "ai_assistant": {"en": "AI Learning Assistant", "ne": "AI सिकाइ सहायक"},
    "ask_me": {"en": "Ask me anything about", "ne": "बारे जे पनि सोध्नुहोस्"},
    "type_question": {"en": "Type your question...", "ne": "तपाईंको प्रश्न लेख्नुहोस्..."},
    "search": {"en": "Search topics, subjects...", "ne": "विषयवस्तु, पाठ खोज्नुहोस्..."},
    "your_progress": {"en": "Your Learning Progress", "ne": "तपाईंको सिकाइ प्रगति"},
    "admin": {"en": "Admin", "ne": "प्रशासक"},
    "learning_objectives_list": {
        "en": "After completing this topic, students will be able to:",
        "ne": "यो विषयवस्तु पूरा गरेपछि विद्यार्थीहरूले:",
    },
    "generating": {"en": "Generating", "ne": "उत्पन्न भइरहेको छ"},
    "curating": {"en": "Curating high-quality content...", "ne": "उच्च गुणस्तरीय सामग्री तयार गर्दै..."},
    "no_kb": {"en": "No knowledge base", "ne": "कुनै ज्ञान भण्डार छैन"},
    "subjects": {"en": "Subjects (Books)", "ne": "विषयहरू (पुस्तकहरू)"},
    "book": {"en": "Book", "ne": "पुस्तक"},
    "chapters": {"en": "Chapters", "ne": "पाठहरू"},
    "select_all": {"en": "Select all chapters", "ne": "सबै पाठ छान्नुहोस्"},
    "build_kb": {"en": "Build Knowledge Base", "ne": "ज्ञान भण्डार निर्माण गर्नुहोस्"},
    "rebuild_kb": {"en": "Rebuild Knowledge Base", "ne": "ज्ञान भण्डार पुनः निर्माण गर्नुहोस्"},
    "llm_provider": {"en": "LLM Provider", "ne": "LLM प्रदायक"},
    "no_books": {"en": "No textbooks found in the library folder.", "ne": "पुस्तकालय फोल्डरमा कुनै पाठ्यपुस्तक भेटिएन।"},
    "empty_nav": {
        "en": "Pick a class, subject and chapters from the sidebar, then click Build Knowledge Base to start learning.",
        "ne": "साइडबारबाट कक्षा, विषय र पाठ छानेर ज्ञान भण्डार निर्माण गर्नुहोस्।",
    },
    "index_ready": {"en": "Index ready", "ne": "अनुक्रमणिका तयार छ"},
    "chunks": {"en": "chunks", "ne": "टुक्राहरू"},
    "select_chapters_hint": {"en": "Select one or more chapters to include.", "ne": "समावेश गर्न एक वा बढी पाठ छान्नुहोस्।"},
    "generating_resource": {"en": "Generating", "ne": "उत्पन्न भइरहेको छ"},
    "ask_about": {"en": "Ask about the selected chapters", "ne": "छानिएका पाठहरूबारे सोध्नुहोस्"},
    "no_store_hint": {"en": "Knowledge base not built yet.", "ne": "ज्ञान भण्डार अझै निर्माण भएको छैन।"},
    "sources": {"en": "Sources", "ne": "स्रोतहरू"},
    "progress": {"en": "Progress", "ne": "प्रगति"},
    "topics_viewed": {"en": "Topics viewed", "ne": "हेरिएका विषयवस्तुहरू"},
    "flashcards_completed": {"en": "Flashcards completed", "ne": "पूरा भएका फ्ल्यासकार्डहरू"},
    "mcqs_completed": {"en": "MCQs completed", "ne": "पूरा भएका MCQ"},
    "quiz_scores": {"en": "Quiz scores", "ne": "प्रश्नोत्तरी स्कोर"},
    "projects": {"en": "Projects", "ne": "परियोजनाहरू"},
    "learning_streak": {"en": "Learning streak", "ne": "सिकाइ क्रम"},
    "overall_progress": {"en": "Overall progress", "ne": "समग्र प्रगति"},
    "days": {"en": "days", "ne": "दिनहरू"},
    "ai_insight": {"en": "AI insight", "ne": "AI अन्तर्दृष्टि"},
    "reset_progress": {"en": "Reset progress", "ne": "प्रगति रिसेट गर्नुहोस्"},
    "generating_insight": {"en": "Generating progress insights...", "ne": "प्रगति अन्तर्दृष्टि उत्पन्न गर्दै..."},
    "activity_days": {"en": "Active days", "ne": "सक्रिय दिनहरू"},
}


def _(key, lang):
    return L.get(key, {}).get(lang, key)


def apply_theme():
    st.markdown(
        f"""
<style>
    :root {{
        --bg: {BG}; --bg2: {BG2}; --card: {CARD}; --border: {BORDER};
        --blue: {BLUE}; --purple: {PURPLE}; --orange: {ORANGE};
        --green: {GREEN}; --white: {WHITE}; --muted: {MUTED};
    }}
    .stApp {{
        background: {BG};
        color: {WHITE};
        font-family: -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{
        background: {BG2};
        border-right: 1px solid {BORDER};
    }}
    [data-testid="stSidebar"] * {{ color: {WHITE}; }}
    .block-container {{ padding-top: 2.2rem; max-width: 1400px; }}

    h1, h2, h3, h4 {{ color: {WHITE}; letter-spacing: -0.01em; }}
    p, li, span {{ color: {WHITE}; }}
    a {{ color: {BLUE}; }}

    /* Buttons */
    .stButton > button {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
        color: {WHITE};
        font-weight: 600;
        padding: 0.5rem 1rem;
        transition: all .15s ease;
    }}
    .stButton > button:hover {{
        border-color: {BLUE};
        background: {BG2};
        box-shadow: 0 4px 14px rgba(56,103,255,.15);
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {BLUE}, {PURPLE});
        border: none;
    }}

    /* Cards */
    div[data-testid="stVerticalBlockBorderWrapper"],
    .st-expander {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 16px;
    }}
    .st-expander {{ border-radius: 14px; }}
    [data-testid="stExpander"] details {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}

    /* Selects / inputs */
    .stSelectbox div[data-baseweb="select"] > div,
    .stTextInput input,
    .stNumberInput input,
    [data-baseweb="textarea"] {{
        background: {BG2};
        border: 1px solid {BORDER};
        border-radius: 12px;
        color: {WHITE};
    }}
    [data-baseweb="popover"] div {{
        background: {BG2};
        color: {WHITE};
    }}

    /* Radio pills */
    .stRadio div[role="radiogroup"] label {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: .4rem .8rem;
        margin: .15rem;
    }}
    .stRadio div[role="radiogroup"] label:hover {{ border-color: {BLUE}; }}

    /* Chat */
    [data-testid="stChatMessage"] {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: .6rem .9rem;
        margin-bottom: .5rem;
    }}

    /* Custom header bar */
    .aib-header {{
        position: sticky; top: 0; z-index: 1000;
        display: flex; align-items: center; justify-content: space-between;
        background: rgba(8,11,18,.92);
        backdrop-filter: blur(8px);
        border-bottom: 1px solid {BORDER};
        padding: .55rem 1rem; margin: -2.2rem -1.5rem 1rem -1.5rem;
    }}
    .aib-header-left {{ display: flex; align-items: center; gap: .8rem; }}
    .aib-logo {{
        width: 38px; height: 38px; border-radius: 12px;
        background: linear-gradient(135deg, {BLUE}, {PURPLE});
        display: flex; align-items: center; justify-content: center;
        font-size: 20px; font-weight: 800; color: #fff;
        box-shadow: 0 4px 16px rgba(124,77,255,.4);
    }}
    .aib-brand {{ display: flex; flex-direction: column; line-height: 1.15; }}
    .aib-brand b {{ font-size: 17px; color: {WHITE}; }}
    .aib-brand span {{ font-size: 11px; color: {MUTED}; }}
    .aib-header-right {{ display: flex; align-items: center; gap: .6rem; }}
    .aib-pill {{
        border: 1px solid {BORDER}; background: {CARD}; color: {WHITE};
        border-radius: 999px; padding: .35rem .85rem; font-size: 13px; cursor: pointer;
        transition: all .15s ease; white-space: nowrap;
    }}
    .aib-pill:hover {{ border-color: {BLUE}; color: {WHITE}; }}
    .aib-pill.icon {{ font-size: 16px; padding: .35rem .6rem; }}
    .aib-user {{ display: flex; align-items: center; gap: .5rem; }}
    .aib-avatar {{
        width: 32px; height: 32px; border-radius: 50%;
        background: linear-gradient(135deg, {ORANGE}, {PURPLE});
        display: flex; align-items: center; justify-content: center;
        font-size: 13px; font-weight: 700; color: #fff;
    }}
    .aib-user span {{ font-size: 13px; color: {WHITE}; }}

    /* Section header inside sidebar */
    .aib-section {{
        font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
        color: {MUTED}; margin: 1rem 0 .5rem; font-weight: 700;
    }}

    /* Empty state */
    .aib-empty {{ display: flex; flex-direction: column; align-items: center; justify-content: center;
        height: 60vh; text-align: center; gap: .3rem; }}
    .aib-empty-icon {{
        width: 96px; height: 96px; border-radius: 50%;
        background: {CARD}; border: 1px solid {BORDER};
        display: flex; align-items: center; justify-content: center;
        font-size: 44px; margin-bottom: .5rem;
        box-shadow: 0 10px 30px rgba(0,0,0,.4);
    }}
    .aib-empty h2 {{ font-size: 26px; margin: 0; }}
    .aib-empty p {{ color: {MUTED}; max-width: 420px; margin: 0; }}

    /* Badges */
    .aib-badge {{
        display: inline-flex; align-items: center; gap: .3rem;
        background: {CARD}; border: 1px solid {BORDER};
        color: {WHITE}; border-radius: 999px; padding: .25rem .7rem;
        font-size: 12px; margin-right: .4rem; font-weight: 600;
    }}
    .aib-badge.blue {{ border-color: {BLUE}; color: #a8c0ff; }}
    .aib-badge.purple {{ border-color: {PURPLE}; color: #d0c2ff; }}
    .aib-badge.orange {{ border-color: {ORANGE}; color: #ffd0a8; }}
    .aib-badge.green {{ border-color: {GREEN}; color: #a8ffd0; }}

    /* Action buttons (regenerate etc.) */
    .aib-action {{
        border: 1px solid {BORDER}; background: {CARD}; color: {WHITE};
        border-radius: 12px; padding: .45rem .9rem; font-size: 13px;
        display: inline-flex; align-items: center; gap: .4rem; cursor: pointer;
    }}
    .aib-action:hover {{ border-color: {ORANGE}; }}
    .aib-action.primary {{ border-color: transparent;
        background: linear-gradient(135deg, {BLUE}, {PURPLE}); }}

    /* Contents tool buttons */
    .aib-tool {{
        display: flex; align-items: center; gap: .6rem;
        background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
        color: {WHITE}; padding: .5rem .75rem; font-size: 13.5px; cursor: pointer;
        width: 100%; text-align: left; margin-bottom: .35rem; transition: all .15s ease;
    }}
    .aib-tool:hover {{ border-color: {BLUE}; background: {BG2}; }}
    .aib-tool.active {{ border-color: {BLUE};
        background: linear-gradient(135deg, rgba(56,103,255,.18), rgba(124,77,255,.12)); }}
    .aib-tool .ic {{ font-size: 15px; width: 22px; text-align: center; }}

    /* Topic page hero */
    .aib-breadcrumb {{ color: {MUTED}; font-size: 13px; margin-bottom: .2rem; }}
    .aib-breadcrumb b {{ color: {WHITE}; font-weight: 600; }}
    .aib-topic-title {{ font-size: 30px; font-weight: 800; margin: .2rem 0 .6rem; color: {WHITE}; }}
    .aib-obj-card {{
        background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px;
        padding: 1rem 1.2rem; margin-top: 1rem;
    }}
    .aib-obj-card li {{ margin-bottom: .35rem; color: {WHITE}; }}

    /* Flashcard */
    .aib-flashcard {{
        min-height: 220px; display: flex; align-items: center; justify-content: center;
        background: {BG2}; border: 1px solid {BORDER}; border-radius: 18px;
        font-size: 22px; padding: 2rem; text-align: center;
        transition: transform .3s ease; box-shadow: 0 8px 24px rgba(0,0,0,.35);
    }}
    .aib-flashcard.small {{ font-size: 16px; }}

    /* Progress bar */
    .stProgress > div > div > div {{ background: linear-gradient(90deg, {BLUE}, {PURPLE}); }}

    /* Mind map node */
    .mm-node {{
        display: flex; align-items: center; justify-content: center;
        border-radius: 14px; font-weight: 700; text-align: center;
    }}

    /* Floating AI button */
    .aib-fab {{
        position: fixed; bottom: 24px; right: 24px; z-index: 2000;
        width: 58px; height: 58px; border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #ff8a3d, {ORANGE});
        display: flex; align-items: center; justify-content: center;
        font-size: 26px; color: #fff; cursor: pointer;
        box-shadow: 0 8px 24px rgba(255,122,24,.45);
        border: none; transition: transform .2s ease;
    }}
    .aib-fab:hover {{ transform: scale(1.08); }}

    /* Skeleton shimmer */
    .aib-skeleton {{
        background: linear-gradient(90deg, {CARD} 25%, {BG2} 50%, {CARD} 75%);
        background-size: 200% 100%; border-radius: 12px;
        height: 14px; margin: .5rem 0; animation: aib-shimmer 1.4s infinite;
    }}
    @keyframes aib-shimmer {{ 0% {{ background-position: 200% 0; }} 100% {{ background-position: -200% 0; }} }}

    /* Count-up stat cards */
    .aib-stat {{
        background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px;
        padding: .8rem 1rem; text-align: center;
    }}
    .aib-stat b {{ font-size: 22px; color: {WHITE}; display: block; }}
    .aib-stat span {{ font-size: 12px; color: {MUTED}; }}

    @media (max-width: 768px) {{
        .block-container {{ padding-top: 1rem; }}
        .aib-pill:not(.icon) {{ display: none; }}
    }}
</style>
""",
        unsafe_allow_html=True,
    )


def render_header(lang, on_ticket=None):
    """Fixed top header as HTML. on_ticket is ignored (Streamlit has no JS callbacks);
    real interactive controls live in the sidebar instead."""
    left = f"""
        <div class="aib-header-left">
            <div class="aib-logo">AI</div>
            <div class="aib-brand"><b>{_('ai_books', lang)}</b><span>{_('tagline', lang)}</span></div>
        </div>"""
    right = f"""
        <div class="aib-header-right">
            <span class="aib-pill">&#128197; {_('raise_ticket', lang)}</span>
            <span class="aib-pill icon">&#128276;</span>
            <span class="aib-pill icon">&#9881;</span>
            <span class="aib-user"><span class="aib-avatar">AB</span><span>Anil Bk</span> <span style="color:{MUTED}">&#9660;</span></span>
        </div>"""
    st.markdown(f'<div class="aib-header">{left}{right}</div>', unsafe_allow_html=True)