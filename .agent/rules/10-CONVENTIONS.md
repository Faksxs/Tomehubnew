---
trigger: always_on
---

Frontend (React):
- Functional components only
- Strict TypeScript (no any)
- Tailwind utility-first, consistent spacing
- Accessible forms (label, aria)

Backend (FastAPI):
- Async endpoints only
- Pydantic models required
- Clear separation: router / service / repository
- Explicit error handling

Firebase Functions:
- Small single-responsibility functions
- Explicit auth checks
- No business logic duplication

General:
- No magic strings
- No silent failures
