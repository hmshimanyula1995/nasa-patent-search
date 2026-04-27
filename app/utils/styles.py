import base64
from pathlib import Path

import streamlit as st


def _load_nasa_logo_data_uri() -> str:
    # Bundle the NASA meatball SVG as a data URI so the logo renders without
    # any external dependency. Fixes broken hotlinks (Wikimedia rejects
    # non-browser referers with HTTP 400).
    svg_path = Path(__file__).resolve().parent.parent / "assets" / "nasa_logo.svg"
    encoded = base64.b64encode(svg_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


NASA_LOGO_URL = _load_nasa_logo_data_uri()


def inject_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@300;400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap');

    /* ── NASA Color Tokens ── */
    :root {
        --nasa-blue: #0B3D91;
        --nasa-blue-light: #105BD8;
        --nasa-blue-lighter: #4773AA;
        --nasa-blue-lightest: #DCE4EF;
        --nasa-blue-bg: #F0F4FA;
        --nasa-green: #2E8540;
        --nasa-green-light: #4AA564;
        --nasa-green-lighter: #94BFA2;
        --nasa-green-lightest: #E7F4E4;
        --nasa-cyan: #02BFE7;
        --nasa-cyan-light: #9BDAF1;
        --nasa-cyan-lightest: #E1F3F8;
        --nasa-red: #DD361C;
        --nasa-gold: #FF9D1E;
        --nasa-gold-lightest: #FFEBD1;
        --nasa-gray-dark: #323A45;
        --nasa-gray: #5B616B;
        --nasa-gray-light: #AEB0B5;
        --nasa-gray-lighter: #D6D7D9;
        --nasa-gray-lightest: #F1F1F1;
        --nasa-base: #212121;
        --surface: #FFFFFF;
        --surface-raised: #FAFBFD;
    }

    html, body, [class*="css"] {
        font-family: 'Public Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    h1, h2, h3, h4, h5, h6,
    [data-testid="stMetricLabel"],
    .section-title {
        font-family: 'Inter', -apple-system, sans-serif;
    }

    code, pre, .patent-number {
        font-family: 'DM Mono', 'JetBrains Mono', monospace;
    }

    /* ── Main background ── */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #FFFFFF 0%, #F6F8FC 100%);
    }

    .main .block-container {
        max-width: 1400px;
        padding-top: 2rem;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #FFFFFF 0%, #F0F4FA 100%);
        border-right: 1px solid #DCE4EF;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 14px;
        color: #5B616B;
    }

    /* ── Metric cards ── */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #DCE4EF;
        border-radius: 12px;
        padding: 18px 22px;
        box-shadow: 0 1px 3px rgba(11, 61, 145, 0.06);
        transition: all 0.2s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: #4773AA;
        box-shadow: 0 4px 12px rgba(11, 61, 145, 0.1);
    }

    [data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif;
        font-size: 30px;
        font-weight: 800;
        color: #0B3D91;
    }

    [data-testid="stMetricLabel"] {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: #5B616B !important;
    }

    /* ── Primary button ── */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: linear-gradient(135deg, #0B3D91 0%, #105BD8 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        letter-spacing: 0.5px !important;
        padding: 0.65rem 1.5rem !important;
        color: #FFFFFF !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 2px 8px rgba(11, 61, 145, 0.25) !important;
    }

    /* Streamlit wraps the button label in a nested <p> inside
       [data-testid="stMarkdownContainer"] whose color rule wins over the
       container's. Force white on the label markup explicitly. */
    .stButton > button[kind="primary"] p,
    .stFormSubmitButton > button p,
    .stButton > button[kind="primary"] [data-testid="stMarkdownContainer"] p,
    .stFormSubmitButton > button [data-testid="stMarkdownContainer"] p {
        color: #FFFFFF !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        box-shadow: 0 6px 20px rgba(11, 61, 145, 0.35) !important;
        transform: translateY(-1px) !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 2px solid #DCE4EF;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        color: #5B616B;
    }

    .stTabs [aria-selected="true"] {
        color: #0B3D91 !important;
        border-bottom: 3px solid #0B3D91;
        background: rgba(11, 61, 145, 0.04);
    }

    /* ── Expander ── */
    [data-testid="stExpander"] {
        background: #FFFFFF;
        border: 1px solid #DCE4EF;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(11, 61, 145, 0.04);
    }

    [data-testid="stExpander"] details summary {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        color: #323A45;
    }

    /* ── Dataframe ── */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #DCE4EF;
    }

    /* ── Text inputs ── */
    [data-testid="stTextInput"] input {
        border: 1.5px solid #9DA9BA;
        background-color: #F8FAFC;
        color: #1A1F2C;
        border-radius: 10px;
        font-family: 'Public Sans', sans-serif;
        font-size: 14px;
        padding: 10px 14px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
    }

    [data-testid="stTextInput"] input::placeholder {
        color: #6B7480;
        opacity: 1;
    }

    [data-testid="stTextInput"] input:hover {
        border-color: #6B7480;
    }

    [data-testid="stTextInput"] input:focus {
        border-color: #105BD8;
        background-color: #FFFFFF;
        box-shadow: 0 0 0 3px rgba(16, 91, 216, 0.18);
    }

    /* Hide Streamlit's "Press Enter to submit form" hint that overlays the
       input on the right side. The form has a labeled submit button, so the
       hint is redundant — and with our higher-contrast input fill it visually
       clashes with the typed value. */
    [data-testid="InputInstructions"] {
        display: none !important;
    }

    /* ── Slider ── */
    [data-testid="stSlider"] [role="slider"] {
        background-color: #0B3D91;
    }

    /* ── Patent card ── */
    .patent-card {
        background: #FFFFFF;
        border: 1px solid #DCE4EF;
        border-left: 4px solid #0B3D91;
        border-radius: 0 14px 14px 0;
        padding: 28px 32px;
        margin: 20px 0;
        box-shadow: 0 2px 8px rgba(11, 61, 145, 0.06);
    }

    .patent-card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 18px;
    }

    .patent-badge {
        background: linear-gradient(135deg, #0B3D91, #105BD8);
        color: #FFFFFF;
        padding: 5px 14px;
        border-radius: 20px;
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }

    .patent-number {
        color: #0B3D91;
        font-family: 'DM Mono', monospace;
        font-size: 14px;
        font-weight: 500;
    }

    .patent-title {
        color: #212121;
        font-family: 'Inter', sans-serif;
        font-size: 20px;
        font-weight: 700;
        margin: 0 0 22px 0;
        line-height: 1.4;
    }

    .patent-meta {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 18px;
        margin-bottom: 22px;
        padding: 18px;
        background: #F6F8FC;
        border-radius: 10px;
    }

    .meta-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .meta-label {
        color: #5B616B;
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }

    .meta-value {
        color: #212121;
        font-family: 'Public Sans', sans-serif;
        font-size: 14px;
        font-weight: 500;
    }

    .patent-abstract-text {
        color: #5B616B;
        font-family: 'Public Sans', sans-serif;
        font-size: 13.5px;
        line-height: 1.75;
        margin-top: 8px;
    }

    /* ── Tags ── */
    .tags-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 18px;
    }

    .tag {
        background: #E1F3F8;
        color: #046B99;
        padding: 4px 14px;
        border-radius: 20px;
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        font-weight: 500;
        border: 1px solid #9BDAF1;
    }

    /* ── AI Summary ── */
    .ai-summary {
        background: linear-gradient(135deg, #E7F4E4 0%, #F6F8FC 100%);
        border-left: 4px solid #2E8540;
        border-radius: 0 12px 12px 0;
        padding: 26px;
        color: #323A45;
        font-family: 'Public Sans', sans-serif;
        line-height: 1.8;
        font-size: 14px;
    }

    /* ── Section headers ── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 36px 0 18px 0;
        padding-bottom: 10px;
        border-bottom: 2px solid #DCE4EF;
    }

    .section-title {
        color: #0B3D91;
        font-family: 'Inter', sans-serif;
        font-size: 18px;
        font-weight: 700;
        margin: 0;
    }

    .section-subtitle {
        color: #5B616B;
        font-family: 'Public Sans', sans-serif;
        font-size: 13px;
        font-weight: 400;
        margin-left: auto;
    }

    /* ── Empty state hero ── */
    .empty-state {
        text-align: center;
        padding: 80px 20px 60px;
        animation: empty-state-fade-in 0.45s ease-out both;
    }

    @keyframes empty-state-fade-in {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    .empty-state-icon {
        width: 110px;
        margin-bottom: 28px;
        filter: drop-shadow(0 6px 16px rgba(11, 61, 145, 0.18));
    }

    .empty-state h2 {
        color: #0B3D91;
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 30px;
        letter-spacing: -0.01em;
        margin: 0 0 10px 0;
    }

    .empty-state p {
        color: #5B616B;
        font-family: 'Public Sans', sans-serif;
        max-width: 560px;
        margin: 0 auto;
        font-size: 15px;
        line-height: 1.7;
    }

    .empty-state-examples {
        margin: 36px auto 0;
        max-width: 560px;
        text-align: left;
        background: #F8FAFC;
        border: 1px solid #E1E8F2;
        border-radius: 14px;
        padding: 22px 26px;
    }

    .empty-state-examples-label {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.6px;
        text-transform: uppercase;
        color: #5B616B;
        margin-bottom: 12px;
    }

    .empty-state-examples-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }

    .empty-state-example {
        font-family: 'DM Mono', monospace;
        font-size: 13px;
        color: #0B3D91;
        background: #FFFFFF;
        border: 1px solid #DCE4EF;
        border-radius: 8px;
        padding: 6px 12px;
    }

    /* ── AI summary "thinking" indicator (shown until the first stream
       chunk arrives so users see continuous activity, never a blank). ── */
    .ai-thinking {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 4px 0 8px;
        color: #5B616B;
        font-family: 'Public Sans', sans-serif;
        font-size: 14px;
        font-style: italic;
    }

    .ai-thinking-dots {
        display: inline-flex;
        gap: 5px;
    }

    .ai-thinking-dot {
        width: 8px;
        height: 8px;
        background: #105BD8;
        border-radius: 50%;
        animation: ai-thinking-bounce 1.3s ease-in-out infinite both;
    }

    .ai-thinking-dot:nth-child(2) { animation-delay: 0.16s; }
    .ai-thinking-dot:nth-child(3) { animation-delay: 0.32s; }

    @keyframes ai-thinking-bounce {
        0%, 80%, 100% { opacity: 0.25; transform: scale(0.7); }
        40%          { opacity: 1;    transform: scale(1); }
    }

    /* ── Header banner ── */
    .header-banner {
        background: linear-gradient(135deg, #0B3D91 0%, #105BD8 60%, #046B99 100%);
        border-radius: 14px;
        padding: 28px 36px;
        margin-bottom: 28px;
        display: flex;
        align-items: center;
        gap: 20px;
        box-shadow: 0 4px 16px rgba(11, 61, 145, 0.2);
    }

    .header-banner img {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: white;
        padding: 4px;
    }

    .header-banner h1 {
        color: #FFFFFF;
        font-family: 'Inter', sans-serif;
        font-size: 24px;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.3px;
    }

    .header-banner p {
        color: rgba(255, 255, 255, 0.8);
        font-family: 'Public Sans', sans-serif;
        font-size: 13px;
        margin: 4px 0 0 0;
        letter-spacing: 0.5px;
    }

    /* ── Graph legend (sidebar) ── */
    .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 12px;
        color: #5B616B;
        margin-right: 12px;
    }

    .legend-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
    }

    /* Score-tier sizing: bigger dot = better score. Mirrors the network
       graph's size-by-score encoding (graph.py: 18 + score*32) so color-blind
       users get a size hierarchy that reinforces the ordering. */
    .legend-dot.tier-1 { width: 6px;  height: 6px;  }
    .legend-dot.tier-2 { width: 8px;  height: 8px;  }
    .legend-dot.tier-3 { width: 10px; height: 10px; }
    .legend-dot.tier-4 { width: 12px; height: 12px; }
    .legend-dot.tier-5 { width: 14px; height: 14px; }
    .legend-dot.tier-6 { width: 16px; height: 16px; }

    .legend-triangle {
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-bottom: 10px solid #5B616B;
        display: inline-block;
    }

    .legend-section-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #323A45;
        margin-top: 8px;
        margin-bottom: 2px;
        display: block;
    }

    /* ── Footer ── */
    .footer {
        text-align: center;
        padding: 32px 20px 16px;
        color: #AEB0B5;
        font-family: 'Public Sans', sans-serif;
        font-size: 12px;
        border-top: 1px solid #DCE4EF;
        margin-top: 60px;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }

    ::-webkit-scrollbar-track {
        background: #F1F1F1;
    }

    ::-webkit-scrollbar-thumb {
        background: #AEB0B5;
        border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #5B616B;
    }

    /* ── Responsive ── */
    @media (max-width: 768px) {
        .patent-meta {
            grid-template-columns: 1fr 1fr;
        }

        [data-testid="stMetricValue"] {
            font-size: 24px;
        }

        .patent-title {
            font-size: 17px;
        }

        .header-banner {
            padding: 20px;
        }

        .header-banner h1 {
            font-size: 18px;
        }
    }

    /* ── Print styles ── */
    @media print {
        @page {
            size: landscape;
            margin: 0.5in;
        }

        /* Hide sidebar, search form, download button, interactive graph */
        [data-testid="stSidebar"],
        [data-testid="stStatusWidget"],
        .stFormSubmitButton,
        .stDownloadButton,
        .stSlider,
        iframe { display: none !important; }

        /* Full width - remove max-width constraint */
        .main .block-container {
            max-width: 100% !important;
            padding: 0 !important;
        }

        /* Remove overflow clipping */
        [data-testid="stDataFrame"],
        [data-testid="stExpander"] {
            overflow: visible !important;
        }

        /* Force columns to stack vertically */
        [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            width: 100% !important;
            flex: none !important;
        }

        /* Remove decorative effects */
        .patent-card,
        [data-testid="stMetric"],
        [data-testid="stExpander"] {
            box-shadow: none !important;
            border-radius: 0 !important;
        }

        /* Expand expanders so content is visible */
        [data-testid="stExpander"] details {
            open: true;
        }
        [data-testid="stExpander"] details[open] summary ~ * {
            display: block !important;
        }

        /* Clean header banner for print */
        .header-banner {
            background: #0B3D91 !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }

        /* Ensure background colors print */
        .patent-badge, .tag, .ai-summary, .patent-meta {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }

        /* Page break control */
        .patent-card, .section-header {
            break-inside: avoid;
        }
        .section-header {
            break-after: avoid;
        }

        /* Hide footer */
        .footer { display: none !important; }
    }
    </style>
    """, unsafe_allow_html=True)
