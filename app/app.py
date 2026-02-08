import io
import zipfile
import streamlit as st
import streamlit.components.v1 as components

from utils.styles import inject_custom_css, NASA_LOGO_URL
from utils.bigquery_client import search_patents
from utils.gemini_client import generate_summary, build_results_text
from utils.charts import create_assignee_chart, create_inventor_chart, create_cpc_chart
from utils.graph import build_network_html

st.set_page_config(
    page_title="NASA Patent Similarity Search",
    page_icon="https://www.nasa.gov/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

# ── Sidebar ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f"""
        <div style="text-align:center; padding: 16px 0 24px;">
            <img src="{NASA_LOGO_URL}" style="width:72px; margin-bottom:12px;" />
            <h2 style="margin:0; font-size:18px; font-weight:700; color:#0B3D91;">
                Technology Transfer Office
            </h2>
            <p style="margin:6px 0 0; font-size:11px; color:#5B616B; letter-spacing:1.5px; text-transform:uppercase;">
                Patent Similarity Search
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    with st.form("search_form"):
        patent_number = st.text_input(
            "Patent Number",
            placeholder="e.g. US-2007156035-A1",
            help="Enter a US patent publication number from the indexed database.",
        )
        top_k = st.slider(
            "Number of Results",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="How many similar patents to retrieve.",
        )
        submitted = st.form_submit_button(
            "Search",
            use_container_width=True,
        )

    if submitted and patent_number:
        st.session_state["patent_number"] = patent_number.strip()
        st.session_state["top_k"] = top_k

    st.markdown("---")

    st.markdown(
        """
        <div style="padding:8px 0;">
            <p style="font-size:11px; color:#5B616B; font-weight:600; margin:0 0 6px;">
                Graph Legend
            </p>
            <span class="legend-item"><span class="legend-dot" style="background:#105BD8;"></span> Similar</span>
            <span class="legend-item"><span class="legend-dot" style="background:#4773AA;"></span> Cites</span>
            <span class="legend-item"><span class="legend-dot" style="background:#FF9D1E;"></span> Parent</span>
            <span class="legend-item"><span class="legend-dot" style="background:#DD361C;"></span> Child</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Main Area ────────────────────────────────────────────────────────────

if "patent_number" not in st.session_state:
    st.markdown(
        f"""
        <div class="empty-state">
            <img src="{NASA_LOGO_URL}" class="empty-state-icon" />
            <h2>Search NASA's Patent Database</h2>
            <p>
                Enter a patent number in the sidebar to find semantically similar
                patents using AI-powered vector search across millions of US patents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ── Header banner ────────────────────────────────────────────────────────

pn = st.session_state["patent_number"]
tk = st.session_state["top_k"]

st.markdown(
    f"""
    <div class="header-banner">
        <img src="{NASA_LOGO_URL}" />
        <div>
            <h1>Patent Similarity Search</h1>
            <p>Searching for {pn} &middot; Top {tk} results</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Run search ───────────────────────────────────────────────────────────

with st.status("Analyzing patents...", expanded=True) as status:
    st.write("Searching patent database...")
    results_df = search_patents(pn, tk)

    if results_df.empty:
        status.update(label="No results found", state="error")
        st.error(f"Patent `{pn}` not found in the indexed database.")
        st.stop()

    query_patent = results_df.iloc[0]
    search_results = results_df.iloc[1:].copy()

    st.write("Generating AI summary...")
    results_text = build_results_text(search_results)
    ai_summary = generate_summary(
        query_pub=query_patent["publication_number"],
        query_title=query_patent["title_text"],
        query_abstract=query_patent["abstract_text"][:800],
        results_json=results_text,
    )

    st.write("Building visualizations...")
    graph_html = build_network_html(results_df, pn)
    fig_assignees = create_assignee_chart(search_results)
    fig_inventors = create_inventor_chart(search_results)
    fig_cpc = create_cpc_chart(search_results)

    status.update(label="Analysis complete", state="complete", expanded=False)

# ── Metrics row ──────────────────────────────────────────────────────────

m1, m2, m3, m4 = st.columns(4)
m1.metric("Results", len(search_results))

unique_assignees = set()
for _, r in search_results.iterrows():
    if r.get("primary_assignee"):
        unique_assignees.add(r["primary_assignee"])
m2.metric("Unique Assignees", len(unique_assignees))

unique_inventors = set()
for _, r in search_results.iterrows():
    if r.get("primary_inventor"):
        unique_inventors.add(r["primary_inventor"])
m3.metric("Unique Inventors", len(unique_inventors))

avg_sim = search_results["similarity_pct"].mean()
m4.metric("Avg Similarity", f"{avg_sim:.1f}%")

# ── Query patent card ────────────────────────────────────────────────────

tags_html = ""
raw_terms = query_patent.get("top_terms")
top_terms = list(raw_terms) if raw_terms is not None and hasattr(raw_terms, '__iter__') else []
if top_terms:
    terms = [t.get("value", "") for t in top_terms[:8] if isinstance(t, dict)]
    terms = [t for t in terms if t]
    if terms:
        tags_html = '<div class="tags-container">' + "".join(
            f'<span class="tag">{t}</span>' for t in terms
        ) + "</div>"

assignee = query_patent.get("primary_assignee") or "N/A"
inventor = query_patent.get("primary_inventor") or "N/A"

st.markdown(
    f"""
    <div class="patent-card">
        <div class="patent-card-header">
            <span class="patent-badge">QUERY PATENT</span>
            <span class="patent-number">{query_patent['publication_number']}</span>
        </div>
        <h3 class="patent-title">{query_patent['title_text']}</h3>
        <div class="patent-meta">
            <div class="meta-item">
                <span class="meta-label">ASSIGNEE</span>
                <span class="meta-value">{assignee}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">INVENTOR</span>
                <span class="meta-value">{inventor}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">FILED</span>
                <span class="meta-value">{query_patent['filed']}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">PUBLISHED</span>
                <span class="meta-value">{query_patent['published']}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">GRANTED</span>
                <span class="meta-value">{query_patent['granted']}</span>
            </div>
        </div>
        <div>
            <span class="meta-label">ABSTRACT</span>
            <p class="patent-abstract-text">{query_patent['abstract_text'][:600]}</p>
        </div>
        {tags_html}
    </div>
    """,
    unsafe_allow_html=True,
)

# ── AI summary ───────────────────────────────────────────────────────────

with st.expander("AI Analysis (Gemini)", expanded=True):
    st.markdown(
        f'<div class="ai-summary">{ai_summary}</div>',
        unsafe_allow_html=True,
    )

# ── Results table ────────────────────────────────────────────────────────

st.markdown(
    '<div class="section-header">'
    '<span class="section-title">Similar Patents</span>'
    f'<span class="section-subtitle">{len(search_results)} results</span>'
    "</div>",
    unsafe_allow_html=True,
)

display_df = search_results[
    [
        "publication_number",
        "title_text",
        "primary_assignee",
        "primary_inventor",
        "filed",
        "similarity_pct",
    ]
].copy()
display_df.insert(0, "rank", range(1, len(display_df) + 1))

st.dataframe(
    display_df,
    column_config={
        "rank": st.column_config.NumberColumn("#", width="small"),
        "similarity_pct": st.column_config.ProgressColumn(
            "Similarity",
            format="%.1f%%",
            min_value=0,
            max_value=100,
        ),
        "publication_number": st.column_config.TextColumn("Patent No."),
        "title_text": st.column_config.TextColumn("Title", width="large"),
        "primary_assignee": st.column_config.TextColumn("Assignee"),
        "primary_inventor": st.column_config.TextColumn("Inventor"),
        "filed": st.column_config.TextColumn("Filed"),
    },
    use_container_width=True,
    hide_index=True,
    height=min(400, 35 * len(display_df) + 38),
)

# ── Charts ───────────────────────────────────────────────────────────────

st.markdown(
    '<div class="section-header">'
    '<span class="section-title">Analytics</span>'
    "</div>",
    unsafe_allow_html=True,
)

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(fig_assignees, use_container_width=True, key="assignees")
with c2:
    st.plotly_chart(fig_inventors, use_container_width=True, key="inventors")

st.plotly_chart(fig_cpc, use_container_width=True, key="cpc")

# ── Network graph ────────────────────────────────────────────────────────

st.markdown(
    '<div class="section-header">'
    '<span class="section-title">Patent Network</span>'
    '<span class="section-subtitle">Drag nodes to explore relationships</span>'
    "</div>",
    unsafe_allow_html=True,
)

components.html(graph_html, height=580, scrolling=False)

# ── Download ─────────────────────────────────────────────────────────────

st.markdown("---")

csv_data = display_df.to_csv(index=False)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("search_results.csv", csv_data)
    zf.writestr("ai_summary.txt", ai_summary)
    zf.writestr("network_graph.html", graph_html)
buf.seek(0)

st.download_button(
    "Download Results (ZIP)",
    data=buf,
    file_name=f"patent_search_{pn}.zip",
    mime="application/zip",
    use_container_width=True,
)

# ── Footer ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="footer">
        Purdue University MSAI Capstone &middot; NASA Technology Transfer Office
    </div>
    """,
    unsafe_allow_html=True,
)
