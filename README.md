# ForgePilot — consent-first browser coding agent

ForgePilot is a Streamlit workspace for chatting with a Hugging Face primary model (and optional OpenRouter fallback), keeping private working memory in Supabase, producing downloadable files, and **optionally** sending narrowly scoped actions to a locally installed browser extension.

> Browser automation is intentionally consent-first. The extension asks on the page before it reads, clicks, types, or inserts code. It cannot work on browser-internal pages, Chrome Web Store pages, or sites that block extensions. Do not use it to bypass paywalls, CAPTCHAs, access controls, or a site's terms.

## Included

- Clean, familiar assistant-workspace UI with a light sidebar, focused welcome composer, conversation history, file context and downloads.
- **No-account guest chat**: visitors can start a temporary chat without Supabase or OAuth. Guest messages, attachments, and the local 7-hour window exist only for the current Streamlit session; sign in to save work and enforce limits across devices.
- Configurable provider-aware model picker. The requested Hugging Face `hwiiiiiiii/gemby-agent-3b` is the primary choice; NVIDIA Nemotron Ultra remains an optional OpenRouter fallback. Verify actual provider availability before deployment.
- GitHub OAuth, optional Google OAuth, and email magic-link authentication through Supabase Auth.
- Supabase Postgres + Storage memory, chats, private file storage, usage windows, browser task relay, and a server-side administrator allow-list for `emir.erningpraja@gmail.com`.
- A **7-hour active access window**, followed by an **8-hour cooldown**, enforced in the database for authenticated users.
- Public web research: paste a public `http(s)` URL to read a capped, text-only excerpt and explicitly include it in the next prompt. Local/private URLs, credentials, non-standard ports, and non-text pages are blocked.
- Kaggle credential upload as a private file vault item (optional; it is not sent to the model by default).
- A Chrome/Chromium companion extension that can perform approved DOM actions on sites you are authorized to use.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

The interface launches in a local-only preview without Supabase, but production sign-in, durable memory, cross-device cooldown enforcement, cloud files, browser tasks, and OAuth require Supabase.

## Supabase setup

1. Create a Supabase project.
2. Open the SQL editor and run [`supabase/schema.sql`](supabase/schema.sql) as the project owner.
3. In **Authentication → URL Configuration**, add the app URL (`https://your-app.example`) as a Site URL and redirect URL.
4. Enable GitHub in **Authentication → Providers**. Create the GitHub OAuth app with the Supabase callback URL shown by Supabase. Optionally enable Google.
5. Create the private `agent-files` bucket, either through the SQL migration or dashboard.
6. Copy only the project URL and **anon/publishable** key into `.streamlit/secrets.toml`. Never put a Supabase `service_role` key in Streamlit secrets.
7. Add a Hugging Face token to `huggingface.api_key` in your local untracked file or deployment secret manager. Add an OpenRouter key only if you also want the NVIDIA fallback.

The app uses Supabase PKCE OAuth. Add every deployed Streamlit URL to Supabase redirect allow-lists. For deployment, set `app.public_url` to the final HTTPS address.

### Model and administrator note

The primary model is configured as `hwiiiiiiii/gemby-agent-3b` through the Hugging Face OpenAI-compatible Inference Providers chat endpoint. Create a fine-grained Hugging Face token with permission to make Inference Provider calls and put it in `huggingface.api_key`. A model must be available through the selected Hugging Face endpoint; if Gemby is served on a custom endpoint, replace `huggingface.chat_endpoint` with that endpoint. NVIDIA Nemotron remains optional through OpenRouter and may be rate limited or unavailable.

The Supabase migration seeds `emir.erningpraja@gmail.com` into the private `admin_users` allow-list. After that email signs in, ForgePilot verifies the role server-side using the signed Supabase JWT and displays the Administrator account status. Re-run the supplied SQL migration after updating an existing project.

## Browser bridge

1. Load [`chrome_extension`](chrome_extension) in Chrome/Edge via **Extensions → Developer mode → Load unpacked**.
2. Sign in to ForgePilot, open **Browser bridge** in the sidebar, and create a pairing bundle.
3. Paste that bundle into the extension popup. The bundle contains a narrow browser-bridge secret, not your GitHub or Supabase account password.
4. Select that paired browser in ForgePilot. Ask the assistant for an approved browser action, or use the manual task panel.
5. Approve or decline every request in the browser page. Results return to the bridge panel and can be sent back to chat.

The extension polls only for tasks intended for its paired identifier. Its secret is stored as a hash in Supabase. It only receives a task after a user queues it, and it cannot silently execute actions. Keep the extension disabled when not needed.

## Web research, Kaggle, and documents

Use the **Web research** panel to read public HTML or text pages. The reader is intentionally limited to public standard-web URLs and marks retrieved material as untrusted reference context, so it cannot direct the agent to take actions. For an authorized logged-in webpage, use **Browser bridge → Request visible text from current page**; the extension asks for on-page approval and returns only after you approve.


Upload `kaggle.json` only if you need it as a private project file. The app does not execute Kaggle commands or expose the credential to prompts automatically. You can upload text, Markdown, JSON, Python, CSV, and PDF reference documents. Select files in the sidebar to add extracted text to a chat turn.

## Security and operating limits

- OAuth identities and data policies are enforced by Supabase RLS in the supplied migration.
- Browser pairing uses a per-browser secret and security-definer RPC functions that can only claim/complete tasks for that browser.
- The app refuses browser tasks containing obvious password, OTP, or payment-card fields. This is a safety guard, not a replacement for review.
- File uploads are private. Avoid uploading secrets unless your Supabase project and deployment are trusted.
- The usage limit begins with the first live request. Authenticated users receive 7 hours, then wait 8 hours before a new window. A local development fallback is not tamper-resistant; deploy with Supabase Auth to enforce limits for all users.

## Tests

```bash
pytest -q
```
