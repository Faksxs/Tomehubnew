# TomeHub GPT Action Setup

This guide wires TomeHub into a Custom GPT using a read-only Action.

## Preconditions

- Production backend must expose `https://api.tomehub.nl/ext/v1/search`
- Production backend must have:
  - `EXTERNAL_API_ENABLED=true`
  - `EXTERNAL_API_KEY_PEPPER` configured
  - `TOMEHUB_EXTERNAL_API_KEYS` migration applied
- You need one production TomeHub external API key

## Why Action, not App

- TomeHub already exposes a REST API
- Custom GPT Actions can import an OpenAPI schema and call external APIs directly
- Apps/MCP are a heavier path and are not needed for this use case

Official references:

- Creating a GPT: https://help.openai.com/en/articles/8554397-creating-a-gpt00%3A00
- GPT Action authentication: https://platform.openai.com/docs/actions/authentication
- GPT Actions production notes: https://platform.openai.com/docs/actions/production

## Files

- OpenAPI schema: `apps/backend/openapi/tomehub_gpt_action.yaml`

## ChatGPT Builder Steps

1. Open `https://chatgpt.com/gpts/editor`
2. Create a new GPT
3. In `Configure`:
   - Name: `TomeHub Research`
   - Description: `Uses TomeHub as a live private retrieval layer for grounded answers.`
4. In `Instructions`, paste the instruction block below
5. Under `Actions`, choose `Import from OpenAPI`
6. Paste the contents of `apps/backend/openapi/tomehub_gpt_action.yaml`
7. In `Authentication`, choose `API Key`
8. Use the production TomeHub external API key as the bearer secret
9. Save and test with `What do my TomeHub sources say about X?`

## Recommended Instructions

```text
You are a research assistant grounded in TomeHub.

Use the TomeHub action whenever the user asks about their books, notes, highlights, insights, reading themes, or stored document content.

Rules:
- Prefer TomeHub action results over guesswork.
- If the question is about the user's stored knowledge, call TomeHub search before answering.
- Quote or paraphrase only from returned TomeHub evidence.
- Cite the source title when answering.
- If TomeHub returns weak or no evidence, say that clearly.
- Do not claim you searched TomeHub if you did not call the action.
- Use include_private_notes=true only when the question clearly needs personal notes or highlights.
- Keep answers grounded and concise.
```

## Recommended Test Prompts

- `What do my TomeHub sources say about zaman?`
- `Which TomeHub sources discuss etik and olum together?`
- `Summarize my notes and highlights about Levinas.`
- `What evidence do I have in TomeHub about devrim?`

## Important Note

The current local key is only for local testing. Use a separate production key in the GPT builder.
