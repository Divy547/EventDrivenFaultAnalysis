"""Technical Manuals & Knowledge Base Management UI view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import ServiceContainer


def render_knowledge_view(services: ServiceContainer) -> None:
    st.subheader("📚 Industrial Manuals & Knowledge Base Pipeline")

    st.markdown(
        "Manage technical documentation using **PyMuPDF** text extraction and **scikit-learn TF-IDF** vector retrieval. "
        "Uploaded manuals are persisted in SQLite with chunk metadata and SHA256 integrity hashes, "
        "powering zero-hallucination diagnostic grounding."
    )

    # Ingestion & Upload Card
    with st.container(border=True):
        st.markdown("#### 📤 Upload Technical Manual (PDF)")
        uploaded_file = st.file_uploader("Select PDF Document (e.g. equipment manual, datasheet, ISO standard):", type=["pdf"])

        if uploaded_file is not None:
            col_up1, col_up2 = st.columns([2, 3])
            with col_up1:
                st.caption(f"File: `{uploaded_file.name}` ({len(uploaded_file.getvalue()) / 1024:.1f} KB)")
                if st.button("📥 Process, Chunk & Index with PyMuPDF", type="primary"):
                    with st.spinner("Extracting text, computing SHA256, and building TF-IDF representations..."):
                        pdf_bytes = uploaded_file.read()
                        meta, count = services.assistant.ingest_pdf_file(pdf_bytes, uploaded_file.name)
                        st.success(
                            f"Successfully indexed `{uploaded_file.name}`! "
                            f"Extracted {count} chunks across {meta['page_count']} pages."
                        )
                        st.rerun()

    st.divider()

    # Document Catalog with Deletion
    st.markdown("### 🗃️ Persisted Documentation & Metadata")
    docs = services.db.list_indexed_documents()

    if docs:
        for doc in docs:
            doc_name = doc["doc_name"]
            with st.container(border=True):
                col_info, col_del = st.columns([4, 1])
                with col_info:
                    st.markdown(f"#### 📄 `{doc_name}`")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.caption(f"**Pages:** {doc.get('page_count', 1)}")
                    with c2:
                        st.caption(f"**Indexed Chunks:** {doc.get('chunk_count', 0)}")
                    with c3:
                        size_kb = doc.get("file_size_bytes", 0) / 1024
                        st.caption(f"**Size:** {size_kb:.1f} KB")
                    with c4:
                        st.caption(f"**Indexed At:** {str(doc.get('indexed_at', ''))[:19]}")

                    sha = doc.get("sha256_hash", "")
                    if sha:
                        st.caption(f"SHA-256: `{sha[:24]}...`")

                with col_del:
                    st.write("")
                    if st.button("🗑️ Delete Manual", key=f"del_{doc_name}", type="secondary", use_container_width=True):
                        services.assistant.delete_document(doc_name)
                        st.warning(f"Deleted `{doc_name}` from SQLite and TF-IDF index.")
                        st.rerun()

                # View chunks expander
                with st.expander(f"🔍 Inspect Chunks for `{doc_name}`"):
                    chunks = services.db.get_chunks_for_document(doc_name)
                    for c in chunks:
                        st.markdown(f"**Chunk {c['chunk_index']} (Page {c['page_number']}):**")
                        st.text(c["content"])
                        st.divider()
    else:
        st.warning("No manuals currently indexed.")
        if st.button("📥 Re-bootstrap Default Industrial Troubleshooting Manual"):
            services.assistant._bootstrap_default_manual()
            st.rerun()

    st.divider()

    # Interactive TF-IDF Search Tester
    st.markdown("### 🔎 TF-IDF Semantic Retrieval Tester")
    st.caption("Test cosine similarity matching against the active TF-IDF manual vector space.")
    col_q, col_top = st.columns([4, 1])
    with col_q:
        search_q = st.text_input(
            "Search Query:",
            value="ISO 10816 Zone D critical vibration threshold"
        )
    with col_top:
        top_k = st.selectbox("Top K:", [1, 2, 3, 5], index=2)

    if st.button("🔍 Search Knowledge Base"):
        results = services.assistant.tfidf_index.search(search_q, top_k=top_k)
        if results:
            for idx, r in enumerate(results, 1):
                with st.container(border=True):
                    st.markdown(
                        f"**Citation {idx}** | Doc: `{r.get('doc_name')}` | "
                        f"Page: **{r.get('page', 1)}** | Similarity Score: **{r.get('score', 0):.4f}**"
                    )
                    st.info(r.get("content"))
        else:
            st.info("No matching passages met the minimum similarity threshold.")
