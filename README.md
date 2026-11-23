# Nonprofit Grant-Matcher & Summarizer Bot

A Streamlit app that compares a nonprofit's profile against grant guidelines (pasted text or PDF), rates the fit, flags eligibility issues and key requirements, and drafts a 7-part application outline you can download as Markdown.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Enter your Anthropic API key in the sidebar, or put it in `.streamlit/secrets.toml` (do not commit that file):

```toml
ANTHROPIC_API_KEY = "your-key-here"
```

## Deploy on Streamlit Community Cloud

Set **Main file path** to `app.py`, and add `ANTHROPIC_API_KEY` under **Advanced settings → Secrets**.

> The AI output is a starting point. Verify all local data, numbers, and dates before submitting an application.
