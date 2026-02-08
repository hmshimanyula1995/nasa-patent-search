import streamlit as st

NASA_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/NASA_logo.svg/200px-NASA_logo.svg.png"


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
        border: 1.5px solid #DCE4EF;
        border-radius: 10px;
        font-family: 'Public Sans', sans-serif;
        font-size: 14px;
        padding: 10px 14px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    [data-testid="stTextInput"] input:focus {
        border-color: #105BD8;
        box-shadow: 0 0 0 3px rgba(16, 91, 216, 0.12);
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

    /* ── Empty state ── */
    .empty-state {
        text-align: center;
        padding: 100px 20px 60px;
    }

    .empty-state-icon {
        width: 100px;
        margin-bottom: 28px;
    }

    .empty-state h2 {
        color: #0B3D91;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 26px;
        margin: 0 0 10px 0;
    }

    .empty-state p {
        color: #5B616B;
        font-family: 'Public Sans', sans-serif;
        max-width: 520px;
        margin: 0 auto;
        font-size: 15px;
        line-height: 1.7;
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
    </style>
    """, unsafe_allow_html=True)
