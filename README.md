# MIT Learn path demo

Type what you want to learn (and a bit about yourself) and get a short, ordered
learning plan built only from resources returned by the MIT Learn search API.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
.venv/bin/streamlit run app.py
```

Optional: set `APP_PASSWORD` (in `.env` or Streamlit secrets) to require a password.

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. At https://share.streamlit.io create a new app pointing at `app.py`.
3. In Advanced settings → Secrets, add:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "choose-a-password"
   ```
4. Deploy and share the URL plus the password.

## How it works

1. Claude splits the request into 3–6 sub-topics, prerequisites first.
2. Each sub-topic is searched on MIT Learn; the top 5 results are kept.
3. Claude picks up to 6 resources from that pool, orders them, and explains the plan.
4. Code verifies every pick was actually returned by the search.
