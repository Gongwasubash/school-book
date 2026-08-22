import os
import sys

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from dotenv import load_dotenv
load_dotenv()

from nepali_font_loader import load_pdf_documents


DB_FAISS_PATH = "vectorstore/db_faiss"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SUPPORTED = (".pdf", ".txt")


def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def find_documents(folder):
    paths = []
    for root, dirs, files in os.walk(folder):
        for name in sorted(files):
            if name.lower().endswith(SUPPORTED):
                paths.append(os.path.join(root, name))
    return paths


def load_document(path):
    lower = path.lower()
    if lower.endswith(".pdf"):
        return load_pdf_documents(path)
    if lower.endswith(".txt"):
        return TextLoader(path, encoding="utf-8", autodetect_encoding=True).load()
    return []


def main(folder):
    embedding_model = get_embedding_model()
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    if os.path.exists(os.path.join(DB_FAISS_PATH, "index.faiss")):
        db = FAISS.load_local(DB_FAISS_PATH, embedding_model, allow_dangerous_deserialization=True)
        print(f"Loaded existing store: {db.index.ntotal} chunks")
    else:
        db = None

    paths = find_documents(folder)
    print(f"Found {len(paths)} files")

    for path in paths:
        name = os.path.basename(path)
        try:
            docs = load_document(path)
            if not docs:
                print(f"  SKIP {name}: no extractable text (scanned/image PDF?)")
                continue
            chunks = splitter.split_documents(docs)
            if not chunks:
                print(f"  SKIP {name}: no chunks produced")
                continue
            if db is None:
                db = FAISS.from_documents(chunks, embedding_model)
            else:
                db.add_documents(chunks)
            os.makedirs(DB_FAISS_PATH, exist_ok=True)
            db.save_local(DB_FAISS_PATH)
            print(f"  OK   {name}: {len(docs)} pages -> {len(chunks)} chunks (saved, total {db.index.ntotal})")
        except Exception as e:
            print(f"  FAIL {name}: {e}")

    if db is None:
        print("No documents were ingested.")
        return

    os.makedirs(DB_FAISS_PATH, exist_ok=True)
    db.save_local(DB_FAISS_PATH)
    print(f"Saved store with {db.index.ntotal} chunks total.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_folder.py <folder>")
        sys.exit(1)
    main(sys.argv[1])