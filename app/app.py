import hashlib
import io
import logging
import time
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.styles import inject_custom_css, NASA_LOGO_URL
from utils.bigquery_client import (
    normalize_patent_number,
    search_patents,
    extract_citation_neighbors,
    fetch_citation_neighbors,
)
from utils.gemini_client import (
    stream_summary,
    build_results_text,
    build_results_text_with_graph,
    GRAPH_AWARE_PROMPT,
)
from utils.charts import create_assignee_chart, create_inventor_chart, create_cpc_chart
from utils.graph import build_network_html
from utils.graph_ranking import (
    build_citation_graph,
    compute_ppr,
    normalize_scores,
    blend_scores,
    get_citation_edges,
)
from utils.refresh import (
    AGING_DAYS,
    COOLDOWN_DAYS,
    STALE_WARNING_DAYS,
    cooldown_remaining,
    days_since,
    get_last_refresh,
    trigger_refresh,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            placeholder="e.g. US-2007156035-A1 or 8410469",
            help="Enter a US patent publication number (US-XXXXXXX-A1) or grant number (8410469). Commas are stripped automatically.",
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
            <span class="legend-section-label">Edges</span>
            <span class="legend-item"><span class="legend-dot" style="background:#105BD8;"></span> Similar</span>
            <span class="legend-item"><span class="legend-dot" style="background:#4773AA;"></span> Cites</span>
            <span class="legend-item"><span class="legend-dot" style="background:#FF9D1E;"></span> Parent</span>
            <span class="legend-item"><span class="legend-dot" style="background:#DD361C;"></span> Child</span>
            <br/><br/>
            <span class="legend-section-label">Node Score</span>
            <span class="legend-item"><span class="legend-dot tier-6" style="background:#1a7431;"></span> 95%+</span>
            <span class="legend-item"><span class="legend-dot tier-5" style="background:#2E8540;"></span> 90%+</span>
            <span class="legend-item"><span class="legend-dot tier-4" style="background:#4A90D9;"></span> 85%+</span>
            <span class="legend-item"><span class="legend-dot tier-3" style="background:#F0C419;"></span> 80%+</span>
            <span class="legend-item"><span class="legend-dot tier-2" style="background:#FF9D1E;"></span> 75%+</span>
            <span class="legend-item"><span class="legend-dot tier-1" style="background:#DD361C;"></span> &lt;75%</span>
            <br/><br/>
            <span class="legend-section-label">Node Shape</span>
            <span class="legend-item"><span class="legend-dot" style="background:#5B616B;"></span> Search result</span>
            <span class="legend-item"><span class="legend-triangle" style="border-bottom-color:#5B616B;"></span> Citation network</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    ranking_mode = st.radio(
        "Ranking Mode",
        ["Blended", "Text Similarity", "Graph Importance"],
        index=0,
        help="Controls result sorting and graph node coloring.",
    )

    # ── Patent Data Refresh ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Patent Data Refresh**")
    st.caption(
        "Updates automatically every 3 months — use the button below if "
        "you need it sooner."
    )

    refresh_status = get_last_refresh()

    if not refresh_status.configured:
        st.caption(
            ":grey[Manual refresh is not available in this environment. "
            "Contact an administrator if you need the latest patents.]"
        )
    else:
        if refresh_status.last_run_time is None:
            st.info("No refresh has run yet.")
        else:
            n_days = days_since(refresh_status.last_run_time) or 0
            if n_days == 0:
                when = "today"
            elif n_days == 1:
                when = "yesterday"
            else:
                when = f"{n_days} days ago"

            if n_days <= AGING_DAYS:
                st.success(f"Patent data is current. Last refreshed {when}.")
            elif n_days <= STALE_WARNING_DAYS:
                st.warning(
                    f"Patent data is getting old — last refreshed {when}."
                )
            else:
                st.error(
                    f"Patent data is more than {STALE_WARNING_DAYS} days old. "
                    "Use the button below to pull the latest patents."
                )

            if refresh_status.last_run_state and refresh_status.last_run_state != "SUCCEEDED":
                st.caption(
                    f"Last refresh did not finish successfully "
                    f"({refresh_status.last_run_state.lower()})."
                )

        # In-flight gate: cooldown is keyed off the last *successful* run, so
        # during a first PENDING/RUNNING run cooldown_remaining returns 0 and
        # the button would stay enabled, letting a user spam-trigger duplicate
        # multi-dollar BigQuery scans. Block the button while a run is active;
        # the existing cooldown branch then takes over once the run succeeds.
        if refresh_status.last_run_state in {"PENDING", "RUNNING"}:
            st.button(
                "Refresh in progress…",
                disabled=True,
                use_container_width=True,
                key="refresh_running",
            )
            st.caption("Check back in a minute.")
        else:
            # Cooldown is keyed off the last *successful* run, so a failed run
            # does not block an admin from retrying immediately.
            cooldown = cooldown_remaining(refresh_status.last_successful_run_time)
            if cooldown > 0:
                day_word = "day" if cooldown == 1 else "days"
                st.button(
                    f"Manual refresh available in {cooldown} {day_word}",
                    disabled=True,
                    use_container_width=True,
                    key="refresh_disabled",
                )
                st.caption("Manual refreshes are limited to once a week.")
            else:
                if st.button(
                    "Refresh Patent Data Now",
                    use_container_width=True,
                    type="secondary",
                    key="refresh_trigger",
                ):
                    with st.spinner("Starting refresh…"):
                        ok, msg = trigger_refresh()
                    if ok:
                        st.toast(msg, icon="✅")
                    else:
                        st.toast(msg, icon="⚠️")
                st.caption("Pulls the newest US patents into the index.")

# ── Main Area ────────────────────────────────────────────────────────────

# ── Stale-data banner (shown when last refresh > STALE_WARNING_DAYS) ─────

_refresh_banner_status = get_last_refresh()
if (
    _refresh_banner_status.configured
    and _refresh_banner_status.last_run_time is not None
    and not st.session_state.get("dismissed_stale_banner", False)
):
    _n_days = days_since(_refresh_banner_status.last_run_time) or 0
    if _n_days > STALE_WARNING_DAYS:
        col_msg, col_action = st.columns([6, 1])
        with col_msg:
            st.warning(
                f"The patent index has not been refreshed in {_n_days} days. "
                "Some recent patents may be missing from your results. "
                "Use the refresh button in the sidebar to pull the latest."
            )
        with col_action:
            if st.button("Dismiss", key="dismiss_stale_banner"):
                st.session_state["dismissed_stale_banner"] = True
                st.rerun()


if "patent_number" not in st.session_state:
    st.markdown(
        f"""
        <div class="empty-state">
            <img src="{NASA_LOGO_URL}" class="empty-state-icon" alt="NASA" />
            <h2>Search NASA's Patent Database</h2>
            <p>
                Enter a patent number in the sidebar to find semantically similar
                patents using AI-powered vector search across millions of US patents.
                Results stream in live with a Gemini-generated landscape analysis.
            </p>
            <div class="empty-state-examples">
                <div class="empty-state-examples-label">Try one of these</div>
                <div class="empty-state-examples-list">
                    <span class="empty-state-example">US-2007156035-A1</span>
                    <span class="empty-state-example">US-8410469-B2</span>
                    <span class="empty-state-example">US-9890038-B2</span>
                </div>
            </div>
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
    # ── Normalize patent number ──
    st.write("Resolving patent number...")
    logger.info("Search initiated: input='%s', top_k=%d", pn, tk)
    t_start = time.time()

    normalized = normalize_patent_number(pn)
    if normalized is None:
        status.update(label="Patent not found", state="error")
        st.error(
            f"Patent number `{pn}` not found in the indexed database. "
            "Try the full publication format (e.g. `US-8410469-B2`) or check "
            "the number for typos."
        )
        logger.warning("Normalization failed for input='%s'", pn)
        st.stop()

    if normalized != pn:
        st.write(f"Resolved `{pn}` → `{normalized}`")
        logger.info("Normalized '%s' -> '%s'", pn, normalized)

    pn = normalized

    st.write("Searching patent database...")
    results_df = search_patents(pn, tk)

    if results_df.empty:
        status.update(label="No results found", state="error")
        st.error(
            f"Patent `{pn}` was found but returned no similarity results. "
            "It may not yet be indexed for similarity search."
        )
        logger.warning("Vector search returned 0 results for '%s'", pn)
        st.stop()

    # Identify the query patent by publication number rather than row position.
    # The vector search ORDER BY distance puts ties (identical embeddings) in
    # undefined order, so the self-match is not guaranteed to be at row 0.
    query_mask = results_df["publication_number"] == pn
    if query_mask.any():
        query_patent = results_df[query_mask].iloc[0]
        search_results = results_df[~query_mask].copy()
    else:
        # Self-match missing entirely (rare). Fall back to row 0 so the page
        # still renders, but log it because it indicates a data issue.
        logger.warning(
            "Query patent '%s' not found in its own vector search results; "
            "falling back to row 0 as the query patent.", pn,
        )
        query_patent = results_df.iloc[0]
        search_results = results_df.iloc[1:].copy()

    # ── Citation expansion + PPR pipeline ──
    ppr_available = False
    expanded_df = None
    ppr_scores: dict[str, float] = {}
    citation_edges: list[tuple[str, str, str]] = []

    try:
        st.write("Expanding citation network...")
        neighbor_ids = extract_citation_neighbors(results_df)
        if neighbor_ids:
            expanded_df = fetch_citation_neighbors(tuple(neighbor_ids))

        st.write("Computing graph ranking (PageRank)...")
        G = build_citation_graph(results_df, expanded_df, pn)
        ppr_scores = compute_ppr(G, pn)

        if ppr_scores:
            search_results = blend_scores(search_results, ppr_scores)
            result_pubs = set(search_results["publication_number"].tolist())
            citation_edges = get_citation_edges(G, result_pubs)
            ppr_available = True

            # Add PPR scores to expanded_df for visualization
            if expanded_df is not None and not expanded_df.empty:
                normalized = normalize_scores(ppr_scores)
                expanded_df["ppr_score"] = expanded_df["publication_number"].map(
                    lambda pub: normalized.get(pub, 0.0)
                )
                expanded_df["ppr_pct"] = (expanded_df["ppr_score"] * 100).clip(0, 100)
    except Exception as exc:
        # Graceful degradation: PPR failed, continue with cosine-only
        logger.error("PPR pipeline failed, falling back to cosine-only: %s", exc)
        ppr_available = False
        expanded_df = None

    # ── Determine score column from ranking mode ──
    # Sort BEFORE generating the AI summary so the summary's "top 5" matches
    # the ordering shown in the table and graph.
    if not ppr_available:
        score_col = "similarity"
        sort_col = "similarity"
    elif ranking_mode == "Text Similarity":
        score_col = "similarity"
        sort_col = "similarity"
    elif ranking_mode == "Graph Importance":
        score_col = "ppr_score"
        sort_col = "ppr_score"
    else:  # Blended
        score_col = "blended_score"
        sort_col = "blended_score"

    search_results = search_results.sort_values(sort_col, ascending=False)

    # ── Build AI summary prompt inputs ──
    # The Gemini call itself is moved out of the critical render path; it
    # streams into the AI placeholder after the table/charts/network render.
    # Building results_text here is cheap and keeps the prompt's data inputs
    # consistent with the order shown in the UI.
    if ppr_available:
        results_text = build_results_text_with_graph(
            search_results, ppr_scores, citation_edges, expanded_df,
        )
        ai_prompt_template = GRAPH_AWARE_PROMPT
    else:
        results_text = build_results_text(search_results)
        ai_prompt_template = None

    # Rebuild full results_df with query patent + scored search results for graph
    graph_results_df = pd.concat(
        [results_df.iloc[:1], search_results], ignore_index=True,
    )

    st.write("Building visualizations...")
    graph_html = build_network_html(
        results_df=graph_results_df,
        query_patent=pn,
        score_column=score_col,
        expanded_df=expanded_df,
        expanded_score_column="ppr_score",
    )
    fig_assignees = create_assignee_chart(search_results)
    fig_inventors = create_inventor_chart(search_results)
    fig_cpc = create_cpc_chart(search_results)

    t_total = time.time() - t_start
    logger.info(
        "Analysis complete: %d results, ppr=%s, total=%.2fs",
        len(search_results), ppr_available, t_total,
    )
    status.update(label="Analysis complete", state="complete", expanded=False)

# ── Metrics row ──────────────────────────────────────────────────────────

if ppr_available:
    m1, m2, m3, m4, m5 = st.columns(5)
else:
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

if ppr_available:
    expanded_count = len(expanded_df) if expanded_df is not None and not expanded_df.empty else 0
    m5.metric("Citation Network", f"+{expanded_count}")

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

# ── AI summary (placeholder; filled by streaming block below the network) ─

# Reserve the visual position now so the streamed content lands above the
# results table when it arrives. Render the expander immediately with a
# "Generating analysis…" indicator so the panel shows continuous activity
# while Gemini's first token is in flight (otherwise the user sees the
# panel blank for 1–3s before text starts appearing).
ai_placeholder = st.empty()

AI_THINKING_HTML = """
<div class="ai-thinking">
    <span class="ai-thinking-dots">
        <span class="ai-thinking-dot"></span>
        <span class="ai-thinking-dot"></span>
        <span class="ai-thinking-dot"></span>
    </span>
    Generating analysis…
</div>
"""

with ai_placeholder.container():
    with st.expander("AI Analysis (Gemini)", expanded=True):
        st.markdown(AI_THINKING_HTML, unsafe_allow_html=True)

# ── Results table ────────────────────────────────────────────────────────

sort_label = ranking_mode if ppr_available else "Text Similarity"
st.markdown(
    '<div class="section-header">'
    '<span class="section-title">Similar Patents</span>'
    f'<span class="section-subtitle">{len(search_results)} results &middot; Sorted by {sort_label}</span>'
    "</div>",
    unsafe_allow_html=True,
)

# Build display columns based on available scores
base_cols = [
    "publication_number",
    "title_text",
    "primary_assignee",
    "primary_inventor",
    "filed",
    "similarity_pct",
]
col_config: dict = {
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
}

if ppr_available:
    base_cols.extend(["ppr_pct", "blended_pct"])
    col_config["ppr_pct"] = st.column_config.ProgressColumn(
        "Graph (PPR)",
        format="%.1f%%",
        min_value=0,
        max_value=100,
    )
    col_config["blended_pct"] = st.column_config.ProgressColumn(
        "Blended",
        format="%.1f%%",
        min_value=0,
        max_value=100,
    )

display_df = search_results[base_cols].copy()
display_df.insert(0, "rank", range(1, len(display_df) + 1))

st.dataframe(
    display_df,
    column_config=col_config,
    use_container_width=True,
    hide_index=True,
    height=min(400, 35 * len(display_df) + 38),
)

# ── Structurally Important Patents (from citation expansion) ─────────────

if ppr_available and expanded_df is not None and not expanded_df.empty:
    struct_df = expanded_df[expanded_df["ppr_pct"] > 0].copy()
    struct_df = struct_df.sort_values("ppr_pct", ascending=False).head(10)

    if not struct_df.empty:
        st.markdown(
            '<div class="section-header">'
            '<span class="section-title">Structurally Important Patents</span>'
            '<span class="section-subtitle">Discovered via citation network analysis</span>'
            "</div>",
            unsafe_allow_html=True,
        )

        struct_display = struct_df[
            [
                "publication_number",
                "title_text",
                "primary_assignee",
                "filed",
                "ppr_pct",
            ]
        ].copy()
        struct_display.insert(0, "rank", range(1, len(struct_display) + 1))

        st.dataframe(
            struct_display,
            column_config={
                "rank": st.column_config.NumberColumn("#", width="small"),
                "publication_number": st.column_config.TextColumn("Patent No."),
                "title_text": st.column_config.TextColumn("Title", width="large"),
                "primary_assignee": st.column_config.TextColumn("Assignee"),
                "filed": st.column_config.TextColumn("Filed"),
                "ppr_pct": st.column_config.ProgressColumn(
                    "Graph Importance",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                ),
            },
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(struct_display) + 38),
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

# ── Stream AI summary into the placeholder reserved above ────────────────

# Hash results_text into the session key so the cached stream invalidates if
# the prompt's data inputs change mid-session (e.g. user toggles ranking_mode
# and the rebuilt results_text reorders or shifts the graph context).
results_hash = hashlib.sha1(results_text.encode("utf-8")).hexdigest()[:12]
session_key = (
    f"ai_summary_streamed:{pn}|{tk}|{ranking_mode}|{ppr_available}|{results_hash}"
)

with ai_placeholder.container():
    with st.expander("AI Analysis (Gemini)", expanded=True):
        if session_key in st.session_state:
            ai_summary = st.session_state[session_key]
            st.markdown(
                f'<div class="ai-summary">{ai_summary}</div>',
                unsafe_allow_html=True,
            )
        else:
            ai_summary = st.write_stream(
                stream_summary(
                    query_pub=query_patent["publication_number"],
                    query_title=query_patent["title_text"],
                    query_abstract=query_patent["abstract_text"][:800],
                    results_json=results_text,
                    prompt_template=ai_prompt_template,
                )
            )
            st.session_state[session_key] = ai_summary

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
