"""AI Books - AI Learning Portal (Streamlit) backed by the real textbook RAG pipeline.

  native sidebar = LEFT: class -> subject (book) -> chapters -> Build KB + LLM provider
  left column    = RIGHT: learning-tools Contents panel
  main column    = topic content (LLM-generated from the real chapter text) + RAG chat
"""

from __future__ import annotations

import os
import sys
import time

import streamlit as st

from dotenv import load_dotenv

load_dotenv()

try:
    from .theme import (
        apply_theme, render_header, _, RESOURCES, RESOURCE_TYPES, TEACHER_RESOURCES,
        BLUE, MUTED,
    )
    from . import rag
    from . import progress as progress_mod
    from .viewers import VIEWERS
except ImportError:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from aibooks.theme import (
        apply_theme, render_header, _, RESOURCES, RESOURCE_TYPES, TEACHER_RESOURCES,
        BLUE, MUTED,
    )
    from aibooks import rag
    from aibooks import progress as progress_mod
    from aibooks.viewers import VIEWERS


APP_TITLE = "AI Books"
TEXTBOOK_ROOT = rag.TEXTBOOK_ROOT


def init_state():
    if "lang" not in st.session_state:
        st.session_state.lang = "en"
    if "resource" not in st.session_state:
        st.session_state.resource = "Summary"
    if "mode" not in st.session_state:
        st.session_state.mode = "student"  # student | teacher
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "ai_open" not in st.session_state:
        st.session_state.ai_open = False
    if "store" not in st.session_state:
        st.session_state.store = None
    if "store_label" not in st.session_state:
        st.session_state.store_label = None
    if "store_chunks" not in st.session_state:
        st.session_state.store_chunks = 0
    if "store_fp" not in st.session_state:
        st.session_state.store_fp = ""
    if "resource_cache" not in st.session_state:
        st.session_state.resource_cache = {}
    if "provider" not in st.session_state:
        st.session_state.provider = rag.PROVIDERS[0]
    if "selected_class" not in st.session_state:
        st.session_state.selected_class = 1


def class_sidebar():
    """LEFT panel = native Streamlit sidebar with real textbook navigation."""
    lang = st.session_state.lang
    books = rag.cached_scan_library(TEXTBOOK_ROOT)
    classes = rag.available_classes(books)

    with st.sidebar:
        st.markdown(f"<div class='aib-section'>{_('classes', lang)}</div>", unsafe_allow_html=True)
        if not classes:
            st.error(_("no_books", lang))
            st.stop()

        sel_class = st.selectbox(
            _("classes", lang), options=classes, index=0,
            format_func=lambda c: f"Class {c}", key="classbox",
        )
        st.session_state.selected_class = sel_class

        class_books = [b for b in books if b["class"] == sel_class]
        book_labels = [f"{b['file']} ({b['size'] / 1e6:.1f} MB)" for b in class_books]
        sel_label = st.selectbox(_("subjects", lang), options=book_labels, key="bookbox")
        book = class_books[book_labels.index(sel_label)]

        chapters = rag.cached_get_chapters(book["path"])
        st.caption(f"{len(chapters)} {_('chapters', lang).lower()}")

        sel_all = st.checkbox(_("select_all", lang), value=False, key="sel_all")
        if sel_all:
            chosen = list(chapters)
        else:
            titles = st.multiselect(
                _("chapters", lang),
                options=[c["title"] for c in chapters],
                default=None,
                placeholder=_("select_chapters_hint", lang),
            )
            chosen = [c for c in chapters if c["title"] in titles]

        if st.button(_("build_kb", lang), disabled=not chosen, use_container_width=True,
                     type="primary"):
            with st.spinner(f"{_('generating_resource', lang)} ({len(chosen)} chapters)..."):
                store, n = rag.build_store(book, chosen)
            if store is None:
                st.error(_("no_kb", lang))
            else:
                st.session_state.store = store
                st.session_state.store_label = rag.format_selection(book, chosen)
                st.session_state.store_chunks = n
                st.session_state.store_fp = f"c{sel_class}_{abs(hash(book['path']))}_{abs(hash(tuple(c['title'] for c in chosen)))}"
                st.session_state.resource_cache = {}
                st.success(f"{_('index_ready', lang)}: {n} {_('chunks', lang)}")

        st.divider()
        if st.session_state.get("store") is not None:
            st.success(st.session_state["store_label"])
            st.caption(f"{st.session_state['store_chunks']} {_('chunks', lang)}")
        else:
            st.info(_("no_store_hint", lang))

        st.divider()
        provider = st.radio(_("llm_provider", lang), options=rag.PROVIDERS,
                            index=rag.PROVIDERS.index(st.session_state.provider))
        st.session_state.provider = provider

        lang = st.selectbox("🌐 Language", ["English", "नेपाली"],
                            index=0 if st.session_state.lang == "en" else 1, key="langbox")
        st.session_state.lang = "ne" if lang == "नेपाली" else "en"


def tools_sidebar():
    """RIGHT panel = learning tools, rendered as the first (narrow) column."""
    lang = st.session_state.lang
    with st.container():
        st.markdown(f"<div class='aib-section'>{_('contents', lang)}</div>", unsafe_allow_html=True)

        mode = st.session_state.mode
        c1, c2 = st.columns(2)
        with c1:
            if st.button(_("student_resources", lang), key="mode_stu",
                         use_container_width=True,
                         type="primary" if mode == "student" else "secondary"):
                st.session_state.mode = "student"
                st.rerun()
        with c2:
            if st.button(_("teacher_resources", lang), key="mode_tea",
                         use_container_width=True,
                         type="primary" if mode == "teacher" else "secondary"):
                st.session_state.mode = "teacher"
                st.rerun()

        pool = TEACHER_RESOURCES if mode == "teacher" else RESOURCE_TYPES
        icons = {r[0]: r[1] for r in RESOURCES}
        for rt in pool:
            active = st.session_state.resource == rt
            ic = icons.get(rt, "▣")
            if st.button(f"{ic} {rt}", key=f"tool_{rt}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.resource = rt
                st.rerun()


def _get_resource(resource_type):
    lang = st.session_state.lang
    store = st.session_state.store
    label = st.session_state.store_label or "Selected chapters"

    if resource_type in TEACHER_RESOURCES:
        return rag.teacher_resource(resource_type, label)

    if resource_type == "Progress":
        stats = progress_mod.get_progress()
        with st.spinner(_("generating_insight", lang)):
            stats["insight"] = rag.progress_insight(
                stats, st.session_state.provider, st.session_state.lang)
        return stats

    cached = st.session_state.resource_cache.get(resource_type)
    if cached is not None:
        return cached

    with st.spinner(f"{_('generating_resource', lang)} {resource_type}..."):
        data = rag.generate_resource(resource_type, store, label, st.session_state.provider)
    st.session_state.resource_cache[resource_type] = data
    return data


def topic_page():
    lang = st.session_state.lang
    cls = st.session_state.selected_class
    label = st.session_state.store_label
    mode = st.session_state.mode
    res = st.session_state.resource

    st.markdown(
        f"<div class='aib-breadcrumb'><b>Class {cls}</b> / "
        f"<b>{label.split(' — ')[0]}</b> / <span style='color:{BLUE}'>{res}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='aib-topic-title'>{label.split(' — ')[0]}</div>",
                unsafe_allow_html=True)

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        st.markdown(f"<span class='aib-badge blue'>🎓 Class {cls}</span>", unsafe_allow_html=True)
    with b2:
        st.markdown(f"<span class='aib-badge purple'>📖 {st.session_state.store_chunks} {_('chunks', lang)}</span>",
                    unsafe_allow_html=True)
    with b3:
        st.markdown(f"<span class='aib-badge orange'>{res}</span>", unsafe_allow_html=True)
    with b4:
        st.markdown(
            f"<span class='aib-badge green'>{'Teacher Resources' if mode == 'teacher' else _('ai_books', lang)}</span>",
            unsafe_allow_html=True,
        )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button(f"↻ {_('regenerate', lang)}", key="act_reg"):
            st.session_state.resource_cache = {}
            st.rerun()
    with c2:
        if st.button(f"✦ {_('ai_generate', lang)}", key="act_ai"):
            st.session_state.resource_cache = {}
            st.rerun()
    with c3:
        if st.button(f"◇ {_('resources', lang)}", key="act_res"):
            st.session_state.resource = "Summary"
            st.rerun()

    st.markdown("---")

    fp = st.session_state.store_fp
    topic_key = f"topic_rec_{fp}"
    if not st.session_state.get(topic_key):
        progress_mod.record_topic_viewed(f"{cls}|{fp}")
        st.session_state[topic_key] = True

    data = _get_resource(res)
    viewer = VIEWERS.get(res, VIEWERS["Summary"])
    viewer(data, lang, f"r_{res}_{st.session_state.store_fp}")


def empty_state():
    lang = st.session_state.lang
    st.markdown(
        f"""<div class="aib-empty">
            <div class="aib-empty-icon">📚</div>
            <h2>{_('select_a_topic', lang)}</h2>
            <p>{_('empty_nav', lang)}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def ai_chat():
    """RAG learning assistant: answers from the built knowledge base."""
    lang = st.session_state.lang
    store = st.session_state.store

    if st.button("🤖 " + _('ai_assistant', lang), key="fab", use_container_width=True):
        st.session_state.ai_open = not st.session_state.ai_open
        st.rerun()

    if not st.session_state.ai_open:
        return

    st.markdown(f"### {_('ai_assistant', lang)}")
    st.caption(_("ask_about", lang))

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant" and m.get("sources"):
                with st.expander(_("sources", lang)):
                    for s in m["sources"]:
                        st.write(s)

    q = st.chat_input(_("type_question", lang))
    if q:
        st.session_state.messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner(f"{_('generating_resource', lang)}..."):
                answer, sources = rag.chat_answer(
                    store, q, st.session_state.provider)
            st.markdown(answer)
            if sources:
                with st.expander(_("sources", lang)):
                    for s in sources:
                        st.write(s)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "sources": sources})


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    apply_theme()
    init_state()
    render_header(st.session_state.lang)

    class_sidebar()

    c_left, c_main = st.columns([0.28, 0.72], gap="medium")
    with c_left:
        tools_sidebar()
    with c_main:
        if st.session_state.get("store") is None:
            empty_state()
        else:
            topic_page()
            ai_chat()


if __name__ == "__main__":
    main()
