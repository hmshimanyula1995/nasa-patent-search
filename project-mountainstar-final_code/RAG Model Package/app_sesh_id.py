#!/usr/bin/env python
# coding: utf-8
# %%

# %%


# app.py — NASA dark UI that runs your existing notebook ONLY when "Run Search" is clicked.

import os
import time, re
import sys, signal, subprocess
import base64, io, zipfile
from pathlib import Path
from PIL import Image
import pandas as pd
import streamlit as st
import papermill as pm
import streamlit.components.v1 as components
from concurrent.futures import ThreadPoolExecutor
import json
from typing import Optional, Dict, Any
from datetime import datetime
import random

### Per-tab / Per-browser SESSION_ID ----
### human-readable session ID ----
def get_session_id() -> str:
    """
    Format example: 20251121_231505123
    - 20251121  → YYYYMMDD
    - 231505    → HHMMSS
    - 123       → mmm
    """
    if "session_id" not in st.session_state:
        now = datetime.now()
        ms = int(now.microsecond / 1000)  # convert µs → ms (0–999)
        st.session_state["session_id"] = now.strftime("%Y%m%d_%H%M%S") + f"{ms:03d}"
    return st.session_state["session_id"]

SESSION_ID = get_session_id()
SESSION_PREFIX = f"{SESSION_ID}__"

# lightweight scraping (for Google Patents)
try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None

# autorefresh (community component)
try:
    from streamlit_autorefresh import st_autorefresh
    HAVE_AUTOREFRESH = True
except Exception:
    HAVE_AUTOREFRESH = False

# one shared background executor across reruns
@st.cache_resource
def get_executor():
    return ThreadPoolExecutor(max_workers=1)

# --- persistent "running" banner style (white on black) ---
st.markdown("""RAGModelTesting
<style>
.run-panel{
  background:#0B0B0B; color:#FFFFFF; border:1px solid #222; border-radius:10px;
  padding:12px 16px; display:flex; align-items:center; gap:10px; font-weight:500;
}
.run-panel .spin{
  width:28px; height:28px; border:4px solid #555; border-top-color:#fff;
  border-radius:50%; animation:spin 1s linear infinite;
}
@keyframes spin{ to{ transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)

# --------- Paths (assumes app.py is in the same folder as the notebook) ---------
ENGINE_NOTEBOOK = Path(__file__).parent / "RAGModel-V3-Final.ipynb"
ENGINE_DIR = ENGINE_NOTEBOOK.parent

# All outputs live under ./outputs/<type>/SESSION_PREFIX*
OUTPUTS_DIR    = ENGINE_DIR / "outputs"
PRIMARY_DIR    = OUTPUTS_DIR / "primary"
SECONDARY_DIR  = OUTPUTS_DIR / "secondary"
HTML_DIR       = OUTPUTS_DIR / "html"
VISUALS_DIR_L1 = OUTPUTS_DIR / "visuals_level_1"
VISUALS_DIR_L2 = OUTPUTS_DIR / "visuals_level_2"

for d in (PRIMARY_DIR, SECONDARY_DIR, HTML_DIR, VISUALS_DIR_L1, VISUALS_DIR_L2):
    d.mkdir(parents=True, exist_ok=True)


# Expected outputs produced by your notebook (relative to project root)
PRIMARY_CSV   = PRIMARY_DIR   / f"{SESSION_PREFIX}rag_search_from_patent_abstract_results_with_connections.csv"
SECONDARY_CSV = SECONDARY_DIR / f"{SESSION_PREFIX}rag_search_second_connections.csv"

# Network diagram HTML lives in outputs/html
HTML_NETWORK  = HTML_DIR / f"{SESSION_PREFIX}patent_connection_network.html"

TOPK_MAX_CAP = 100_000  # safety cap used when user selects "ALL" (tune as needed)

# ---- Helpers to build per-run paths using <SESSION_ID>_<PATENT>__ ----

def make_session_prefix_for(patent_code: str) -> str:
    """
    Build a per-run prefix:
        <SESSION_ID>_<CANONICAL_PATENT_NO_DASHES>__
    Example:
        20251129-184530_US9872293B1__
    """
    canon = to_canonical_patent(patent_code)
    compact = re.sub(r"[^A-Z0-9]", "", canon.upper())
    return f"{SESSION_ID}_{compact}__"

def get_paths_for(patent_code: str) -> dict[str, Path]:
    """
    Return the primary/secondary/html Paths and the prefix
    for a given patent code and this SESSION_ID.
    """
    prefix = make_session_prefix_for(patent_code)
    return {
        "primary":   PRIMARY_DIR   / f"{prefix}rag_search_from_patent_abstract_results_with_connections.csv",
        "secondary": SECONDARY_DIR / f"{prefix}rag_search_second_connections.csv",
        "html":      HTML_DIR      / f"{prefix}patent_connection_network.html",
        "prefix":    prefix,
    }

# Helper for buidling output zip file

def build_outputs_zip(started_ts: float):
    """
    Collect all artifacts from the last run into an in-memory ZIP.
    Only files whose mtime is >= started_ts are included.
    Returns bytes or None if nothing was added.
    """
    if not started_ts:
        return None

    # We need the patent used for the last run to derive the prefix/paths
    run_patent = st.session_state.get("run_patent")
    if not run_patent:
        return None

    paths = get_paths_for(run_patent)
    primary   = paths["primary"]
    secondary = paths["secondary"]
    html      = paths["html"]
    prefix    = paths["prefix"]

    buf = io.BytesIO()
    added = False

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def add_if_fresh(path: Path):
            nonlocal added
            try:
                if path.exists() and path.stat().st_mtime >= started_ts:
                    zf.write(path, path.name)
                    added = True
            except Exception:
                # Fail-soft: just skip any problematic file
                pass

        # CSVs
        add_if_fresh(primary)
        add_if_fresh(secondary)
        # Network HTML
        add_if_fresh(html)
        # Visuals: any PNGs for this <SESSION_ID>_<PATENT>__ from both levels
        for vis_dir in (VISUALS_DIR_L1, VISUALS_DIR_L2):
            try:
                if vis_dir.exists():
                    for fname in os.listdir(vis_dir):
                        if not fname.lower().endswith(".png"):
                            continue
                        if not fname.startswith(prefix):
                            continue
                        add_if_fresh(vis_dir / fname)
            except Exception:
                # Fail-soft: just skip any problematic directory
                pass

    if not added:
        return None

    buf.seek(0)
    return buf.getvalue()


# Helpers - Batch 1
# ---------- DOM helpers for label/value tables on Google Patents ----------
def _select_texts(soup, selectors: list[str]) -> list[str]:
    """Collect non-empty texts for a list of CSS selectors; de-duplicate, keep order."""
    seen, out = set(), []
    for sel in selectors:
        for el in soup.select(sel):
            txt = el.get_text(" ", strip=True)
            if txt and txt not in seen:
                seen.add(txt); out.append(txt)
    return out

def _find_by_label(soup, labels: list[str]) -> str | None:
    """
    Find a label (dt/th/span/div) whose text contains any of the given labels (case-insensitive),
    then return the text of its next dd/td/span/div.
    """
    lab = soup.find(
        lambda t: t and t.name in ("dt", "th", "span", "div")
        and any(lbl in t.get_text(" ", strip=True).lower() for lbl in labels)
    )
    if not lab:
        return None
    val = lab.find_next(lambda x: x and x.name in ("dd", "td", "span", "div"))
    if not val:
        return None
    txt = val.get_text(" ", strip=True)
    return txt or None

def _find_list_by_label(soup, labels: list[str]) -> list[str]:
    """Label→value, then split into a list by common delimiters."""
    txt = _find_by_label(soup, labels)
    if not txt:
        return []
    parts = [p.strip() for p in re.split(r"(?:\s*[;,•]\s*|\s+and\s+)", txt) if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

def _extract_current_assignee_from_dom(soup) -> list[str]:
    """Specific convenience for 'Current assignee' if JSON-LD lacks it."""
    hits = _select_texts(soup, [
        '[itemprop="assigneeCurrent"]',
        '[itemprop="assignee-current"]',
        '[itemprop="currentAssignee"]',
    ])
    if hits:
        return hits
    hits = _find_list_by_label(soup, ["current assignee"])
    return hits

# ---------------- Google Patents: fetch & render ----------------
@st.cache_data(ttl=24*60*60, show_spinner=False)
def _fetch_patent_summary_from_google(patent_code: str) -> Optional[Dict[str, Any]]:
    """
    Fetch title, abstract, identifiers, dates, inventors, assignees, and CURRENT assignees
    from Google Patents. Tries JSON-LD first, then meta, then visible DOM labels.
    Accepts 'US-9872293-B1' or 'US9872293B1'.
    """
    if requests is None or BeautifulSoup is None:
        return None

    def _norm_list(x):
        if not x:
            return []
        items = x if isinstance(x, (list, tuple)) else [x]
        out = []
        for it in items:
            if isinstance(it, dict):
                name = it.get("name") or it.get("legalName") or it.get("givenName")
                if name:
                    out.append(str(name))
            elif isinstance(it, str):
                s = it.strip()
                if s:
                    out.append(s)
        return out

    code = patent_code.upper().replace(" ", "")
    code_compact = re.sub(r"[^A-Z0-9]", "", code)
    candidates = [
        f"https://patents.google.com/patent/{code_compact}/en",
        f"https://patents.google.com/patent/{code_compact}",
        f"https://patents.google.com/patent/{code}/en",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NASA-TTO-Streamlit)"}

    for url in candidates:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")

            # ---------- 1) Prefer JSON-LD ----------
            info: Dict[str, Any] | None = None
            for tag in soup.find_all("script", {"type": "application/ld+json"}):
                try:
                    payload = json.loads(tag.text)
                except Exception:
                    continue
                items = payload if isinstance(payload, list) else [payload]
                for obj in items:
                    if not isinstance(obj, dict):
                        continue
                    if ("publicationNumber" in obj) or ("applicationNumber" in obj) or (obj.get("@type") == "Patent"):
                        inventors = _norm_list(obj.get("inventor") or obj.get("inventors"))
                        assignees = _norm_list(obj.get("assigneeOriginal") or obj.get("assignee") or obj.get("assignees"))
                        assignees_cur = _norm_list(
                            obj.get("assigneeCurrent")
                            or obj.get("currentAssignee")
                            or obj.get("assigneeCurrentOriginal")
                        )
                        info = {
                            "title":             obj.get("name") or obj.get("headline"),
                            "abstract":          (obj.get("abstract") or obj.get("description") or "").strip(),
                            "publicationNumber": obj.get("publicationNumber"),
                            "applicationNumber": obj.get("applicationNumber"),
                            "grantNumber":       obj.get("publicationNumber") if obj.get("isPatentGrant") else None,
                            "filingDate":        obj.get("filingDate") or obj.get("datePublished"),
                            "publicationDate":   obj.get("publicationDate") or obj.get("datePublished"),
                            "grantDate":         obj.get("publicationDate") if obj.get("isPatentGrant") else None,
                            "inventors":         inventors,
                            "assignees":         assignees,
                            "assigneesCurrent":  assignees_cur,  # NEW
                            "url":               url,
                        }
                        break  # take the first viable JSON-LD block

            # ---------- 2) Fallback: meta tags (minimal but fast) ----------
            def _meta(name):
                el = soup.find("meta", attrs={"name": name})
                return el.get("content").strip() if el and el.get("content") else None

            if not info:
                title = _meta("DC.title")
                abstract = _meta("DC.description")
                info = {
                    "title":             title,
                    "abstract":          abstract,
                    "publicationNumber": None,
                    "applicationNumber": None,
                    "grantNumber":       None,
                    "filingDate":        _meta("citation_date") or _meta("DC.date"),
                    "publicationDate":   _meta("DC.date"),
                    "grantDate":         None,
                    "inventors":         [],
                    "assignees":         [],
                    "assigneesCurrent":  [],  # NEW
                    "url":               url,
                }

            # ---------- 3) If any fields are still missing, patch from visible DOM ----------
            # IDs
            if not info.get("publicationNumber"):
                info["publicationNumber"] = _find_by_label(soup, ["publication number"])
            if not info.get("applicationNumber"):
                info["applicationNumber"] = _find_by_label(soup, ["application number", "application no"])
            if not info.get("grantNumber"):
                # Some pages label simply "Patent number" for grants
                info["grantNumber"] = _find_by_label(soup, ["grant number", "patent number"])

            # Dates
            if not info.get("filingDate"):
                info["filingDate"] = _find_by_label(soup, ["filed", "filing date"])
            if not info.get("publicationDate"):
                info["publicationDate"] = _find_by_label(soup, ["published", "publication date"])
            if not info.get("grantDate"):
                info["grantDate"] = _find_by_label(soup, ["granted", "grant date"])

            # People / Orgs
            if not info.get("inventors"):
                # Try itemprops first, then label
                inv = _select_texts(soup, ['[itemprop="inventor"]', '[itemprop="inventor"] a'])
                if not inv:
                    inv = _find_list_by_label(soup, ["inventor", "inventors"])
                info["inventors"] = inv

            if not info.get("assignees"):
                ass = _select_texts(soup, ['[itemprop="assigneeOriginal"]', '[itemprop="assignee"]'])
                if not ass:
                    ass = _find_list_by_label(soup, ["assignee", "assignees", "original assignee"])
                info["assignees"] = ass

            if not info.get("assigneesCurrent"):
                info["assigneesCurrent"] = _extract_current_assignee_from_dom(soup)

            # If we have at least a title or abstract, treat as success
            if any([info.get("title"), info.get("abstract")]):
                return info

        except Exception:
            continue

    return None

def render_patent_header_summary(patent_code: str):
    """Render a clean, non-dropdown summary: CODE : TITLE, Abstract, and key fields."""
    canon = to_canonical_patent(patent_code)
    data = _fetch_patent_summary_from_google(canon)
    
    # graceful fallbacks
    title     = (data or {}).get("title") or ""
    abstract  = ((data or {}).get("abstract") or "").strip()
    pub_no    = (data or {}).get("publicationNumber") or "—"
    app_no    = (data or {}).get("applicationNumber") or "—"
    grant_no  = (data or {}).get("grantNumber") or "—"
    filed     = (data or {}).get("filingDate") or "—"
    published = (data or {}).get("publicationDate") or "—"
    granted   = (data or {}).get("grantDate") or "—"
    inventors = ", ".join((data or {}).get("inventors") or []) or "—"
    assignees = ", ".join((data or {}).get("assignees") or []) or "—"
    current_assignees = ", ".join((data or {}).get("assigneesCurrent") or []) or "—"
    url       = (data or {}).get("url")

    header = f"{canon} : {title}" if title else canon

    # Card
    with st.container(border=True):
        # larger header
        st.markdown(f"## {header}")

        # abstract (no dropdown)
        if abstract:
            st.markdown("**Abstract:**")
            st.markdown(abstract)

        # details in two columns
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"- **Publication:** {pub_no}")
            st.markdown(f"- **Application:** {app_no}")
            st.markdown(f"- **Grant:** {grant_no}")
            st.markdown(f"- **Inventor(s):** {inventors}")
            st.markdown(f"- **Current assignee(s):** {current_assignees}")
            
        with c2:
            st.markdown(f"- **Filed:** {filed}")
            st.markdown(f"- **Published:** {published}")
            st.markdown(f"- **Granted:** {granted}")
            if url:
                st.markdown(f"- **Google Patents:** [{url}]({url})")
            
# ------------- Short process explainer (for left panel) -------------
def render_pipeline_explainer():
    st.subheader("How these results are generated:")

    # Short narrative intro
    st.markdown(
        "When you click **Run Search**, the app looks up the patent you entered, "
        "uses its text (mainly the abstract) to understand what it’s about, then finds "
        "other patents with the most similar language and topics. The goal is to quickly surface "
        "related prior art and nearby ideas—not to judge novelty or legal status."
    )

    # Clear, step-by-step bullets
    st.markdown(
        """
- **Step 1 - Get the context.** We fetch the patent’s page on Google Patents to capture its title, key numbers, dates, and the **abstract** (the short technical summary in plain text).
- **Step 2 - Turn text into numbers.** The abstract is converted into a compact **vector** (a list of numbers) using a sentence-embedding model (e.g., *MiniLM-L6-v2*). This gives the patent a mathematical “fingerprint.”
- **Step 3 - Search the vector index.** We query a prebuilt **FAISS (IVFPQ)** index of patent embeddings to find the **Top-K nearest neighbors**—i.e., patents whose fingerprints are closest to the searched one.
- **Step 4 - Score and organize.** Matches are ranked by a **similarity score (0 to 1)**. Higher scores usually mean the patents discuss very similar concepts or wording.
- **Step 5 - Expand connections.** From the top matches, we optionally pull **second-level connections** (patents connected to those primaries) to reveal clusters and thematic neighborhoods.
- **Step 6 - Package the outputs.** We save:
  - **Primary connections** (CSV),
  - **Second-level connections** (CSV, when found),
  - **Visuals** (e.g., score distribution, topic clustering),
  - and an **interactive network** (HTML) so you can explore relationships.
        """
    )

    # Helpful notes
    st.caption(
        "Tips: A larger **Top-K** finds more neighbors (broader exploration) but may include weaker matches. "
        "Results reflect text similarity on the indexed corpus; they are not legal opinions."
    )

# Where executed notebooks will be saved
RUNS_DIR = Path(__file__).parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# ---- GLOBAL CONCURRENCY SETTINGS ----
# Maximum number of papermill engine runs allowed simultaneously on this Vertex instance.
# Tune this depending on RAM/CPU. For testing you might set 1 or 2; later you can increase.
MAX_CONCURRENT_RUNS = 2  # <<< ADJUST THIS NUMBER AS NEEDED

# Simple global FIFO queue file (shared by all sessions)
QUEUE_FILE = RUNS_DIR / "run_queue.json"

# ---- Per-session manifest (one file per SESSION_ID) ----
MANIFEST = RUNS_DIR / f"run_manifest_{SESSION_ID}.json"


def _read_manifest():
    try:
        import json
        return json.loads(MANIFEST.read_text())
    except Exception:
        return None

def _write_manifest(d: dict):
    try:
        import json
        MANIFEST.write_text(json.dumps(d, indent=2, sort_keys=True))
    except Exception:
        pass

def _clear_manifest():
    try:
        if MANIFEST.exists():
            MANIFEST.unlink()
    except Exception:
        pass

# ---- GLOBAL QUEUE & RUNNING-JOBS HELPERS ----

def _read_global_queue() -> list[str]:
    """Read the global FIFO queue of SESSION_IDs from QUEUE_FILE."""
    try:
        data = json.loads(QUEUE_FILE.read_text())
        if isinstance(data, list):
            # Keep only string session IDs
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def _write_global_queue(queue: list[str]) -> None:
    """Persist the global queue back to disk."""
    try:
        QUEUE_FILE.write_text(json.dumps(queue, indent=2))
    except Exception:
        pass


def _remove_from_queue(session_id: str) -> None:
    """Remove a SESSION_ID from the global queue if present."""
    q = _read_global_queue()
    new_q = [sid for sid in q if sid != session_id]
    if new_q != q:
        _write_global_queue(new_q)


def _count_running_jobs() -> int:
    """
    Count how many jobs are currently marked as 'running' in all manifests,
    and opportunistically fix any stale manifests where the PID is no longer alive.
    """
    running = 0
    for mf in RUNS_DIR.glob("run_manifest_*.json"):
        try:
            data = json.loads(mf.read_text())
        except Exception:
            continue

        if data.get("status") != "running":
            continue

        pid = data.get("pid")
        if not pid:
            continue

        # Check if process is still alive
        if _is_pid_alive(pid):
            running += 1
        else:
            # Process is dead but manifest still says running → mark as done
            data["status"] = "done"
            data["ended_ts"] = time.time()
            try:
                mf.write_text(json.dumps(data, indent=2, sort_keys=True))
            except Exception:
                pass

    return running


def _maybe_start_queued_job():
    """
    For this SESSION_ID:
      - If we're marked as queued,
      - and we're at the head of the global queue,
      - and there is a free slot (running < MAX_CONCURRENT_RUNS),
    then start the engine run and remove us from the queue.
    """
    if not st.session_state.get("queued"):
        return

    queue = _read_global_queue()
    if not queue:
        return

    # Not our turn yet
    if queue[0] != SESSION_ID:
        return

    # Check global concurrency
    if _count_running_jobs() >= MAX_CONCURRENT_RUNS:
        return

    # We are at head and there is capacity → start our job
    patent = st.session_state.get("queued_patent")
    search_type = st.session_state.get("queued_search_type")
    top_k = st.session_state.get("queued_top_k", 100)

    # If we somehow lost the parameters, just dequeue and exit
    if not patent or not search_type:
        _remove_from_queue(SESSION_ID)
        st.session_state["queued"] = False
        return

    # Remove ourselves from the queue, clear queued flag, start run
    _remove_from_queue(SESSION_ID)
    st.session_state["queued"] = False
    start_engine_run(patent, search_type, top_k)

    # Immediately re-render in "running" view
    st.rerun()



def _rehydrate_from_manifest():
    m = _read_manifest()
    if not m:
        return
    pid = m.get("pid")
    started = float(m.get("started_ts", 0))
    status = m.get("status", "running")

    # If still running → reattach (single-run invariant)
    if status == "running" and pid and _is_pid_alive(pid):
        st.session_state["run_pid"] = int(pid)
        st.session_state["job_started_ts"] = started
        if m.get("log_path"):
            st.session_state["run_log"] = m["log_path"]
        if m.get("patent"):
            st.session_state["run_patent"] = m["patent"]
        return

    # Not running anymore → clear manifest so page opens fresh
    _clear_manifest()
    # Do NOT set any of: _last_run, _last_run_started_ts, run_patent, etc.
    return


def _is_pid_alive(pid: int) -> bool:
    """Best-effort check: reap child if it's finished, else fall back to kill(0)."""
    try:
        # If it's our child, this returns immediately with (pid, status) when finished.
        finished_pid, _ = os.waitpid(int(pid), os.WNOHANG)
        if finished_pid == int(pid):
            return False
    except ChildProcessError:
        # Not our child (or already reaped) → fall through to kill(0)
        pass
    except Exception:
        pass

    try:
        os.kill(int(pid), 0)          # raises if no such process
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                    # exists but not ours
    except Exception:
        return True
    else:
        return True

### Background cleanup for stale runs
@st.cache_resource
def start_cleanup_thread():
    import threading, json as _json, time as _time

    def _cleanup_loop():
        while True:
            _time.sleep(60)  # run once per minute
            try:
                for mf in RUNS_DIR.glob("run_manifest_*.json"):
                    try:
                        data = _json.loads(mf.read_text())
                    except Exception:
                        continue

                    # Only care about genuinely running jobs
                    if data.get("status") != "running":
                        continue

                    pid = data.get("pid")
                    last_ping = float(data.get("last_ping_ts", data.get("started_ts", 0)))
                    if not pid or not last_ping:
                        continue

                    # No heartbeat for 5 minutes → treat as stale and kill
                    if _time.time() - last_ping > 300:
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGTERM)
                            _time.sleep(1.0)
                            if _is_pid_alive(pid):
                                os.killpg(pgid, signal.SIGKILL)
                        except Exception:
                            pass
                        data["status"] = "timeout"
                        data["ended_ts"] = _time.time()
                        try:
                            mf.write_text(_json.dumps(data, indent=2, sort_keys=True))
                        except Exception:
                            pass
            except Exception:
                # Never crash the app due to cleanup issues
                continue

    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()
    return True

# Start the cleanup thread once per process
start_cleanup_thread()

def cancel_running_proc() -> bool:
    """Hard-kill the papermill process group and clear run state (no file deletion)."""
    pid = st.session_state.get("run_pid")
    if not pid:
        return False
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(1.0)
        if _is_pid_alive(pid):
            os.killpg(pgid, signal.SIGKILL)
    except Exception:
        pass
    st.session_state.pop("run_pid", None)
    st.session_state.pop("job_started_ts", None)

    # Update manifest
    m = _read_manifest()
    if m and m.get("status") == "running":
        m["status"] = "canceled"
        m["ended_ts"] = time.time()
        _write_manifest(m)

    return True


def start_engine_run(patent: str, search_type: str, top_k: int):
    # stop any existing run (no file deletions)
    cancel_running_proc()

    # map “ALL” (we use -1) or any non-positive to a big safety cap
    eff_top_k = TOPK_MAX_CAP if int(top_k) < 1 else int(top_k)

    prefix_for_run = make_session_prefix_for(patent)
    run_id = prefix_for_run  # include SESSION_ID + normalized patent in the run_id
    out_nb = RUNS_DIR / f"exec_{prefix_for_run}.ipynb"

    cmd = [
        sys.executable, "-m", "papermill",
        str(ENGINE_NOTEBOOK), str(out_nb),
        "-p", "PATENT_TO_SEARCH",         patent,
        "-p", "SEARCH_TYPE",              search_type,
        "-p", "TOP_K_RESULTS",            str(eff_top_k),
        "-p", "SESSION_ID",               SESSION_ID,        # Tie notebook to this session
        "-p", "SESSION_PREFIX",           prefix_for_run,
        "-k", "python3",  # change if your kernel name differs
    ]


    # --- NEW: capture stdout/stderr to a log file and start a new process group
    log_path = RUNS_DIR / f"exec_{prefix_for_run}.log"
    log_f = open(log_path, "wb")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ENGINE_DIR),
        stdout=log_f,
        stderr=log_f,
        preexec_fn=os.setsid,  # new process group → cancel works
    )
    # Parent can close its handle; child keeps the fd
    try:
        log_f.close()
    except Exception:
        pass

    # Session state for reattach + UI
    st.session_state["run_pid"] = int(proc.pid)
    st.session_state["job_started_ts"] = time.time()
    st.session_state["run_log"] = str(log_path)
    st.session_state["run_patent"] = patent
    st.session_state.pop("_err", None)

    # --- NEW: persist a manifest so refresh/reopen can reattach
    manifest = {
        "run_id": run_id,
        "session_id": SESSION_ID,   # Trace which session owns this run
        "session_prefix": prefix_for_run,
        "pid": int(proc.pid),
        "started_ts": st.session_state["job_started_ts"],
        "patent": patent,
        "search_type": search_type,
        "top_k": eff_top_k,
        "status": "running",
        "log_path": str(log_path),
    }

    # Persist manifest so refresh/reopen in THIS session can reattach
    _write_manifest(manifest)

def schedule_or_start_run(patent: str, search_type: str, top_k: int) -> str:
    """
    Decide whether to start the engine immediately or enqueue this SESSION_ID.
    Returns:
        "started" if the run started right away
        "queued"  if the run was placed into the queue
    """
    # Remember intended run parameters in this session so we can start later when dequeued
    st.session_state["queued_patent"] = patent
    st.session_state["queued_search_type"] = search_type
    st.session_state["queued_top_k"] = top_k

    # Ensure we are not duplicated in the queue
    _remove_from_queue(SESSION_ID)

    running_now = _count_running_jobs()
    if running_now < MAX_CONCURRENT_RUNS:
        # Start immediately
        st.session_state["queued"] = False
        start_engine_run(patent, search_type, top_k)
        return "started"
    else:
        # No capacity → enqueue this session
        q = _read_global_queue()
        if SESSION_ID not in q:
            q.append(SESSION_ID)
            _write_global_queue(q)
        st.session_state["queued"] = True
        return "queued"


# --------- Page / Theme ---------
st.set_page_config(page_title="NASA TTO Patent Matching Tool", page_icon="🛰️", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
h1, h2, h3 { line-height: 1.1; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Increase the top inner padding of the main page container */
.block-container { padding-top: 2.2rem; }  /* try 2.2–3.0rem */
</style>
""", unsafe_allow_html=True)


def make_hero_css(img_path: str, height_px: int = 300, max_w: int = 1600, jpeg_quality: int = 82) -> str:
    """
    Builds CSS for the top hero:
      - resizes the image (max_w) and compresses (jpeg_quality) to keep it light
      - anchors the photo to the TOP (no stretch; uses cover)
      - left-to-right black fade so the NASA logo/text stay readable
    """
    p = Path(img_path)
    # --- load + resize + compress (to JPEG always for small size) ---
    img = Image.open(p).convert("RGB")
    if img.width > max_w:
        h = int(img.height * (max_w / img.width))
        img = img.resize((max_w, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    mime = "image/jpeg"

    return f"""
<style>
/* Full-width hero inside the Streamlit content area */
.hero-wrap {{
  width: 100%;
  height: {height_px}px;
  border-radius: 14px;
  overflow: hidden;
  margin: 6px 0 0 0;                 /* no gap above the divider area */
}}
.hero-bg {{
  width: 100%; height: 100%;
  background:
    /* slightly lighter fade so the image is visible */
    linear-gradient(90deg, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.48) 34%, rgba(0,0,0,0.00) 58%),
    url("data:{mime};base64,{b64}");
  background-size: cover;             /* no stretch; crop if needed */
  background-position: top 22% center;   /* or: center 20% */
  background-repeat: no-repeat;
}}
.hero-inner {{
  height: 100%;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px;
  color: #fff;
}}
.hero-logo  {{ width: 240px; max-width: 75vw; }}
.hero-title {{ font-size: 42px; font-weight: 720; line-height: 1.1; margin: 0; }}
.hero-title {{ font-size: 42px; font-weight: 720; line-height: 1.1; margin: 0; }}
.hero-title--sm  {{
  font-size: 36px;                 /* or: clamp(18px, 2.2vw, 26px) */
  font-weight: 640;
  line-height: 1.15;
  margin-top: 2px;
}}
@media (min-width: 900px) {{
  .hero-title--sm {{ font-size: 26px; }}
}}

.hero-sub   {{ opacity: .95; margin-top: 8px; }}
@media (max-width: 680px) {{
  .hero-title {{ font-size: 22px; }}
  .hero-logo  {{ width: 80px; }}
}}
/* tuck the divider right under the hero with no extra gap */
.hero-wrap + .st-emotion-cache-hr {{}}
</style>
"""
# --------- Header (hero background behind NASA logo + title) ---------
NASA_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/NASA_logo.svg/512px-NASA_logo.svg.png"

# image is in the same folder as config.toml (streamlit/)
HERO_DIR = (
    Path(os.environ.get("STREAMLIT_CONFIG")).parent
    if os.environ.get("STREAMLIT_CONFIG")
    else Path(__file__).parent / "streamlit"
)
HERO_IMAGE = HERO_DIR / "header_1.jpg"   # <-- change to your actual filename

if HERO_IMAGE.exists():
    st.markdown(make_hero_css(str(HERO_IMAGE), height_px=300), unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="hero-wrap">
          <div class="hero-bg">
            <div class="hero-inner">
              <img class="hero-logo" src="{NASA_LOGO_URL}" alt="NASA logo"/>
              <div>
                <div class="hero-title">NASA Technology Transfer Office</div>
                 <div class="hero-title hero-title--sm">AI Tool for Patent Matching</div>
                <div class="hero-sub">
                  Enter details on the left, click <b>Run Search</b>, and see results on the right.<br/>
                  </div>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.warning(f"Hero image not found at: {HERO_IMAGE}")

st.divider()  # sits immediately below the hero band

# --------- Helpers ---------
# Accept: CC<digits><2-chars>, with optional dashes (CC-<digits>-<2chars>)
_PATTERN_OPEN = re.compile(r"^[A-Za-z]{2}-?\d+-?[A-Za-z0-9]{2}$")

def valid_patent(s: str) -> bool:
    s = (s or "").strip()
    return bool(_PATTERN_OPEN.match(s))

def to_canonical_patent(s: str) -> str:
    """
    Normalize to 'CC-<digits>-<2chars>' (uppercase), or return the original if invalid.
    """
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s).upper()
    m = re.match(r"^([A-Z]{2})-?(\d+)-?([A-Z0-9]{2})$", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else s


def show_csv(path: Path, title: str):
    st.markdown(f"### {title}")
    if path.exists():
        df = pd.read_csv(path)
        st.dataframe(df, use_container_width=True)
        # (no download button by request)
    else:
        st.info(f"Missing: `{path.name}`")

def show_image(path: Path, caption: str):
    if path.exists(): st.image(str(path), use_container_width=True, caption=caption)
    else: st.info(f"Missing: `{path.name}`")

def show_html(path: Path, height: int = 720):
    if path.exists():
        components.html(path.read_text(encoding="utf-8", errors="ignore"), height=height, scrolling=True)
    else:
        st.info(f"Missing: `{path.name}`")

def list_session_images(vis_dir: Path, started_ts: float) -> list[Path]:
    """Return all PNGs in vis_dir for this <SESSION_ID>_<PATENT>__ updated on/after started_ts."""
    run_patent = st.session_state.get("run_patent")
    if not run_patent:
        return []

    prefix = get_paths_for(run_patent)["prefix"]
    out: list[Path] = []
    try:
        if vis_dir.exists():
            for fname in sorted(os.listdir(vis_dir)):
                if not fname.lower().endswith(".png"):
                    continue
                if not fname.startswith(prefix):
                    continue
                p = vis_dir / fname
                try:
                    if p.stat().st_mtime >= started_ts:
                        out.append(p)
                except Exception:
                    continue
    except Exception:
        pass
    return out


# --- Similarity legend + image swatch indicator (keeps native st.dataframe scroll + menu) ---
import base64, io
from PIL import Image, ImageDraw

# Colors tuned for dark theme (two distinct greens)
COLOR_RED   = "#DC2626"   # < 0.6
COLOR_YELL  = "#F59E0B"   # 0.6–0.8
COLOR_YGRN  = "#A3E635"   # 0.8–0.9 (yellowish green)
COLOR_GRN   = "#22C55E"   # > 0.9   (bright green)

def _score_color(v: float) -> str:
    # Treat None / "None" / NaN / non-numeric as RED
    try:
        if v is None:
            return COLOR_RED
        # handle strings like "None" or ""
        if isinstance(v, str) and v.strip().lower() in {"", "none","None", "Nan", "nan"}:
            return COLOR_RED
        s = float(v)
        # NaN check: NaN != NaN
        if s != s:
            return COLOR_RED
    except Exception:
        return COLOR_RED

    if s <= 0.6:  return COLOR_RED
    if s <= 0.8:  return COLOR_YELL
    if s <= 0.9:  return COLOR_YGRN
    return COLOR_GRN


def _swatch_base64(hex_color: str, w: int = 90, h: int = 24, radius: int = 6) -> str:
    """Return a data URI for a rounded-rectangle color swatch."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(0, 0), (w-1, h-1)], radius=radius, fill=hex_color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

# cache swatches so we don’t regenerate per row
_SWATCH_CACHE = {
    COLOR_RED:  _swatch_base64(COLOR_RED),
    COLOR_YELL: _swatch_base64(COLOR_YELL),
    COLOR_YGRN: _swatch_base64(COLOR_YGRN),
    COLOR_GRN:  _swatch_base64(COLOR_GRN),
}

def add_similarity_swatch(df):
    """Add a 'Match' image column right after Rank (or at index 0 if no Rank)."""
    d = df.copy()
    if "Similarity_Score" in d.columns:
        sw = d["Similarity_Score"].map(lambda v: _SWATCH_CACHE[_score_color(v)])
        insert_at = 1 if "Rank" in d.columns else 0
        d.insert(insert_at, "Match", sw)
    return d

def render_similarity_legend():
    st.markdown(
        """
<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;">
  <div style="display:flex;align-items:center;gap:8px;">
    <span style="display:inline-block;width:28px;height:14px;background:#DC2626;border-radius:4px;"></span>
    <span style="opacity:0.9;">&lt; 0.6</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;">
    <span style="display:inline-block;width:28px;height:14px;background:#F59E0B;border-radius:4px;"></span>
    <span style="opacity:0.9;">0.6–0.8</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;">
    <span style="display:inline-block;width:28px;height:14px;background:#A3E635;border-radius:4px;"></span>
    <span style="opacity:0.9;">0.8–0.9</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;">
    <span style="display:inline-block;width:28px;height:14px;background:#22C55E;border-radius:4px;"></span>
    <span style="opacity:0.9;">&gt; 0.9</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


# --------- Two-column layout (Left = inputs; Right = outputs) ---------
#left, right = st.columns([0.36, 0.64], gap="large")
LEFT_RATIO, DIVIDER_RATIO, RIGHT_RATIO = 0.30, 0.02, 0.68
left, divider, right = st.columns([LEFT_RATIO, DIVIDER_RATIO, RIGHT_RATIO], gap="large")

# draw a subtle vertical divider
with divider:
    st.markdown(
        '<div style="border-left:1px solid #2a2f3a; height: 500vh; opacity: 0.9;"></div>',
        unsafe_allow_html=True
    )


with left:
    st.subheader("Input")

    patent = st.text_input(
        "Document Code (CC-<digits>-<2 alphanumerics>)",
        placeholder="EP-1234567-A1  or  ep1234567a1",
        help="Two-letter prefix (any country), any number of digits, two-character alphanumeric suffix. Dashes optional."
    ).strip().upper()
    if patent and not valid_patent(patent):
        st.error("Invalid format. Examples: EP-1234567-A1, US1234567B2, WO-2020-123456-A1")

    search_type = st.selectbox("Search Type", ["publication", "application", "auto"], index=2)
    st.markdown("**Results to retrieve (Top-K)**")
    k_mode = st.radio(
        "How many neighbors to fetch?",
        ["Set a number", "All"],
        horizontal=True,
        label_visibility="collapsed",
        key="k_mode"
    )
    if k_mode == "Set a number":
        top_k = int(st.number_input(
            "Top-K",
            min_value=1, max_value=TOPK_MAX_CAP, value=100, step=1,
            key="topk_num"
        ))
    else:
        top_k = -1   # “ALL”; mapped to TOPK_MAX_CAP in start_engine_run()

    st.markdown("—")
    c1, c2 = st.columns([1,1])
    with c1:
        run_clicked = st.button("Run Search", type="primary", use_container_width=True, disabled=not valid_patent(patent))
    with c2:
        if st.button("Clear", use_container_width=True):
            for k in ["_last_run", "_last_run_started_ts", "_last_run_ended_ts", "_err"]:
                st.session_state.pop(k, None)
            # reset Top-K widgets to defaults
            st.session_state.update({
                "k_mode": "Set a number",
                "topk_num": 100,
            })
            # (optional) reset other inputs if they use keys:
            # st.session_state.update({"inp_patent": "", "inp_search": "auto"})
            st.rerun()
    if "_last_run" in st.session_state:
        render_pipeline_explainer()

st.markdown("---")

with right:
    st.subheader("Output")

    # 0) Reattach to a running or completed job on refresh/open (one time)
    if "rehydrated" not in st.session_state:
        _rehydrate_from_manifest()
        st.session_state["rehydrated"] = True
    
    # If nothing is running after rehydrate, wipe stale output state (only once per fresh page load)
    if (
        st.session_state.get("rehydrated")
        and not st.session_state.get("run_pid")
        and not st.session_state.get("_did_initial_cleanup")
    ):
        for k in ["_last_run", "_last_run_started_ts", "_last_run_ended_ts", "run_patent", "run_log"]:
            st.session_state.pop(k, None)
        st.session_state["_did_initial_cleanup"] = True

    # If this session has a queued job, check if it is now at the head of the queue
    # and there is global capacity to start it.
    _maybe_start_queued_job()

    
    # 1) Launch or queue a fresh run when Run is clicked
    if run_clicked:
        for k in ["_err", "_last_run"]:
            st.session_state.pop(k, None)
        canon = to_canonical_patent(patent)

        status = schedule_or_start_run(canon, search_type, top_k)

        # In both cases we rerun:
        # - "started": we will show the running panel
        # - "queued": we will show the queue status panel
        st.rerun()  # go into "running" or "queued" view immediately


    # 2) While the process is running, show the running panel + a real Cancel
    pid = st.session_state.get("run_pid")
    if pid and _is_pid_alive(pid):
        # heartbeat so cleanup thread knows this session is alive
        m = _read_manifest()
        if m and m.get("status") == "running":
            m["last_ping_ts"] = time.time()
            _write_manifest(m)

        # Refresh every 10s so elapsed time + status stay live
        try:
            st_autorefresh(interval=10_000, key="run_refresh")
        except Exception:
            pass

        elapsed = int(time.time() - st.session_state.get("job_started_ts", time.time()))
        m, s = divmod(elapsed, 60)
        dots = "." * (1 + (elapsed % 3))

        rowL, rowR = st.columns([0.72, 0.28], gap="small")
        
        with rowL:
            st.markdown(
                f"""
                <div class="run-panel">
                  <div class="spin"></div>
                  <div>Running the core similarity search model{dots} • Elapsed {m:02d}:{s:02d}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with rowR:
            if st.button("Cancel run", type="secondary", use_container_width=True):
                canceled = cancel_running_proc()

                # Prevent any success rendering from a previous run
                for k in ["_last_run", "_last_run_started_ts", "_last_run_ended_ts", "run_patent", "run_log"]:
                    st.session_state.pop(k, None)

                # Delete this session's manifest so refresh shows clean page
                try:
                    if MANIFEST.exists():
                        MANIFEST.unlink()
                except Exception:
                    pass

                st.session_state["_err"] = "Run canceled by user." if canceled else "No active run."
                st.rerun()
     
        # keep-alive if still genuinely running and no outputs yet
        time.sleep(10)
        st.rerun()
        st.stop()

    # 3) If the process ended, mark success and remember when it started
    if pid and not _is_pid_alive(pid):
        started_ts = st.session_state.get("job_started_ts", 0)
        ended_ts = time.time()
    
        st.session_state.pop("run_pid", None)
        st.session_state["_last_run_started_ts"] = started_ts
        st.session_state["_last_run_ended_ts"] = ended_ts
        st.session_state["_last_run"] = str(int(ended_ts))
        
        # Persist completion in manifest
        m = _read_manifest()
        if m:
            m["status"] = "done"
            m["ended_ts"] = ended_ts
            _write_manifest(m)
        
        st.success("Done.")
        st.rerun()

    # 3b) If we are queued (no active PID), show queue status
    elif st.session_state.get("queued"):
        queue = _read_global_queue()
        position = None
        try:
            position = queue.index(SESSION_ID) + 1 if SESSION_ID in queue else None
        except ValueError:
            position = None

        # Auto-refresh so we can start when our turn comes
        try:
            st_autorefresh(interval=10_000, key="queue_refresh")
        except Exception:
            pass

        msg = "Your search is queued and will start automatically when resources are available."
        if position is not None:
            msg = f"Your search is queued (position #{position}). It will start automatically when a slot is free."

        st.info(msg)

        # Allow user to cancel their queued job
        if st.button("Cancel queued run", type="secondary", use_container_width=False):
            _remove_from_queue(SESSION_ID)
            st.session_state["queued"] = False
            for k in ["queued_patent", "queued_search_type", "queued_top_k"]:
                st.session_state.pop(k, None)
            st.rerun()


    # 4) Error path
    if "_err" in st.session_state:
        st.error(f"Model execution failed: {st.session_state['_err']}")
        if st.checkbox("Show troubleshooting tips"):
            st.markdown(
                "- Ensure your model writes outputs to the expected filenames.\n"
                "- Confirm required packages are installed.\n"
                "- Open the executed model under the `runs/` folder to see cell errors."
            )

    # 5) Success path: render artifacts (only those written by this run)
    elif "_last_run" in st.session_state:
        started_ts = st.session_state.get("_last_run_started_ts", 0)
        # Ensure we are not marked as queued after a completed run
        st.session_state["queued"] = False
        
        # Determine which patent this completed run used
        run_code = st.session_state.get("run_patent") or patent
        paths = get_paths_for(run_code)
        PRIMARY_CSV   = paths["primary"]
        SECONDARY_CSV = paths["secondary"]
        HTML_NETWORK  = paths["html"]
    
        # Freshness per artifact (mtime must be >= run start)
        def fresh(p: Path) -> bool:
            try:
                return p.exists() and p.stat().st_mtime >= started_ts
            except Exception:
                return False
    
        f_primary   = fresh(PRIMARY_CSV)
        f_secondary = fresh(SECONDARY_CSV)
        f_html      = fresh(HTML_NETWORK)
    
        any_fresh = any([
            f_primary, f_secondary, f_html
        ])

    
        if not any_fresh:
            st.info("No new outputs were produced in this run.")
        else:
            # --- Run summary: elapsed time + download-all button ---
            ended_ts = st.session_state.get("_last_run_ended_ts")

            elapsed_label = ""
            if started_ts and ended_ts and ended_ts >= started_ts:
                elapsed_sec = int(ended_ts - started_ts)
                m, s = divmod(elapsed_sec, 60)
                elapsed_label = f"{m} min {s} sec" if m else f"{s} sec"
            elif started_ts:
                # fallback in case ended_ts is missing
                elapsed_sec = int(time.time() - started_ts)
                m, s = divmod(elapsed_sec, 60)
                elapsed_label = f"{m} min {s} sec" if m else f"{s} sec"

            top_l, top_r = st.columns([0.55, 0.45])
            with top_l:
                if elapsed_label:
                    st.markdown(f"**Total elapsed time:** {elapsed_label}")
            with top_r:
                zip_bytes = None
                if started_ts:
                    zip_bytes = build_outputs_zip(started_ts)
                if zip_bytes:
                    zip_name_patent = (
                        st.session_state.get("run_patent") or patent or "run"
                    )
                    zip_name_patent = zip_name_patent.replace(" ", "_")
                    st.download_button(
                        label="Download all outputs (.zip)",
                        data=zip_bytes,
                        file_name=f"patent_outputs_{zip_name_patent}.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )

            # --- Patent overview card (Google Patents) ---
            run_code = st.session_state.get("run_patent") or patent
            render_patent_header_summary(run_code)


             # --- Interactive Graph ---
            st.markdown("### Interactive Graph")
            if f_html:
                components.html(HTML_NETWORK.read_text(encoding="utf-8", errors="ignore"), height=720, scrolling=True)
            else:
                st.info("No interactive network was updated for this run.")
            
            # --- Primary ---
            st.markdown("### Primary Results")
            if f_primary:
                render_similarity_legend()
                df1 = pd.read_csv(PRIMARY_CSV)
                df1_view = add_similarity_swatch(df1)
                st.dataframe(
                    df1_view,
                    use_container_width=True,
                    column_config={"Match": st.column_config.ImageColumn("Match", help="Similarity bucket")},
                )
                btn_cols = st.columns([0.28, 0.72])
                with btn_cols[0]:
                    st.download_button(
                        label="Download original CSV",
                        data=df1.to_csv(index=False).encode("utf-8"),
                        file_name=PRIMARY_CSV.name,
                        mime="text/csv",
                    )
            else:
                st.info("No primary results were updated for this run.")
    
            # --- Secondary ---
            st.markdown("### Second-Level Results")
            if f_secondary:
                render_similarity_legend()
                df2 = pd.read_csv(SECONDARY_CSV)
                df2_view = add_similarity_swatch(df2)
                st.dataframe(
                    df2_view,
                    use_container_width=True,
                    column_config={"Match": st.column_config.ImageColumn("Match", help="Similarity bucket")},
                )
                btn_cols = st.columns([0.28, 0.72])
                with btn_cols[0]:
                    st.download_button(
                        label="Download original CSV",
                        data=df2.to_csv(index=False).encode("utf-8"),
                        file_name=SECONDARY_CSV.name,
                        mime="text/csv",
                    )
            else:
                st.info("No second-level connections were updated for this run.")
    
            # --- Visualizations ---
            
            st.markdown("### Visualizations")

            imgs_l1 = list_session_images(VISUALS_DIR_L1, started_ts)
            imgs_l2 = list_session_images(VISUALS_DIR_L2, started_ts)

            if not imgs_l1 and not imgs_l2:
                st.info("No visualizations were updated for this run.")
            else:
                if imgs_l1:
                    st.markdown("#### Level 1 Visualizations")
                    for p in imgs_l1:
                        st.image(str(p), use_container_width=True, caption=p.name)

                if imgs_l2:
                    st.markdown("#### Level 2 Visualizations")
                    for p in imgs_l2:
                        st.image(str(p), use_container_width=True, caption=p.name)

    
               
    else:
        st.info("Enter inputs and click Run Search to generate outputs.")


# --------------------------- Footer ---------------------------
def _encode_image_b64(img_path: Path) -> str:
    try:
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

def render_footer():
    # Logo lives in streamlit/ (same dir as config.toml)
    logo_path = Path(__file__).parent / "streamlit" / "purduelogo1.jpg"
    logo_b64  = _encode_image_b64(logo_path)
    logo_mime = "image/jpeg"   # it's a JPG

    # Purdue-aligned colors (pure black so it blends with the JPG background)
    purdue_gold = "#CFB991"
    footer_bg   = "#000000"    # pure black to match the logo’s background
    footer_txt  = "#E8E8E8"

    st.markdown(f"""
<style>
:root {{
  --purdue-gold: {purdue_gold};
  --footer-bg:   {footer_bg};
  --footer-text: {footer_txt};
}}

.footer-bar {{
  margin-top: 0.1rem;
  padding: 0px 24px;               /* more room for the big logo */
  background: var(--footer-bg);
  border-top: 1px solid rgba(207,185,145,.35);
  border-radius: 12px;
}}

.footer-inner {{
  display: flex;
  align-items: center;              /* center against tall logo */
  justify-content: space-between;
  gap: 24px;
}}

.footer-text {{
  font-size: .95rem;
  color: var(--footer-text);
  line-height: 1.45;
}}

.footer-text .brand {{
  color: var(--purdue-gold);
  font-weight: 600;
}}

.footer-logos img {{
  height: clamp(108px, 14vw, 180px);  /* ~3–4× bigger, responsive */
  display: block;
  max-width: none;
  background: var(--footer-bg);       /* ensures perfect blend with bar */
}}

@media (max-width: 1200px) {{
  .footer-inner {{ flex-direction: column; align-items: flex-start; gap: 24px; }}
  .footer-logos {{ align-self: flex-end; }}
  .footer-logos img {{ height: 72px; }}  /* comfortable on mobile/tablet */
}}
</style>

<div class="footer-bar">
  <div class="footer-inner">
    <div class="footer-text">
      <div> © NASA Technology Transfer Office — 2025</div>
      <div> © 2025 <span class="brand">Purdue University</span> | Joint and Special Programs | Master of Science in Artificial Intelligence | Project Team E (Fall 2025)</div>
    </div>
    <div class="footer-logos">
      {"<img alt='Purdue Graduate School' src='data:" + logo_mime + ";base64," + logo_b64 + "'/>" if logo_b64 else ""}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

render_footer()
