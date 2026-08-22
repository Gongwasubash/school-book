"""Reusable learning-resource viewer components (rendered inside Streamlit)."""

from __future__ import annotations

import streamlit as st
from .theme import _, ORANGE, BLUE, PURPLE, GREEN, MUTED, CARD, BORDER
from . import progress


def _nav(key, total, lang, wrap=True):
    """Previous / Next navigation row."""
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button(_("previous", lang), key=f"prev_{key}"):
            idx = st.session_state.get(key, 0) - 1
            if idx < 0 and wrap:
                idx = total - 1
            st.session_state[key] = max(0, idx) if not wrap else idx % total
    with c2:
        idx = st.session_state.get(key, 0)
        st.markdown(
            f"<div style='text-align:center;color:{MUTED};font-size:14px'>{idx + 1} / {total}</div>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button(_("next", lang), key=f"next_{key}"):
            idx = st.session_state.get(key, 0) + 1
            if idx >= total and wrap:
                idx = 0
            st.session_state[key] = idx


def _progress(cur, total):
    st.progress(min(cur + 1, total) / total)


def render_flashcards(data, lang, key_prefix):
    cards = data.get("cards", [])
    if not cards:
        st.info("No flashcards yet. Press AI Generate.")
        return
    key = f"{key_prefix}_fc"
    idx = st.session_state.setdefault(key, 0) % len(cards)
    flipped = st.session_state.setdefault(f"{key}_flip", False)
    _progress(idx, len(cards))

    st.markdown(
        f"""<div class="aib-flashcard{' small' if not flipped else ''}">
            {cards[idx]['back'] if flipped else cards[idx]['front']}
        </div>""",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        if st.button(_("flip_card", lang), key=f"{key}_flipbtn", use_container_width=True):
            st.session_state[f"{key}_flip"] = not flipped
    _nav(key, len(cards), lang)

    cur = st.session_state.get(key, 0) % len(cards)
    seen = set(st.session_state.get(f"{key}_seen", []))
    seen.add(cur)
    st.session_state[f"{key}_seen"] = seen
    if len(seen) >= len(cards) and not st.session_state.get(f"{key}_deck_recorded"):
        progress.record_cards_completed(len(cards))
        st.session_state[f"{key}_deck_recorded"] = True
        st.success(f"✅ {_('flashcards_completed', lang)}: {len(cards)}")


def render_mcq(data, lang, key_prefix):
    questions = data.get("questions", [])
    if not questions:
        st.info("No MCQs yet. Press AI Generate.")
        return
    key = f"{key_prefix}_mcq"
    idx = st.session_state.setdefault(key, 0) % len(questions)
    answers = st.session_state.setdefault(f"{key}_ans", [None] * len(questions))
    scores = st.session_state.setdefault(f"{key}_score", 0)
    done = st.session_state.setdefault(f"{key}_done", False)
    q = questions[idx]

    st.markdown(
        f"<div style='color:{MUTED};font-size:13px'>Question {idx + 1} of {len(questions)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div style='font-size:19px;font-weight:700;margin:.4rem 0'>{q['q']}</div>", unsafe_allow_html=True)

    chosen = answers[idx]
    for opt in q["options"]:
        label = opt
        if chosen is not None:
            if opt == q["answer"]:
                label = f"✅ {opt}"
            elif opt == chosen:
                label = f"❌ {opt}"
        if st.button(label, key=f"{key}_opt_{idx}_{opt}", use_container_width=True, disabled=chosen is not None):
            st.session_state[f"{key}_ans"][idx] = opt
            correct = opt == q["answer"]
            if correct:
                st.session_state[f"{key}_score"] += 1
            progress.record_mcq_answered(correct)
            st.rerun()

    if chosen is not None:
        color = GREEN if chosen == q["answer"] else ORANGE
        st.markdown(
            f"<div style='background:{CARD};border:1px solid {color};border-radius:12px;padding:.7rem .9rem;"
            f"color:#fff'><b>{'सही! Correct!' if chosen == q['answer'] else 'गलत! Wrong!'}</b><br>{q.get('explanation','')}</div>",
            unsafe_allow_html=True,
        )

    if chosen is not None:
        if idx < len(questions) - 1:
            if st.button(_("next", lang), key=f"{key}_n", type="primary"):
                st.session_state[key] = idx + 1
                st.rerun()
        else:
            if st.button("Show Score", key=f"{key}_finish", type="primary"):
                progress.record_quiz(scores, len(questions))
                st.session_state[f"{key}_done"] = True
                st.rerun()

    if done:
        st.markdown("---")
        pct = int(scores / len(questions) * 100)
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(
                f"<div class='aib-stat'><b>{scores} / {len(questions)}</b><span>{_('your_score', lang)}</span></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div class='aib-stat'><b>{pct}%</b><span>Score</span></div>",
                unsafe_allow_html=True,
            )
        if st.button(_("try_again", lang), key=f"{key}_retry"):
            for k in [key, f"{key}_ans", f"{key}_score", f"{key}_done"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()


def render_vocabulary(data, lang, key_prefix):
    items = data.get("items", [])
    if not items:
        st.info("No vocabulary yet. Press AI Generate.")
        return
    key = f"{key_prefix}_voc"
    idx = st.session_state.setdefault(key, 0) % len(items)
    it = items[idx]
    st.markdown(
        f"""<div style="background:{CARD};border:1px solid {BORDER};border-radius:16px;padding:1.2rem">
            <div style="color:{MUTED};font-size:12px;letter-spacing:.1em;text-transform:uppercase">Term</div>
            <div style="font-size:24px;font-weight:800;margin:.2rem 0">{it['term']}</div>
            <div style="color:{MUTED};font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin-top:.8rem">Meaning</div>
            <div style="font-size:16px;margin:.2rem 0">{it['meaning']}</div>
            <div style="color:{MUTED};font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin-top:.8rem">Example</div>
            <div style="font-size:15px;font-style:italic;color:#cfd6e4;margin:.2rem 0">{it['example']}</div>
        </div>""",
        unsafe_allow_html=True,
    )
    _nav(key, len(items), lang)


def render_questions(data, lang, key_prefix):
    items = data.get("questions", [])
    st.markdown("### Questions")
    for i, it in enumerate(items, 1):
        with st.expander(f"Q{i}. {it['q']}", expanded=i == 1):
            st.markdown(it.get("a", ""))


def render_summary(data, lang, key_prefix):
    st.markdown("### Overview")
    st.markdown(f"<div style='background:{CARD};border:1px solid {BORDER};border-radius:14px;"
                f"padding:1rem;font-size:16px;line-height:1.6'>{data.get('overview','')}</div>", unsafe_allow_html=True)
    st.markdown("### Important Concepts")
    for c in data.get("concepts", []):
        st.markdown(f"- {c}")
    st.markdown("### Key Takeaways")
    cols = st.columns(len(data.get("takeaways", [1])))
    for col, t in zip(cols, data.get("takeaways", [])):
        with col:
            st.markdown(f"<div style='background:{CARD};border:1px solid {BORDER};border-radius:12px;"
                        f"padding:.8rem;font-size:13px;text-align:center'>{t}</div>", unsafe_allow_html=True)


def render_key_points(data, lang, key_prefix):
    points = data.get("points", [])
    st.markdown("### Key Points")
    for i, p in enumerate(points, 1):
        st.markdown(
            f"""<div style="display:flex;gap:.8rem;background:{CARD};border:1px solid {BORDER};
                border-radius:14px;padding:.9rem 1rem;margin-bottom:.5rem">
                <div style="font-size:22px;font-weight:800;color:{BLUE};min-width:40px">{i:02d}</div>
                <div style="font-size:15px;padding-top:.3rem">{p}</div></div>""",
            unsafe_allow_html=True,
        )


def render_key_terms(data, lang, key_prefix):
    terms = data.get("terms", [])
    st.markdown("### Key Terms")
    for t in terms:
        st.markdown(f"**{t['term']}** — {t['definition']}")


def render_real_life(data, lang, key_prefix):
    st.markdown("### Real-Life Examples")
    cols = st.columns(2)
    for i, ex in enumerate(data.get("examples", [])):
        with cols[i % 2]:
            st.markdown(
                f"""<div style="background:{CARD};border:1px solid {BORDER};border-radius:16px;
                    padding:1rem;margin-bottom:.6rem">
                    <div style="font-size:15px;font-weight:700">🌍 Example {i + 1} — {ex['title']}</div>
                    <div style="font-size:13.5px;color:#cfd6e4;margin-top:.4rem">{ex['description']}</div></div>""",
                unsafe_allow_html=True,
            )


def render_fun_facts(data, lang, key_prefix):
    st.markdown("### ⚡ Did You Know?")
    for i, f in enumerate(data.get("facts", [])):
        st.markdown(
            f"""<div style="background:linear-gradient(135deg,rgba(255,122,24,.12),rgba(255,122,24,.04));
                border:1px solid {ORANGE};border-radius:16px;padding:1rem;margin-bottom:.6rem;
                font-size:15px">⚡ {f}</div>""",
            unsafe_allow_html=True,
        )


def render_group_activity(data, lang, key_prefix):
    act = data.get("activity", {})
    st.markdown("### Group Activity")
    st.markdown(f"**{act.get('title','')}**")
    st.markdown(act.get("description", ""))
    for i, s in enumerate(act.get("steps", []), 1):
        st.markdown(f"{i}. {s}")
    if st.button("Start Activity", type="primary", key=f"{key_prefix}_ga"):
        st.session_state[f"{key_prefix}_ga_on"] = True
        progress.record_project(act.get("title", "Group Activity"))
        st.rerun()
    if st.session_state.get(f"{key_prefix}_ga_on"):
        st.success("Activity started! Discuss in your group and share your findings.")


def render_project(data, lang, key_prefix):
    proj = data.get("project", {})
    st.markdown("### Project Work")
    st.markdown(
        f"""<div style="background:{CARD};border:1px solid {BORDER};border-radius:16px;padding:1.2rem">
            <div style="color:{MUTED};font-size:12px;text-transform:uppercase">Project</div>
            <div style="font-size:20px;font-weight:800">{proj.get('title','')}</div>
            <div style="color:{MUTED};font-size:12px;text-transform:uppercase;margin-top:.8rem">Objective</div>
            <div style="margin:.2rem 0">{proj.get('objective','')}</div>
            <div style="color:{MUTED};font-size:12px;text-transform:uppercase;margin-top:.8rem">Activities</div>
        </div>""",
        unsafe_allow_html=True,
    )
    for a in proj.get("activities", []):
        st.markdown(f"• {a}")
    if st.button("Start Project", type="primary", key=f"{key_prefix}_proj"):
        st.session_state[f"{key_prefix}_proj_on"] = True
        progress.record_project(proj.get("title", "Project"))
        st.rerun()
    if st.session_state.get(f"{key_prefix}_proj_on"):
        st.success("Project started! Track your activities and prepare your report.")


def render_slides(data, lang, key_prefix):
    slides = data.get("slides", [])
    if not slides:
        st.info("No slides yet.")
        return
    key = f"{key_prefix}_slides"
    idx = st.session_state.setdefault(key, 0) % len(slides)
    s = slides[idx]
    st.markdown(
        f"""<div style="background:linear-gradient(160deg,#121a2e,#151927);border:1px solid {BORDER};
            border-radius:18px;padding:2.4rem 2rem;min-height:300px;text-align:center;position:relative">
            <div style="color:{MUTED};font-size:12px;letter-spacing:.12em;text-transform:uppercase">{s.get('subtitle','')}</div>
            <div style="font-size:28px;font-weight:800;margin:.8rem 0">{s.get('title','')}</div>
            <div style="display:flex;flex-direction:column;gap:.3rem;max-width:560px;margin:1rem auto;text-align:left">
        """,
        unsafe_allow_html=True,
    )
    for b in s.get("bullets", []):
        st.markdown(f"<div style='font-size:15px;padding:.15rem 0'>• {b}</div>", unsafe_allow_html=True)
    st.markdown(f"</div><div style='color:#fff;font-size:14px'>{idx + 1} / {len(slides)}</div></div>", unsafe_allow_html=True)
    _nav(key, len(slides), lang)


def render_videos(data, lang, key_prefix):
    st.markdown("### Videos")
    for v in data.get("videos", []):
        st.markdown(
            f"""<div style="display:flex;gap:.8rem;background:{CARD};border:1px solid {BORDER};
                border-radius:14px;padding:.9rem 1rem;margin-bottom:.5rem;align-items:center">
                <div style="font-size:26px">▶️</div>
                <div><div style="font-weight:700;font-size:14.5px">{v['title']}</div>
                <div style="color:{MUTED};font-size:13px">{v['desc']}</div></div></div>""",
            unsafe_allow_html=True,
        )


def render_points(data, lang, key_prefix):
    st.markdown("### ★ Points to Remember")
    for i, p in enumerate(data.get("points", []), 1):
        st.markdown(f"{i}. {p}")


def render_mind_map(data, lang, key_prefix):
    center = data.get("center", "")
    branches = data.get("branches", [])
    st.markdown("### Mind Map")
    n = len(branches)
    colors = [BLUE, PURPLE, ORANGE, GREEN, BLUE, PURPLE]
    rows_html = []
    cols = 3
    rows_html.append(
        f"<div style='display:flex;justify-content:center;margin:1rem 0'>"
        f"<div class='mm-node' style='background:linear-gradient(135deg,{BLUE},{PURPLE});color:#fff;"
        f"font-size:20px;padding:1rem 1.6rem'>{center}</div></div>"
    )
    for start in range(0, n, cols):
        chunk = branches[start:start + cols]
        cells = ""
        for j, br in enumerate(chunk):
            col = colors[(start + j) % len(colors)]
            cells += (
                f"<div class='mm-node' style='background:{CARD};border:1px solid {col};"
                f"color:#fff;font-size:14px;padding:.6rem 1rem;min-width:120px'>{br}</div>"
            )
        rows_html.append(
            f"<div style='display:flex;justify-content:center;gap:.6rem;margin:.4rem 0'>{cells}</div>"
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)


def render_teacher(data, lang, key_prefix):
    for item in data.get("content", []):
        st.markdown(f"### {item['heading']}")
        st.markdown(item.get("text", ""))


def render_progress(data, lang, key_prefix):
    st.markdown(f"### {_('overall_progress', lang)}")
    st.progress(data.get("overall", 0) / 100)
    st.caption(f"{data.get('overall', 0)}%")

    stats = [
        (_("topics_viewed", lang), data.get("topics_viewed", 0), BLUE),
        (_("flashcards_completed", lang), data.get("flashcards_completed", 0), GREEN),
        (_("mcqs_completed", lang), data.get("mcqs_completed", 0), PURPLE),
        (_("quiz_scores", lang), f"{data.get('quiz_avg', 0)}%", ORANGE),
        (_("projects", lang), data.get("projects", 0), BLUE),
        (_("learning_streak", lang), f"{data.get('streak', 0)} {_('days', lang)}", GREEN),
    ]
    cols = st.columns(3)
    for i, (label, value, color) in enumerate(stats):
        with cols[i % 3]:
            st.markdown(
                f"""<div style="background:{CARD};border:1px solid {BORDER};border-left:3px solid {color};
                    border-radius:14px;padding:1rem;text-align:center;margin-bottom:.6rem">
                    <div style="font-size:26px;font-weight:800;color:{color}">{value}</div>
                    <div style="font-size:12.5px;color:{MUTED}">{label}</div></div>""",
                unsafe_allow_html=True,
            )

    st.caption(f"{_('activity_days', lang)}: {data.get('activity_days', 0)}")

    if data.get("insight"):
        st.markdown(
            f"""<div style="background:linear-gradient(135deg,rgba(56,103,255,.14),rgba(124,77,255,.10));
                border:1px solid {BLUE};border-radius:16px;padding:1rem 1.2rem;margin-top:.8rem">
                <div style="color:{MUTED};font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:.3rem">
                ✦ {_('ai_insight', lang)}</div>
                <div style="font-size:15px;line-height:1.6">{data['insight']}</div></div>""",
            unsafe_allow_html=True,
        )

    if st.button(_("reset_progress", lang), key=f"{key_prefix}_reset"):
        progress.reset_progress()
        st.rerun()


VIEWERS = {
    "Slides": render_slides,
    "MCQ": render_mcq,
    "Vocabulary": render_vocabulary,
    "Flashcards": render_flashcards,
    "Questions": render_questions,
    "Videos": render_videos,
    "Key Points": render_key_points,
    "Key Terms": render_key_terms,
    "Real-Life Examples": render_real_life,
    "Fun Facts": render_fun_facts,
    "Group Activity": render_group_activity,
    "Summary": render_summary,
    "Project Work": render_project,
    "Mind Map": render_mind_map,
    "Points to Remember": render_points,
    "Progress": render_progress,
}

for _t in ("Lesson Plan", "Teaching Notes", "Classroom Activity", "Assignment",
           "Quiz", "Discussion Questions", "Assessment Rubric"):
    VIEWERS[_t] = render_teacher