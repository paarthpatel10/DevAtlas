import streamlit as st
import httpx
import os
import uuid

# ── Configuration ────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Data Assistant",
    page_icon="✨",
    layout="wide",
)

# ── Clean & Premium Aesthetics ───────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Sleek container for the header */
    .header-container {
        padding: 2rem 0 1rem 0;
        margin-bottom: 2rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .main-title {
        font-size: 2rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0;
    }
    
    .sub-title {
        color: #94a3b8;
        font-size: 1rem;
        margin-top: 0.5rem;
    }
    
    /* Clean Badges */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.5rem;
    }
    .badge-sql { background-color: rgba(168, 85, 247, 0.1); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.2); }
    .badge-rag { background-color: rgba(56, 189, 248, 0.1); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.2); }
    
    /* Source citation styling */
    .source-block {
        background-color: rgba(30, 41, 59, 0.5);
        border-left: 2px solid #3b82f6;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        border-radius: 0 4px 4px 0;
        font-size: 0.9rem;
    }
    .source-title {
        color: #94a3b8;
        font-size: 0.8rem;
        margin-bottom: 0.25rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ── Health Check ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=5)
def check_health():
    try:
        res = httpx.get(f"{API_URL}/assistant/health", timeout=2.0)
        return res.status_code == 200
    except:
        return False

is_online = check_health()

# ── Session State Initializer ────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}"

if "past_sessions" not in st.session_state:
    st.session_state.past_sessions = [st.session_state.session_id]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-container">
    <div class="main-title">✨ Data Assistant</div>
    <div class="sub-title">Natural Language SQL & Document Search</div>
</div>
""", unsafe_allow_html=True)

if not is_online:
    st.error("Backend API is currently offline. Please ensure FastAPI is running.")

# Helper to fetch history for a given session
def load_session_history(sid: str):
    if is_online:
        try:
            res = httpx.get(f"{API_URL}/history/{sid}", timeout=5.0)
            if res.status_code == 200:
                history = res.json().get("history", [])
                st.session_state.chat_history = [
                    {
                        "role": item["role"],
                        "content": item["content"],
                        "route": item.get("route"),
                        "sql_query": item.get("sql_query"),
                        "sources": item.get("sources")
                    }
                    for item in history
                ]
        except Exception as e:
            st.sidebar.error(f"Error loading history: {e}")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💬 Conversations")
    
    # "New Session" Button
    if st.button("➕ New Chat", use_container_width=True):
        new_sid = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.session_id = new_sid
        if new_sid not in st.session_state.past_sessions:
            st.session_state.past_sessions.insert(0, new_sid)
        st.session_state.chat_history = []
        st.rerun()

    # Session List
    st.markdown("#### Recent Sessions")
    for sid in st.session_state.past_sessions:
        is_active = (sid == st.session_state.session_id)
        # Prefix active vs inactive
        label = f"💬 {sid}" if is_active else f"📄 {sid}"
        
        if st.button(
            label, 
            key=f"btn_{sid}", 
            use_container_width=True, 
            type="primary" if is_active else "secondary"
        ):
            st.session_state.session_id = sid
            load_session_history(sid)
            st.rerun()

    st.markdown("---")
    st.markdown("### Upload Knowledge")
    uploaded_file = st.file_uploader("Upload PDF Document", type=["pdf"])
    if uploaded_file and st.button("Index PDF", disabled=not is_online):
        with st.spinner("Processing..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            try:
                res = httpx.post(f"{API_URL}/upload", files=files, timeout=60.0)
                if res.status_code == 200:
                    st.success("Document indexed successfully!")
                else:
                    st.error("Failed to index document.")
            except Exception as e:
                st.error(f"Error: {e}")
                
    st.markdown("---")
    if st.button("Clear History"):
        st.session_state.chat_history = []
        st.rerun()

# ── Chat State Sync ──────────────────────────────────────────────────────────
# Ensure current session is added to past sessions
if st.session_state.session_id not in st.session_state.past_sessions:
    st.session_state.past_sessions.insert(0, st.session_state.session_id)

# If chat history is empty, try loading it on startup or when switching
if not st.session_state.chat_history and is_online:
    load_session_history(st.session_state.session_id)

# ── Main Chat Interface ──────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Display route badges if present in state
        if msg.get("route") == "sql":
            st.markdown('<div class="badge badge-sql">SQL Query</div>', unsafe_allow_html=True)
        elif msg.get("route") == "rag":
            st.markdown('<div class="badge badge-rag">Document Search</div>', unsafe_allow_html=True)
            
        # Display SQL if present
        if msg.get("sql_query"):
            with st.expander("View SQL"):
                st.code(msg["sql_query"], language="sql")
                
        # Display sources if present
        if msg.get("sources"):
            with st.expander("View Sources"):
                for s in msg["sources"]:
                    st.markdown(f"""
                    <div class="source-block">
                        <div class="source-title">{s.get('file')} (Page {s.get('page')})</div>
                        <div>{s.get('snippet')}</div>
                    </div>
                    """, unsafe_allow_html=True)

if prompt := st.chat_input("Ask a question...", disabled=not is_online):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Thinking...")
        
        try:
            payload = {"query": prompt, "session_id": st.session_state.session_id}
            res = httpx.post(f"{API_URL}/assistant", json=payload, timeout=60.0)
            
            if res.status_code == 200:
                data = res.json()
                answer = data.get("answer", "")
                route = data.get("route", "")
                sql = data.get("sql_query", "")
                sources = data.get("sources", [])
                
                placeholder.markdown(answer)
                
                if route == "sql":
                    st.markdown('<div class="badge badge-sql">SQL Query</div>', unsafe_allow_html=True)
                    if sql:
                        with st.expander("View SQL"):
                            st.code(sql, language="sql")
                elif route == "rag":
                    st.markdown('<div class="badge badge-rag">Document Search</div>', unsafe_allow_html=True)
                    if sources:
                        with st.expander("View Sources"):
                            for s in sources:
                                st.markdown(f"""
                                <div class="source-block">
                                    <div class="source-title">{s.get('file')} (Page {s.get('page')})</div>
                                    <div>{s.get('snippet')}</div>
                                </div>
                                """, unsafe_allow_html=True)
                
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                    "route": route,
                    "sql_query": sql,
                    "sources": sources
                })
            else:
                placeholder.error("Failed to get response.")
        except Exception as e:
            placeholder.error(f"Error: {e}")
