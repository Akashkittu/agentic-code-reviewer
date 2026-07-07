# Repo Review Agent

An agentic code review workflow that analyzes a local repository, GitHub repository URL, or uploaded ZIP file and returns a structured review report.

This project was built for the take-home assignment: **Option B — Code Review Agent**.

## Problem

Manual code review takes time, and small issues can be missed, such as:

- missing setup instructions
- missing dependency files
- no tests
- hardcoded secrets
- unsafe code patterns
- poor repo hygiene
- weak README documentation

This prototype automates the first-pass repository review using a multi-step agentic workflow.

## Architecture

```text
User input
↓
Pydantic validation
↓
Repo loader
↓
LangGraph workflow
↓
Planner chooses next tool
↓
Tool executor runs selected tool
↓
Tool result is saved in state
↓
Planner chooses next step
↓
Final structured report