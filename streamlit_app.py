"""
streamlit_app.py - 可视化管理后台 (LangChain 1.0 重构版)

基于 Streamlit 的 Web UI，支持实时观察多智能体 Swarm 的节点流转。
"""

import streamlit as st
import os
from dotenv import load_dotenv

# Import core components
from core.swarm import SwarmOrchestrator, console
from core import BUS, TODO, TEAM as team_manager
from core.llm import MODEL_ID
from managers.database import load_session, save_session, clear_session
import streamlit.components.v1 as components
import uuid
from utils.paths import get_env_path

# Load environment variables
env_path = get_env_path()
if env_path:
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Streamlit Page Config
st.set_page_config(
    page_title="Production Agent - Swarm UI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stChatMessage { border-radius: 15px; padding: 15px; margin-bottom: 10px; }
    .stMarkdown h1, h2, h3 { color: #00d4ff; }
    .node-header { color: #00d4ff; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px; margin-top: 15px; }
    .tool-box { background-color: #161b22; border-left: 3px solid #f0883e; padding: 8px; margin: 5px 0; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "swarm" not in st.session_state:
    swarm = SwarmOrchestrator(BUS, TODO, team_manager=team_manager, interrupt_checker=lambda: None)
    # 状态由 LangGraph checkpointer 自动持久化
    st.session_state.swarm = swarm

if "current_role" not in st.session_state:
    st.session_state.current_role = "ProductManager"

# Sidebar
with st.sidebar:
    st.title("🤖 Swarm UI")
    st.info(f"Model: {MODEL_ID}")
    st.info(f"Session: {st.session_state.session_id}")
    st.caption("⚡ Powered by LangChain 1.0 + LangGraph")
    
    st.divider()
    
    if st.button("Clear Session", use_container_width=True):
        clear_session(f"swarm_{st.session_state.session_id}")
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.session_state.swarm = SwarmOrchestrator(BUS, TODO, team_manager=team_manager, interrupt_checker=lambda: None)
        st.rerun()

    st.divider()
    st.write("### Active Agents")
    roles = ["ProductManager", "Architect", "Coder", "QA_Reviewer"]
    for role in roles:
        st.markdown(f"**{role}** " + ("🟢" if st.session_state.current_role == role else "⚪"))

    st.divider()
    if os.getenv("LANGSMITH_TRACING") == "true":
        st.success("Tracing: ENABLED")
        project = os.getenv("LANGSMITH_PROJECT", "production-agent")
        st.markdown(f"[LangSmith Dashboard](https://smith.langchain.com/o/default/projects/p/{project})")
    else:
        st.warning("Tracing: DISABLED")

def render_mermaid(mermaid_code: str):
    """渲染 Mermaid 图表"""
    html_code = f"""
    <div class="mermaid">
    {mermaid_code}
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
    </script>
    """
    components.html(html_code, height=400, scrolling=True)

# UI Header
st.title("🚀 Production Agent")
st.caption("Multi-Agent Autonomous Software Engineering Swarm — LangGraph Edition")

# Tabs
tab_chat, tab_viz = st.tabs(["💬 Chat", "📊 Live Flow"])

with tab_viz:
    st.subheader("LangGraph Swarm Topology")
    mermaid_graph = st.session_state.swarm.get_mermaid_graph()
    render_mermaid(mermaid_graph)
    st.caption("Tip: Nodes highlight the internal state machine flow.")

with tab_chat:
    # Display Chat History
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "role_name" in message:
                st.caption(f"Agent: {message['role_name']}")

# Chat Input
if prompt := st.chat_input("Input your project requirements..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.status("Swarm Engine Executing...", expanded=True) as status:
        swarm = st.session_state.swarm
        swarm.inject_user_message(st.session_state.current_role, prompt)
        
        def swarm_callback(event_type, data):
            if event_type == "node_start":
                st.markdown(f"<div class='node-header'>➔ Node Switch: {data['role']}</div>", unsafe_allow_html=True)
            elif event_type == "tool_use":
                st.markdown(f"<div class='tool-box'>🛠️ Tool: {data['name']}</div>", unsafe_allow_html=True)
                with st.expander(f"Tool Inputs: {data['name']}", expanded=False):
                    st.json(data['input'])
            elif event_type == "tool_result":
                st.caption(f"Result: {data['output'][:200]}...")
            elif event_type == "info":
                st.info(data)

        try:
            import asyncio
            # 传入 session_id 作为 thread_id
            final_role = asyncio.run(swarm.run_swarm_loop(
                st.session_state.current_role, 
                thread_id=st.session_state.session_id,
                callback=swarm_callback,
                user_message=prompt
            ))
            st.session_state.current_role = final_role
            
            last_agent_messages = getattr(swarm, "latest_messages", [])
            assistant_responses = [m for m in last_agent_messages if getattr(m, "type", "") == "ai" and not getattr(m, "tool_calls", [])]
            
            if assistant_responses:
                last_response = assistant_responses[-1].content
                if isinstance(last_response, list):
                    text_parts = [b.get("text", "") for b in last_response if hasattr(b, "get") and b.get("type") == "text"]
                    full_response = "\n".join(text_parts)
                else:
                    full_response = str(last_response)
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response,
                    "role_name": final_role
                })
                
                with st.chat_message("assistant"):
                    st.markdown(full_response)
            
            status.update(label="Workflow Complete", state="complete", expanded=False)
            
        except Exception as e:
            st.error(f"Execution Error: {e}")
            status.update(label="Workflow Failed", state="error")

st.divider()
st.caption("Agentic Observability Layer Active — LangChain 1.0 + LangGraph + LangSmith")
