"""Technical Manuals & Knowledge Base Management UI view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import ServiceContainer


def render_knowledge_view(services: ServiceContainer) -> None:
    st.subheader("📚 Industrial Manuals & Knowledge Base")

    st.markdown(
        "Upload equipment manufacturer manuals, ISO vibration guidelines, or schematics in PDF format. "
        "The system extracts text with **PyMuPDF**, chunks documents, and indexes them with **scikit-learn TF-IDF** "
        "for instant grounded diagnostic retrieval."
    )

    # Ingestion Card
    with st.container(border=True):
        st.markdown("#### 📤 Upload Maintenance Manual (PDF)")
        uploaded_file = st.file_uploader("Select PDF Document:", type=["pdf"])

        if uploaded_file is not None:
            if st.button("Process & Index Manual with PyMuPDF", type="primary"):
                with st.spinner("Extracting text and building vector representations..."):
                    pdf_bytes = uploaded_file.read()
                    count = services.assistant.ingest_pdf_file(pdf_bytes, uploaded_file.name)
                    st.success(f"Successfully processed `{uploaded_file.name}` and indexed {count} text chunks!")
                    st.rerun()

    st.divider()

    # Indexed Documents Catalog
    st.markdown("### 🗃️ Currently Indexed Documentation")
    docs = services.db.list_indexed_documents()

    if docs:
        st.dataframe(pd.DataFrame(docs), use_container_width=True, hide_index=True)
    else:
        st.warning("No manuals currently indexed. Click below to load standard equipment manual.")
        if st.button("Re-bootstrap Default Motor Troubleshooting Manual"):
            services.assistant._bootstrap_default_manual()
            st.rerun()

    st.divider()

    # Search Tester
    st.markdown("### 🔎 Interactive TF-IDF Manual Search Tester")
    search_q = st.text_input("Enter search phrase (e.g. 'bearing replacement', 'cavitation', 'ISO 10816'):", "ISO 10816 Zone D vibration limit")

    if st.button("Search Knowledge Index"):
        results = services.assistant.tfidf_index.search(search_q, top_k=3)
        if results:
            for idx, r in enumerate(results, 1):
                st.markdown(f"**Result {idx}** | Doc: `{r.get('doc_name')}` | Page: `{r.get('metadata', {}).get('page')}` | Score: `{r.get('score')}`")
                st.info(r.get("content"))
        else:
            st.info("No matching passages found.")
