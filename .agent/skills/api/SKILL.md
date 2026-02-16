---
name: api
description: FastAPI endpoint, route, request-response model, and service-layer implementation guidance for TomeHub backend APIs, ingestion endpoints, and AI-related API flows.
---

# API Skill

Use this skill when the task involves FastAPI route behavior, request/response contracts, endpoint errors, or backend API architecture.

## Triggers
- api
- endpoint
- route
- fastapi
- request model
- response model
- ingestion api

## Rules
1. Keep endpoints async and explicit about failures.
2. Validate inputs with Pydantic models.
3. Keep router, service, and data access responsibilities separated.
4. Return stable response shapes and clear error messages.
