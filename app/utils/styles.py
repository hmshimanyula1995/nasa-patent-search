import streamlit as st


def inject_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ── Main background ── */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(160deg, #0E1117 0%, #131620 40%, #1a1a2e 100%);
    }

    .main .block-container {
        max-width: 1400px;
        padding-top: 2rem;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.06);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 14px;
    }

    /* ── Metric cards ── */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px 20px;
        backdrop-filter: blur(10px);
        transition: border-color 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: rgba(0, 212, 255, 0.3);
    }

    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 700;
        background: linear-gradient(135deg, #FAFAFA, #A1A1AA);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    [data-testid="stMetricLabel"] {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #71717A !important;
    }

    /* ── Primary button ── */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: linear-gradient(135deg, #0066ff, #00d4ff) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        padding: 0.6rem 1.5rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(0, 102, 255, 0.3) !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        box-shadow: 0 6px 25px rgba(0, 102, 255, 0.5) !important;
        transform: translateY(-1px) !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 500;
        color: #71717A;
        transition: all 0.2s ease;
    }

    .stTabs [aria-selected="true"] {
        color: #00D4FF !important;
        border-bottom: 2px solid #00D4FF;
        background: rgba(0, 212, 255, 0.05);
    }

    /* ── Expander ── */
    [data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        overflow: hidden;
    }

    [data-testid="stExpander"] details summary {
        font-weight: 600;
    }

    /* ── Dataframe ── */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
    }

    /* ── Custom card ── */
    .patent-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.9), rgba(30, 41, 59, 0.5));
        border: 1px solid rgba(0, 212, 255, 0.15);
        border-radius: 16px;
        padding: 28px;
        margin: 16px 0;
        backdrop-filter: blur(10px);
    }

    .patent-card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
    }

    .patent-badge {
        background: linear-gradient(135deg, #0066ff, #00d4ff);
        color: white;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
    }

    .patent-number {
        color: #00D4FF;
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        font-weight: 500;
    }

    .patent-title {
        color: #FAFAFA;
        font-size: 20px;
        font-weight: 600;
        margin: 0 0 20px 0;
        line-height: 1.4;
    }

    .patent-meta {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
        margin-bottom: 20px;
    }

    .meta-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .meta-label {
        color: #71717A;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }

    .meta-value {
        color: #E4E4E7;
        font-size: 14px;
        font-weight: 400;
    }

    .patent-abstract-text {
        color: #A1A1AA;
        font-size: 13px;
        line-height: 1.7;
        margin-top: 8px;
    }

    /* ── Tags ── */
    .tags-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 16px;
    }

    .tag {
        background: rgba(0, 212, 255, 0.12);
        color: #00D4FF;
        padding: 3px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        border: 1px solid rgba(0, 212, 255, 0.15);
    }

    /* ── AI Summary ── */
    .ai-summary {
        background: linear-gradient(135deg, rgba(124, 58, 237, 0.08), rgba(0, 212, 255, 0.06));
        border-left: 3px solid #7C3AED;
        border-radius: 0 12px 12px 0;
        padding: 24px;
        color: #D4D4D8;
        line-height: 1.8;
        font-size: 14px;
    }

    /* ── Section headers ── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 32px 0 16px 0;
    }

    .section-icon {
        font-size: 20px;
    }

    .section-title {
        color: #FAFAFA;
        font-size: 18px;
        font-weight: 600;
        margin: 0;
    }

    .section-subtitle {
        color: #71717A;
        font-size: 13px;
        font-weight: 400;
        margin-left: auto;
    }

    /* ── Empty state ── */
    .empty-state {
        text-align: center;
        padding: 120px 20px 80px;
    }

    .empty-state-icon {
        font-size: 64px;
        margin-bottom: 24px;
        opacity: 0.8;
    }

    .empty-state h2 {
        color: #FAFAFA;
        font-weight: 300;
        font-size: 28px;
        margin: 0 0 12px 0;
    }

    .empty-state p {
        color: #71717A;
        max-width: 500px;
        margin: 0 auto;
        font-size: 15px;
        line-height: 1.6;
    }

    /* ── Footer ── */
    .footer {
        text-align: center;
        padding: 40px 20px 20px;
        color: #52525B;
        font-size: 12px;
        border-top: 1px solid rgba(255, 255, 255, 0.04);
        margin-top: 60px;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }

    ::-webkit-scrollbar-track {
        background: transparent;
    }

    ::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.2);
    }

    /* ── Responsive ── */
    @media (max-width: 768px) {
        .patent-meta {
            grid-template-columns: 1fr 1fr;
        }

        [data-testid="stMetricValue"] {
            font-size: 22px;
        }

        .patent-title {
            font-size: 17px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
