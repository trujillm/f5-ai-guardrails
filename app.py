import html
import json
import streamlit as st
import httpx
from openai import OpenAI
from pathlib import Path
from datetime import datetime

DEFAULT_BASE_URL = "https://aisec.apps.ai-guardrails.bd.f5.com/openai/llamastack"
DEFAULT_MODEL = "llama-3-2-1b-instruct-quantized/RedHatAI/Llama-3.2-1B-Instruct-quantized.w8a8"
HISTORY_FILE = Path("chat_history.json")

st.set_page_config(page_title="F5 AI Security Chat", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d1b2e; color: #e0e0e0; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 5rem; max-width: 860px; }

/* Bottom chat input bar — nuke all white backgrounds */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
[data-testid="stBottom"] * { background-color: #0d1b2e !important; }
[data-testid="stBottom"] { border-top: 1px solid #1a2d45; }

/* The textarea itself */
[data-testid="stChatInputTextArea"] {
    background-color: #132236 !important; color: #d0dce8 !important;
    border: 1px solid #1e3a5a !important; border-radius: 12px !important;
    caret-color: #d0dce8 !important;
}
[data-testid="stChatInputTextArea"]::placeholder { color: #607080 !important; }

/* The wrapper div that renders as white rounded box */
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div { background-color: #132236 !important; border-radius: 12px !important; }
[data-testid="stChatInput"] { background-color: #0d1b2e !important; }

[data-testid="stChatInputSubmitButton"] button {
    background-color: #2a9d8f !important; border-radius: 8px !important;
    visibility: visible !important; opacity: 1 !important;
    padding: 0 14px !important;
}
[data-testid="stChatInputSubmitButton"] button svg { display: none !important; }
[data-testid="stChatInputSubmitButton"] button::after {
    content: "Send"; font-size: 0.85rem; font-weight: 600; color: white;
}

.chat-title {
    font-size: 1.4rem; font-weight: 600; color: #e0e0e0;
    padding-bottom: 1rem; border-bottom: 1px solid #1e3050; margin-bottom: 1rem;
}
.chat-container { display: flex; flex-direction: column; gap: 14px; }

/* User message */
.msg-user { display: flex; flex-direction: row-reverse; align-items: flex-end; gap: 10px; }
.msg-user .bubble {
    background: #1e3050; color: #d0dce8;
    border-radius: 18px 18px 4px 18px;
    padding: 10px 15px; max-width: 65%; font-size: 0.92rem; line-height: 1.5;
    word-break: break-word;
}
.avatar-user {
    width: 34px; height: 34px; border-radius: 50%;
    background: #2a9d8f; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.82rem; color: white; flex-shrink: 0;
}

/* Assistant message */
.msg-assistant { display: flex; flex-direction: row; align-items: flex-end; gap: 10px; }
.msg-assistant .bubble {
    background: #132236; color: #d0dce8;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px; max-width: 70%; font-size: 0.92rem; line-height: 1.5;
    word-break: break-word;
}
.avatar-assistant {
    width: 34px; height: 34px; border-radius: 50%;
    background: #2a9d8f; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; font-size: 1rem; color: white;
}
.bubble-actions {
    display: flex; gap: 8px; margin-top: 8px;
    opacity: 0.4; font-size: 0.8rem; color: #a0b0c0;
}
.bubble-actions span { cursor: pointer; }
.bubble-actions span:hover { opacity: 0.8; }

/* Blocked message */
.msg-blocked { display: flex; flex-direction: row-reverse; }
.blocked-tag {
    background: #132236; color: #607080;
    border-radius: 8px; padding: 5px 13px;
    font-size: 0.75rem; border: 1px solid #1e3050;
}

/* Sidebar */
section[data-testid="stSidebar"] { background-color: #0a1525; }
section[data-testid="stSidebar"] label { color: #a0b8c8 !important; }
section[data-testid="stSidebar"] h3 { color: #e0e0e0 !important; margin-bottom: 0.5rem; }
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
    background-color: #132236 !important; color: #d0dce8 !important;
    border-color: #1e3a5a !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.markdown("### Configuration")
base_url = st.sidebar.text_input("Endpoint URL", value=DEFAULT_BASE_URL)
api_key = st.sidebar.text_input("API Token", type="password")

# Fetch model list from the API
@st.cache_data(show_spinner=False, ttl=300)
def fetch_models(base_url: str, api_key: str) -> list[str]:
    client = OpenAI(base_url=base_url, api_key=api_key, http_client=httpx.Client(verify=False))
    models = client.models.list()
    return sorted(m.id for m in models.data)

model = None
if base_url and api_key:
    with st.sidebar:
        with st.spinner("Loading models..."):
            try:
                model_list = fetch_models(base_url, api_key)
                model = st.selectbox("Available models", model_list)
            except Exception:
                model = st.text_input("Available models", value=DEFAULT_MODEL)

st.sidebar.divider()
if st.sidebar.button("Clear history"):
    st.session_state.messages = []
    HISTORY_FILE.unlink(missing_ok=True)
    st.rerun()

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    if HISTORY_FILE.exists():
        st.session_state.messages = json.loads(HISTORY_FILE.read_text())
    else:
        st.session_state.messages = []

# ── Chat UI ────────────────────────────────────────────────────────────────────
st.markdown('<div class="chat-title">F5 AI Security Chat</div>', unsafe_allow_html=True)


def render_messages():
    parts = ['<div class="chat-container">']
    for msg in st.session_state.messages:
        role = msg["role"]
        if role == "blocked":
            time = msg.get("time", "")
            parts.append(f'<div class="msg-blocked"><div class="blocked-tag">Blocked Message Attempt {time}</div></div>')
        elif role == "user":
            content = html.escape(msg["content"]).replace("\n", "<br>")
            parts.append(f'''
<div class="msg-user">
  <div class="avatar-user">A</div>
  <div class="bubble">{content}</div>
</div>''')
        elif role == "assistant":
            content = html.escape(msg["content"]).replace("\n", "<br>")
            parts.append(f'''
<div class="msg-assistant">
  <div class="avatar-assistant">&#9678;</div>
  <div class="bubble">
    {content}
    <div class="bubble-actions"><span title="Share">&#8599;</span><span title="Copy">&#9647;</span></div>
  </div>
</div>''')
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


render_messages()

if prompt := st.chat_input("Type message here..."):
    if not api_key or not base_url:
        st.error("Enter Endpoint URL and API token in the sidebar.")
        st.stop()
    if not model:
        st.error("No model selected.")
        st.stop()

    time_str = datetime.now().strftime("%-I:%M %p")
    st.session_state.messages.append({"role": "user", "content": prompt, "time": time_str})

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=httpx.Client(verify=False),
    )

    api_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m["role"] in ("user", "assistant")
    ]

    try:
        response = client.chat.completions.create(model=model, messages=api_messages)
        reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": reply, "time": time_str})
    except Exception as e:
        body = getattr(getattr(e, "response", None), "json", lambda: {})()
        if body.get("error", {}).get("cai_error", {}).get("outcome") == "blocked":
            st.session_state.messages.append({"role": "blocked", "time": time_str})
        else:
            st.session_state.messages.pop()
            st.error(f"Error: {e}")

    HISTORY_FILE.write_text(json.dumps(st.session_state.messages))
    st.rerun()
