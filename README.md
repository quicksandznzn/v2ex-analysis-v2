V2EX topic analyzer CLI using the V2EX API v2 and OpenAI Agents.

Setup
- Create a V2EX Personal Access Token (PAT) and set `V2EX_TOKEN`.
- Set `OPENAI_API_KEY`.
- Optional: set `OPENAI_BASE_URL` and `OPENAI_MODEL` in `.env`.
- Optional: set `OPENAI_AGENTS_DISABLE_TRACING=true` to disable agents tracing.

Install deps (uv)
```
uv sync
```

Usage
```
uv run v2ex-agent --topic_id 12345

# or without installing the script entrypoint
uv run python main.py --topic_id 12345
```

Output
```
analysis_outputs/analysis_12345.md
```

Useful flags
```
--max-pages 5
```
