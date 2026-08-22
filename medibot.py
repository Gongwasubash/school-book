import os

import streamlit as st

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain import hub
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

from dotenv import load_dotenv
load_dotenv()

from nepali_font_loader import load_pdf_documents


DB_FAISS_PATH = "vectorstore/db_faiss"
DATA_PATH = "data/"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "none")
QWEN_MODEL_NAME = os.environ.get("QWEN_MODEL_NAME", "Qwen/Qwen3.8-27B")


def get_llm(provider):
    if provider == "Qwen (free HF endpoint)":
        return ChatOpenAI(
            model=QWEN_MODEL_NAME,
            temperature=0.5,
            max_tokens=512,
            base_url=QWEN_BASE_URL,
            api_key=QWEN_API_KEY,
            model_kwargs={"reasoning_effort": "low"},
        )
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.5,
        max_tokens=512,
        api_key=os.environ.get("GROQ_API_KEY"),
    )


@st.cache_resource
def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def index_exists():
    return os.path.exists(os.path.join(DB_FAISS_PATH, "index.faiss"))


def load_vectorstore():
    if index_exists():
        return FAISS.load_local(DB_FAISS_PATH, get_embedding_model(), allow_dangerous_deserialization=True)
    return None


def get_vectorstore():
    if "db" not in st.session_state:
        st.session_state.db = load_vectorstore()
    return st.session_state.db


def set_custom_prompt(custom_prompt_template):
    prompt = PromptTemplate(template=custom_prompt_template, input_variables=["context", "question"])
    return prompt


CUSTOM_PROMPT_TEMPLATE = """You are a friendly, personal study assistant like Google NotebookLM.
You explain topics in a natural, conversational tone as if you are teaching the user personally.
IMPORTANT: You must ALWAYS answer in the same language as the question. If the question is in
Nepali (Devanagari), answer in Nepali (नेपालीमा उत्तर देऊ). If the question is in English, answer
in English. Never switch to Hindi just because the text uses the Devanagari script.
You base your answers ONLY on the provided context from the user's uploaded books, but you do NOT
just quote or copy the text — you explain it in your own words, give clear examples, and keep it
engaging and easy to understand.

If the context does not contain the answer, say so honestly and suggest related topics that ARE in
the books, rather than guessing.

Context:
{context}

Question: {input}

Helpful, personal answer:"""


def save_uploaded_files(uploaded_files):
    saved_paths = []
    for uf in uploaded_files:
        path = os.path.join(DATA_PATH, uf.name)
        with open(path, "wb") as f:
            f.write(uf.getbuffer())
        saved_paths.append(path)
    return saved_paths


def load_document(path):
    lower = path.lower()
    if lower.endswith(".pdf"):
        return load_pdf_documents(path)
    if lower.endswith(".txt"):
        return TextLoader(path, encoding="utf-8", autodetect_encoding=True).load()
    return []


def create_chunks(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return text_splitter.split_documents(documents)


def add_documents_to_store(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    chunks = create_chunks(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return 0
    db = get_vectorstore()
    if db is None:
        db = FAISS.from_documents(chunks, get_embedding_model())
    else:
        db.add_documents(chunks)
    os.makedirs(DB_FAISS_PATH, exist_ok=True)
    db.save_local(DB_FAISS_PATH)
    st.session_state.db = db
    return len(chunks)


def main():
    st.set_page_config(page_title="MediBot", layout="wide")
    st.title("MediBot - Medical RAG Assistant")

    with st.sidebar:
        st.header("Knowledge Base Management")
        chunk_size = st.number_input(
            "Chunk size (characters)", min_value=100, max_value=5000, value=CHUNK_SIZE, step=100
        )
        chunk_overlap = st.number_input(
            "Chunk overlap (characters)", min_value=0, max_value=1000, value=CHUNK_OVERLAP, step=50
        )
        if chunk_overlap >= chunk_size:
            st.warning("Overlap should be smaller than chunk size.")
        uploaded_files = st.file_uploader(
            "Upload PDF or TXT books (multiple files allowed)",
            type=["pdf", "txt"],
            accept_multiple_files=True,
        )
        process = st.button("Process & Add to Knowledge Base", disabled=not uploaded_files)

        if process and uploaded_files:
            with st.spinner("Processing books..."):
                saved_paths = save_uploaded_files(uploaded_files)
                documents = []
                errors = []
                for path in saved_paths:
                    try:
                        docs = load_document(path)
                        if not docs:
                            errors.append(f"{os.path.basename(path)}: no extractable text (scanned/image PDF?)")
                        documents.extend(docs)
                    except Exception as e:
                        errors.append(f"{os.path.basename(path)}: {e}")
                total_chunks = add_documents_to_store(
                    documents, chunk_size=int(chunk_size), chunk_overlap=int(chunk_overlap)
                )
            if documents:
                st.success(
                    f"Added {len(documents)} pages from {len(saved_paths)} file(s) "
                    f"as {total_chunks} chunks."
                )
            else:
                st.error("No text could be extracted from the uploaded file(s).")
            if errors:
                st.warning("Some files failed: " + "; ".join(errors))

        st.divider()
        db = get_vectorstore()
        if db is not None:
            st.info(f"Index ready: {db.index.ntotal} chunks loaded")
        else:
            st.warning("No knowledge base yet. Upload books to get started.")

        st.divider()
        st.header("LLM Provider")
        provider = st.selectbox(
            "Choose the model backend",
            options=["Qwen (free HF endpoint)", "Groq (openai/gpt-oss-20b)"],
        )

    if 'messages' not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            st.markdown(message['content'])
            if message['role'] == 'assistant' and message.get('sources'):
                with st.expander("Sources"):
                    for src in message['sources']:
                        st.write(src)

    prompt = st.chat_input("Ask a question about your medical books...")

    if prompt:
        st.chat_message('user').markdown(prompt)
        st.session_state.messages.append({'role': 'user', 'content': prompt})

        try:
            vectorstore = get_vectorstore()
            if vectorstore is None:
                st.error("No knowledge base found. Upload books first.")
            else:
                llm = get_llm(provider)

                retrieval_qa_chat_prompt = set_custom_prompt(CUSTOM_PROMPT_TEMPLATE)
                combine_docs_chain = create_stuff_documents_chain(llm, retrieval_qa_chat_prompt)
                rag_chain = create_retrieval_chain(
                    vectorstore.as_retriever(search_kwargs={'k': 3}),
                    combine_docs_chain,
                )

                response = rag_chain.invoke({'input': prompt})
                result = response["answer"]
                sources = []
                for i, doc in enumerate(response.get("context", []), 1):
                    source = doc.metadata.get("source", "unknown")
                    sources.append(f"[{i}] {os.path.basename(source)}: {doc.page_content[:150]}...")

                with st.chat_message('assistant'):
                    st.markdown(result)
                    with st.expander("Sources"):
                        for s in sources:
                            st.write(s)
                st.session_state.messages.append({'role': 'assistant', 'content': result, 'sources': sources})

        except Exception as e:
            st.error(f"Error: {str(e)}")


if __name__ == "__main__":
    main()