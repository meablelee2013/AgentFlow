# AgentFlow Development Guide

## Branching Convention

- Always start new work from `main` (master), never from an existing feature branch.
- Before starting a new task: `git checkout main && git pull origin main && git checkout -b feat/<new-feature>`
- This ensures each feature branch is independent and avoids carrying unrelated changes from stale branches.

## Project Structure

- `backend/` — FastAPI + LangGraph application
- `frontend/` — React + Vite + ReactFlow application
- `docs/` — Design documents and specs

## Tech Stack

- Backend: Python 3.12+, FastAPI, LangGraph, LangChain, PostgreSQL
- Frontend: TypeScript, React 18, Vite, ReactFlow (@xyflow/react), Tailwind CSS "4.0"
