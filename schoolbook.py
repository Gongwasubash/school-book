import os

import streamlit as st

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

from dotenv import load_dotenv

load_dotenv()

from textbook_indexer import scan_library, find_book, get_chapters, load_chapter, load_chapter_from_md


TEXTBOOK_ROOT = os.environ.get("TEXTBOOK_ROOT", r"E:\class  1 to 10 book\Nepal Textbooks Grade 1-10")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CLASS_NAMES = [f"Class {i}" for i in range(1, 11)]

QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "none")
QWEN_MODEL_NAME = os.environ.get("QWEN_MODEL_NAME", "Qwen/Qwen3.8-27B")


def get_llm(provider):
    if provider == "Qwen (free HF endpoint)":
        return ChatOpenAI(
            model=QWEN_MODEL_NAME,
            temperature=0.3,
            max_tokens=512,
            base_url=QWEN_BASE_URL,
            api_key=QWEN_API_KEY,
            model_kwargs={"reasoning_effort": "low"},
        )
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_tokens=512,
        api_key=os.environ.get("GROQ_API_KEY"),
    )


@st.cache_resource
def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@st.cache_data(show_spinner=False)
def cached_scan_library(root):
    return scan_library(root)


@st.cache_data(show_spinner=False)
def cached_get_chapters(path):
    return get_chapters(path)


CUSTOM_PROMPT_TEMPLATE = """You are a friendly, personal study assistant for school students in Nepal.
You explain topics in a natural, conversational tone as if you are teaching the student personally.
IMPORTANT: You must ALWAYS answer in the same language as the question. If the question is in
Nepali (Devanagari), answer in Nepali (नेपालीमा उत्तर देऊ). If the question is in English, answer
in English. Never switch to Hindi just because the text uses the Devanagari script.
You base your answers ONLY on the provided context from the student's selected textbook chapters,
but you do NOT just quote or copy the text — you explain it in your own words, give clear examples,
and keep it engaging and easy to understand. For mathematics and science, show clear step-by-step
reasoning. If the context does not contain the answer, say so honestly and suggest related topics
that ARE in the chapters, rather than guessing.

Context:
{context}

Question: {input}

Helpful, personal answer:"""


def build_store(book, selected_chapters):
    documents = []
    is_md = book["path"].lower().endswith(".md")
    for chapter in selected_chapters:
        if is_md:
            docs = load_chapter_from_md(book["path"], chapter, chapter_title=chapter.get("title"))
        else:
            docs = load_chapter(book["path"], chapter, chapter_title=chapter.get("title"))
        documents.extend(docs)
    if not documents:
        return None, 0
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(documents)
    if not chunks:
        return None, 0
    store = FAISS.from_documents(chunks, get_embedding_model())
    return store, len(chunks)


def format_selection(chapters):
    return "; ".join(f"{c['title']} (pp.{c['start'] + 1}-{c['end'] + 1})" for c in chapters)


def main():
    st.set_page_config(page_title="SchoolBook AI", layout="wide")
    st.title("SchoolBook AI - Class 1-10 Study Assistant")
    st.caption(f"Textbooks: `{TEXTBOOK_ROOT}`")

    if not os.path.isdir(TEXTBOOK_ROOT):
        st.error(f"Textbook folder not found: {TEXTBOOK_ROOT}. Set TEXTBOOK_ROOT in .env")
        st.stop()

    books = cached_scan_library(TEXTBOOK_ROOT)
    if not books:
        st.error("No PDF books found in the textbook folder.")
        st.stop()

    class_num = int(st.selectbox("Select Class", options=list(range(1, 11)), format_func=lambda c: f"Class {c}"))

    class_books = [b for b in books if b["class"] == class_num]
    if not class_books:
        st.warning(f"No books found for Class {class_num}.")
        st.stop()

    book_options = [f"{b['file']}  ({b['size'] / 1e6:.1f} MB)" for b in class_books]
    selected_label = st.selectbox("Select Subject (Book)", options=book_options)
    selected_book = class_books[book_options.index(selected_label)]

    chapters = cached_get_chapters(selected_book["path"])

    with st.sidebar:
        st.header("Knowledge Base")
        st.info(f"**{selected_book['file']}**  \n{len(chapters)} chapters detected")

        st.subheader("Select Chapters")
        select_all = st.checkbox("Select all chapters", value=False)
        if select_all:
            selected_titles = [c["title"] for c in chapters]
        else:
            selected_titles = st.multiselect(
                "Chapters", options=[c["title"] for c in chapters], default=None
            )

        selected_chapters = [c for c in chapters if c["title"] in selected_titles]

        build = st.button("Build Knowledge Base", disabled=not selected_chapters, type="primary")
        if build:
            with st.spinner(f"Building index from {len(selected_chapters)} chapter(s)..."):
                store, n_chunks = build_store(selected_book, selected_chapters)
            if store is None:
                st.error("No extractable text found in the selected chapters.")
            else:
                st.session_state.store = store
                st.session_state.selection = format_selection(selected_chapters)
                st.success(f"Index ready: {n_chunks} chunks")

        st.divider()
        if st.session_state.get("store") is not None:
            st.success(st.session_state["selection"])
        else:
            st.warning("No knowledge base yet. Select chapters and build.")

        st.divider()
        st.header("LLM Provider")
        provider = st.selectbox(
            "Choose the model backend",
            options=["Groq (openai/gpt-oss-20b)", "Qwen (free HF endpoint)"],
        )

    if "store" not in st.session_state:
        st.session_state.store = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("sources"):
                with st.expander("Sources"):
                    for src in message["sources"]:
                        st.write(src)

    prompt = st.chat_input("Ask a question about the selected chapters...")

    if prompt:
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        try:
            store = st.session_state.get("store")
            if store is None:
                st.error("No knowledge base yet. Select chapters and click 'Build Knowledge Base'.")
            else:
                llm = get_llm(provider)
                prompt_template = PromptTemplate(
                    template=CUSTOM_PROMPT_TEMPLATE, input_variables=["context", "input"]
                )
                combine_docs_chain = create_stuff_documents_chain(llm, prompt_template)
                rag_chain = create_retrieval_chain(
                    store.as_retriever(search_kwargs={"k": 5}),
                    combine_docs_chain,
                )

                response = rag_chain.invoke({"input": prompt})
                result = response["answer"]
                sources = []
                for i, doc in enumerate(response.get("context", []), 1):
                    meta = doc.metadata
                    src = os.path.basename(meta.get("source", "unknown"))
                    page = meta.get("page", 0) + 1
                    chapter = meta.get("chapter", "?")
                    sources.append(f"[{i}] {src} | Ch: {chapter} | p.{page}: {doc.page_content[:150]}...")

                with st.chat_message("assistant"):
                    st.markdown(result)
                    with st.expander("Sources"):
                        for s in sources:
                            st.write(s)
                st.session_state.messages.append(
                    {"role": "assistant", "content": result, "sources": sources}
                )

        except Exception as e:
            st.error(f"Error: {str(e)}")


if __name__ == "__main__":
    main()