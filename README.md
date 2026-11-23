# Nonprofit Grant-Matcher & Summarizer Bot

A Streamlit app that compares a nonprofit's profile with a grant's guidelines (pasted or uploaded as a PDF). It gives a fit rating, eligibility flags, key dates and requirements, and a 7-part application outline you can download as Markdown. It uses Claude through the Anthropic API.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Paste your Anthropic API key in the sidebar, or put it in `.streamlit/secrets.toml` as `ANTHROPIC_API_KEY = "..."`. That file is ignored by git.

## Deploy
On share.streamlit.io, choose this repository, branch `main`, and main file `app.py`. Then add `ANTHROPIC_API_KEY` under Advanced settings → Secrets.
