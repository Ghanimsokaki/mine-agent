from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from src.auth import (
    SignedInUser,
    begin_oauth,
    complete_oauth_callback,
    restore_session,
    send_email_code,
    verify_email_code,
)
from src.browser_actions import action_summary, extract_browser_actions
from src.config import AppConfig, load_config
from src.files import extract_generated_files, extract_text, json_download, render_context
from src.llm import LLMError, OpenRouterClient, available_models, build_messages
from src.store import StoreError, SupabaseStore
from src.usage import ACTIVE_WINDOW, COOLDOWN_WINDOW, UsageStatus, evaluate_usage, format_remaining

st.set_page_config(page_title="ForgePilot", page_icon="✦", layout="wide", initial_sidebar_state="expanded")


APP_CSS = """
<style>
:root { --fp-bg: #1f1f1d; --fp-panel: #292927; --fp-panel-2: #31312e; --fp-text: #f6f1ea; --fp-muted: #b9b4ad; --fp-accent: #d57b5e; --fp-line: #45433f; }
.stApp { background: radial-gradient(850px 500px at 72% -10%, #44342d 0%, transparent 55%), var(--fp-bg); color: var(--fp-text); }
[data-testid="stSidebar"] { background: #242421; border-right: 1px solid var(--fp-line); }
[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
h1, h2, h3 { letter-spacing: -.03em; }
.fp-brand { font-size: 1.25rem; font-weight: 760; letter-spacing: -.04em; margin: 0; }
.fp-brand span { color: var(--fp-accent); }
.fp-tagline { color: var(--fp-muted); font-size: .8rem; margin: .12rem 0 1.2rem; }
.fp-hero { max-width: 760px; margin: 10vh auto 0; text-align: center; }
.fp-hero h1 { font-size: clamp(2.3rem, 6vw, 4.6rem); margin-bottom: .4rem; }
.fp-hero p { color: var(--fp-muted); font-size: 1.05rem; line-height: 1.6; }
.fp-card { border: 1px solid var(--fp-line); background: rgba(47,47,43,.82); padding: 1rem 1.05rem; border-radius: 13px; margin: .7rem 0; }
.fp-status { border-radius: 99px; display: inline-block; padding: .23rem .65rem; font-size: .76rem; font-weight: 700; background: #38453a; color: #d5f0d3; }
.fp-status.cooldown { background: #573c36; color: #ffd0c3; }
.fp-status.ready { background: #3b4148; color: #d6e6f5; }
.fp-muted { color: var(--fp-muted); font-size: .84rem; line-height: 1.5; }
[data-testid="stChatMessage"] { border: 1px solid var(--fp-line); border-radius: 14px; padding: .35rem .7rem; margin-bottom: .9rem; background: rgba(42,42,39,.75); }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: rgba(54,48,44,.72); }
.stButton > button, .stDownloadButton > button { border-radius: 9px; border: 1px solid #66594f; background: #3a3733; color: var(--fp-text); font-weight: 630; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--fp-accent); color: #fff; }
[data-testid="stChatInput"] { border-radius: 14px; border-color: #5a554e; background: #2c2c29; }
[data-testid="stExpander"] { border: 1px solid var(--fp-line); border-radius: 10px; background: rgba(42,42,39,.6); }
hr { border-color: var(--fp-line); }
code { color: #ffd5bd; }
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)


def get_config() -> AppConfig:
    try:
        return load_config(st.secrets)
    except Exception:
        return load_config({})


def app_header(config: AppConfig) -> None:
    with st.sidebar:
        st.markdown(f'<p class="fp-brand"><span>✦</span> {config.app_name}</p>', unsafe_allow_html=True)
        st.markdown('<p class="fp-tagline">Private agent workspace</p>', unsafe_allow_html=True)


def clean_callback_code() -> str | None:
    code = st.query_params.get("code")
    if isinstance(code, list):
        code = code[0] if code else None
    return str(code) if code else None


def render_auth(config: AppConfig, store: SupabaseStore) -> SignedInUser | None:
    """Render Supabase sign-in choices. No user password is handled by this app."""
    code = clean_callback_code()
    if code:
        try:
            user = complete_oauth_callback(store, st.session_state, code)
            if user:
                st.query_params.clear()
                st.rerun()
        except StoreError as exc:
            st.error(str(exc))
            st.query_params.clear()

    user = restore_session(store, st.session_state)
    if user:
        return user

    st.markdown('<section class="fp-hero"><div class="fp-status ready">PRIVATE WORKSPACE</div><h1>Think. Build. Approve.</h1><p>Chat with your chosen OpenRouter model, keep project memory private, and send only explicitly approved tasks to your paired browser.</p></section>', unsafe_allow_html=True)
    left, middle, right = st.columns([1, 1.25, 1])
    with middle:
        st.markdown("<div class='fp-card'>", unsafe_allow_html=True)
        st.subheader("Sign in to continue")
        st.caption("ForgePilot uses Supabase Auth. It never collects your GitHub password.")
        try:
            github_url = begin_oauth(store, "github", config.public_url)
            st.link_button("Continue with GitHub", github_url, use_container_width=True)
            if config.google_oauth_enabled:
                google_url = begin_oauth(store, "google", config.public_url)
                st.link_button("Continue with Google", google_url, use_container_width=True)
        except StoreError as exc:
            st.warning(str(exc))

        st.divider()
        st.markdown("**Email sign-in**")
        with st.form("email_link_form", clear_on_submit=False):
            email = st.text_input("Email address", placeholder="you@example.com")
            submitted = st.form_submit_button("Send sign-in email", use_container_width=True)
        if submitted:
            if "@" not in email:
                st.error("Enter a valid email address.")
            else:
                try:
                    send_email_code(store, email.strip(), config.public_url)
                    st.session_state["pending_email"] = email.strip()
                    st.success("Check your email. Open the secure link, or enter a Supabase email token below if your template uses tokens.")
                except StoreError as exc:
                    st.error(str(exc))
        with st.expander("Have an email token instead?"):
            with st.form("email_code_form"):
                token_email = st.text_input("Email", value=st.session_state.get("pending_email", ""), key="token_email")
                token = st.text_input("Email token", type="password", help="This is a short Supabase email token, not your password.")
                verify = st.form_submit_button("Verify email token")
            if verify:
                try:
                    user = verify_email_code(store, st.session_state, token_email.strip(), token)
                    if user:
                        st.rerun()
                    st.error("The token did not create a session.")
                except StoreError as exc:
                    st.error(str(exc))
        st.markdown("</div>", unsafe_allow_html=True)
    return None


def status_badge(status: UsageStatus) -> None:
    if status.state == "cooldown":
        st.markdown(f'<span class="fp-status cooldown">COOLDOWN · {format_remaining(status.remaining)}</span>', unsafe_allow_html=True)
        st.caption("Your 7-hour window is complete. You can send another request after the 8-hour cooldown.")
    elif status.starts_on_first_request:
        st.markdown('<span class="fp-status ready">READY · 7H AVAILABLE</span>', unsafe_allow_html=True)
        st.caption("Your 7-hour access window begins with your first live model request.")
    else:
        st.markdown(f'<span class="fp-status">ACTIVE · {format_remaining(status.remaining)} LEFT</span>', unsafe_allow_html=True)
        st.caption("An 8-hour cooldown begins once this active window reaches zero.")


def render_generated_downloads(content: str, key_prefix: str) -> None:
    files = extract_generated_files(content)
    if not files:
        return
    with st.expander(f"Download generated files ({len(files)})", expanded=False):
        for index, generated in enumerate(files):
            st.download_button(
                f"Download {generated.filename}",
                data=generated.content.encode("utf-8"),
                file_name=generated.filename,
                mime="text/plain; charset=utf-8",
                key=f"{key_prefix}-file-{index}-{generated.filename}",
                use_container_width=True,
            )


def render_message(message: dict[str, Any], index: int, store: SupabaseStore, selected_agent: str | None) -> None:
    role = message.get("role", "assistant")
    with st.chat_message(role):
        st.markdown(str(message.get("content", "")))
        if role == "assistant":
            render_generated_downloads(str(message.get("content", "")), f"message-{index}")
            actions = extract_browser_actions(str(message.get("content", "")))
            if actions:
                st.caption("Proposed browser actions — nothing runs until you queue it and approve every action in the page.")
                for action in actions:
                    st.write(f"• {action_summary(action)}")
                if selected_agent:
                    if st.button("Queue these actions to paired browser", key=f"queue-{message.get('id', index)}"):
                        try:
                            store.queue_browser_task(selected_agent, actions, source="chat")
                            st.success("Queued. Open the authorized page in that browser and approve each action.")
                        except StoreError as exc:
                            st.error(str(exc))
                else:
                    st.info("Pair and select a browser in the sidebar before queueing actions.")


def render_files_panel(config: AppConfig, store: SupabaseStore, user: SignedInUser) -> list[dict[str, Any]]:
    with st.sidebar.expander("Files & context", expanded=False):
        st.caption("Files stay private in the `agent-files` Supabase bucket. Only selected non-credential files are included in a prompt.")
        upload = st.file_uploader("Reference file", type=["txt", "md", "pdf", "py", "js", "ts", "json", "csv", "yaml", "yml", "toml", "html", "css", "sql"], key="reference_upload")
        if upload and st.button("Save reference file", key="save-reference"):
            raw = upload.getvalue()
            if len(raw) > config.max_upload_mb * 1024 * 1024:
                st.error(f"File exceeds the {config.max_upload_mb} MB limit.")
            else:
                try:
                    store.upload_file(user.id, upload.name, raw, upload.type, kind="reference")
                    st.success("Saved to your private vault.")
                    st.rerun()
                except StoreError as exc:
                    st.error(str(exc))

        st.divider()
        st.markdown("**Kaggle credential vault**")
        st.warning("Optional. `kaggle.json` is kept as a private file and is never automatically sent to the model or executed.")
        kaggle = st.file_uploader("kaggle.json", type=["json"], key="kaggle_upload")
        confirm = st.checkbox("I understand this file contains a secret", key="kaggle_confirm")
        if kaggle and st.button("Store Kaggle credential privately", key="save-kaggle"):
            if not confirm or kaggle.name != "kaggle.json":
                st.error("Confirm the warning and upload a file named kaggle.json.")
            else:
                try:
                    store.upload_file(user.id, kaggle.name, kaggle.getvalue(), kaggle.type, kind="kaggle-credential")
                    st.success("Stored privately; it will not become chat context.")
                    st.rerun()
                except StoreError as exc:
                    st.error(str(exc))

        try:
            files = store.list_files()
        except StoreError as exc:
            st.error(str(exc))
            return []
        selectable = [item for item in files if item.get("kind") != "kaggle-credential"]
        labels = {str(item["id"]): f"{item['filename']} · {item.get('size_bytes', 0) / 1024:.1f} KB" for item in selectable}
        selected = st.multiselect("Include in next request", options=list(labels), format_func=lambda item: labels[item], key="selected_file_ids")
        selected_items = [item for item in selectable if str(item["id"]) in selected]
        if any(item.get("kind") == "kaggle-credential" for item in files):
            st.caption("🔒 A Kaggle credential is stored and excluded from prompt context.")
        return selected_items


def read_selected_context(store: SupabaseStore, selected_files: list[dict[str, Any]]) -> str:
    extracted: list[tuple[str, str]] = []
    for item in selected_files[:6]:
        try:
            raw = store.download_file(str(item["storage_path"]))
            extracted.append((str(item["filename"]), extract_text(str(item["filename"]), raw)))
        except StoreError:
            extracted.append((str(item["filename"]), "[The private file could not be read.]"))
    return render_context(extracted)


def render_memory_panel(store: SupabaseStore) -> None:
    with st.sidebar.expander("Private memory", expanded=False):
        st.caption("Save short durable notes such as stack choices or coding preferences. This is separate from chat history.")
        note = st.text_area("New note", max_chars=2000, key="memory_note", placeholder="e.g. This project uses Python 3.12 and Ruff.")
        if st.button("Save note", key="save-memory"):
            try:
                store.save_memory(note, source="manual")
                st.session_state["memory_note"] = ""
                st.success("Saved to private memory.")
            except StoreError as exc:
                st.error(str(exc))
        try:
            memories = store.recent_memories()
            if memories:
                st.caption(f"{len(memories)} recent note(s) are supplied to the assistant.")
        except StoreError as exc:
            st.error(str(exc))


def render_browser_panel(config: AppConfig, store: SupabaseStore) -> str | None:
    if not config.browser_bridge_enabled:
        return None
    with st.sidebar.expander("Browser bridge", expanded=False):
        st.caption("Optional Chrome/Edge companion. It requires a per-action confirmation in the active page and blocks obvious sensitive fields.")
        try:
            agents = store.list_browser_agents()
        except StoreError as exc:
            st.error(str(exc))
            return None

        with st.form("pair-browser"):
            browser_name = st.text_input("Browser name", value="My browser")
            create_pair = st.form_submit_button("Create pairing bundle")
        if create_pair:
            try:
                pair = store.create_browser_agent(browser_name)
                st.session_state["pairing_bundle"] = pair.bundle()
                st.success("Pairing bundle created. Copy it once into the unpacked extension popup.")
                st.rerun()
            except StoreError as exc:
                st.error(str(exc))

        bundle = st.session_state.get("pairing_bundle")
        if bundle:
            st.warning("Treat this bundle like a browser key. Paste it only into the local ForgePilot extension, then clear it here.")
            st.code(json.dumps(bundle, indent=2), language="json")
            col_copy, col_clear = st.columns(2)
            with col_copy:
                st.download_button("Download pairing JSON", json_download(bundle), "forgepilot-pairing.json", "application/json", key="download-pairing")
            with col_clear:
                if st.button("Clear shown key", key="clear-pairing"):
                    st.session_state.pop("pairing_bundle", None)
                    st.rerun()

        if not agents:
            st.info("Load `chrome_extension` as an unpacked extension, then create a pairing bundle.")
            return None
        agent_labels = {str(agent["id"]): f"{agent['name']} · last seen {str(agent.get('last_seen_at') or 'never')[:16]}" for agent in agents}
        selected = st.selectbox("Send actions to", options=list(agent_labels), format_func=lambda item: agent_labels[item], key="selected_browser_agent")
        try:
            tasks = store.list_browser_tasks(selected)
        except StoreError as exc:
            st.error(str(exc))
            return selected
        if tasks:
            latest = tasks[0]
            st.caption(f"Latest task: **{latest.get('status')}** · {str(latest.get('created_at'))[:16]}")
            if latest.get("result"):
                st.caption("Latest browser result")
                st.json(latest["result"], expanded=False)
                if st.button("Add result to current chat", key=f"add-browser-result-{latest['id']}"):
                    st.session_state["pending_browser_result"] = latest["result"]
                    st.success("It will be added to your next message as private context.")
        return selected


def render_manual_browser_task(store: SupabaseStore, selected_agent: str | None) -> None:
    if not selected_agent:
        return
    with st.sidebar.expander("Manual browser action", expanded=False):
        st.caption("Use this only on a website you are authorized to operate. The page will ask you to approve the action.")
        with st.form("manual-browser-action"):
            action_type = st.selectbox("Action", ["read_page", "click", "type", "insert_code", "select", "download_file"])
            selector = st.text_input("CSS selector", placeholder="textarea.editor")
            payload = st.text_area("Text / value", max_chars=12000)
            description = st.text_input("What will happen?", placeholder="Place code in the editor")
            filename = st.text_input("Download filename", value="forgepilot-output.txt") if action_type == "download_file" else ""
            queue = st.form_submit_button("Queue for approval")
        if queue:
            raw = {"action": action_type, "selector": selector, "text": payload, "value": payload, "description": description, "filename": filename}
            # Use the same strict parser as model-produced actions.
            fenced = "```browser-actions\n" + json.dumps([raw]) + "\n```"
            from src.browser_actions import extract_browser_actions
            actions = extract_browser_actions(fenced)
            if not actions:
                st.error("Use an allowed action with a selector. Sensitive tasks are blocked.")
            else:
                try:
                    store.queue_browser_task(selected_agent, actions, source="manual")
                    st.success("Queued. Open the target site in the paired browser, then approve it there.")
                except StoreError as exc:
                    st.error(str(exc))


def conversation_controls(store: SupabaseStore) -> tuple[str, list[dict[str, Any]]]:
    with st.sidebar:
        if st.button("＋ New chat", use_container_width=True):
            try:
                row = store.new_conversation()
                st.session_state["conversation_id"] = str(row["id"])
                st.rerun()
            except StoreError as exc:
                st.error(str(exc))
        try:
            conversations = store.list_conversations()
        except StoreError as exc:
            st.error(str(exc))
            conversations = []
        if not conversations:
            row = store.new_conversation()
            conversations = [row]
        ids = [str(row["id"]) for row in conversations]
        current = str(st.session_state.get("conversation_id") or ids[0])
        if current not in ids:
            current = ids[0]
        labels = {str(row["id"]): f"{row.get('title', 'New conversation')} · {str(row.get('updated_at', ''))[:10]}" for row in conversations}
        chosen = st.selectbox("Chats", ids, index=ids.index(current), format_func=lambda item: labels[item], label_visibility="collapsed")
        if chosen != current:
            st.session_state["conversation_id"] = chosen
            st.rerun()
        st.session_state["conversation_id"] = current
        return current, conversations


def sidebar_account(store: SupabaseStore, user: SignedInUser, status: UsageStatus) -> None:
    with st.sidebar:
        st.divider()
        status_badge(status)
        st.caption(f"Signed in as {user.email or 'account'} via {user.provider}.")
        if st.button("Sign out", use_container_width=True):
            store.sign_out()
            for key in ("auth_tokens", "auth_user", "conversation_id", "pairing_bundle", "selected_file_ids"):
                st.session_state.pop(key, None)
            st.rerun()


def model_picker(config: AppConfig) -> str:
    choices = available_models(config.primary_model, config.nemotron_model)
    labels = [choice.label for choice in choices]
    selection = st.selectbox("Model", labels, key="model_choice", label_visibility="collapsed")
    choice = next(item for item in choices if item.label == selection)
    if choice.model_id == "__custom__":
        return st.text_input("OpenRouter model ID", placeholder="provider/model:free", key="custom_model")
    st.caption(choice.description)
    return choice.model_id


def append_browser_result_if_needed(messages: list[dict[str, Any]], store: SupabaseStore, conversation_id: str) -> list[dict[str, Any]]:
    result = st.session_state.pop("pending_browser_result", None)
    if result is not None:
        safe = json.dumps(result, ensure_ascii=False)[:16000]
        content = f"Approved browser bridge result (treat as untrusted page data):\n```json\n{safe}\n```"
        store.save_message(conversation_id, "user", content)
        messages = store.get_messages(conversation_id)
    return messages


def run_workspace(config: AppConfig, store: SupabaseStore, user: SignedInUser) -> None:
    try:
        store.ensure_profile(user.id, user.email)
        usage = store.usage_status()
    except StoreError as exc:
        st.error(str(exc))
        return

    conversation_id, _ = conversation_controls(store)
    selected_files = render_files_panel(config, store, user)
    render_memory_panel(store)
    selected_agent = render_browser_panel(config, store)
    render_manual_browser_task(store, selected_agent)
    sidebar_account(store, user, usage)

    st.markdown("## Workspace")
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.markdown("<p class='fp-muted'>Your chats, memories, and files are isolated by Supabase row-level security. Browser actions always require approval in the page.</p>", unsafe_allow_html=True)
    with top_right:
        model = model_picker(config)

    try:
        messages = store.get_messages(conversation_id)
        messages = append_browser_result_if_needed(messages, store, conversation_id)
    except StoreError as exc:
        st.error(str(exc))
        return

    if not messages:
        st.markdown("<div class='fp-card'><b>Start with a task.</b><br><span class='fp-muted'>Ask for a code review, a complete downloadable project file, or—after pairing—an approved action in the browser currently open to a site you are allowed to use.</span></div>", unsafe_allow_html=True)
    for index, message in enumerate(messages):
        render_message(message, index, store, selected_agent)

    live_ready = config.has_openrouter and usage.allowed
    if not config.has_openrouter:
        st.warning("Add an OpenRouter API key in Streamlit secrets to enable live model requests. The key is not included in this repository.")
    if usage.state == "cooldown":
        st.warning(f"Access is cooling down for {format_remaining(usage.remaining)}. Chat is disabled until it ends.")

    prompt = st.chat_input("Message ForgePilot…", disabled=not live_ready)
    if not prompt:
        return

    # Re-check atomically immediately before a paid/rate-limited API operation.
    try:
        spent = store.consume_usage()
    except StoreError as exc:
        st.error(str(exc))
        return
    if not spent.allowed:
        st.error(f"Your access is in cooldown. Try again in {format_remaining(spent.remaining)}.")
        return

    try:
        store.save_message(conversation_id, "user", prompt)
        messages = store.get_messages(conversation_id)
        document_context = read_selected_context(store, selected_files)
        memories = store.recent_memories()
        llm_messages = build_messages(messages, memories, document_context)
        client = OpenRouterClient(config.openrouter_key, config.openrouter_site_url, config.app_name)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                completion = client.complete(model.strip(), llm_messages)
            st.markdown(completion.content)
            render_generated_downloads(completion.content, "new-response")
        store.save_message(conversation_id, "assistant", completion.content, completion.model)
        st.rerun()
    except LLMError as exc:
        st.error(str(exc))
    except StoreError as exc:
        st.error(str(exc))


def render_configuration_landing(config: AppConfig) -> None:
    st.markdown('<section class="fp-hero"><div class="fp-status ready">SETUP REQUIRED</div><h1>Your private agent workspace.</h1><p>Configure Supabase Auth and storage plus an OpenRouter API key to enable secure chat, OAuth accounts, durable memory, downloadable files, and the consent-first browser bridge.</p></section>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    for column, title, text in (
        (a, "1 · Secrets", "Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Keep it untracked."),
        (b, "2 · Supabase", "Run `supabase/schema.sql`, configure Auth redirect URLs, then add your project URL and anon key."),
        (c, "3 · OpenRouter", "Add a verified model ID and key. Free models can be rate-limited or unavailable."),
    ):
        with column:
            st.markdown(f"<div class='fp-card'><b>{title}</b><br><span class='fp-muted'>{text}</span></div>", unsafe_allow_html=True)
    st.info("Read the README for OAuth, storage, Kaggle vault, usage-limit, and browser-extension setup. No provider key or credential is embedded in this source tree.")


def main() -> None:
    config = get_config()
    app_header(config)
    if not config.has_supabase:
        render_configuration_landing(config)
        return
    store = SupabaseStore(config.supabase_url, config.supabase_anon_key)
    user = render_auth(config, store)
    if not user:
        return
    run_workspace(config, store, user)


if __name__ == "__main__":
    main()
