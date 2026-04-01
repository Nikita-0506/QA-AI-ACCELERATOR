# QA Intelligence Agent 🤖

AI-powered test analysis tool that correlates code changes with test results to explain what broke and why.

## Features

- 📊 Compare test runs (baseline vs current)
- 🔍 Analyze Git commits and diffs
- 🎯 Classify changes (locators, features, steps, page objects)
- ❌ Detect regressions and improvements
- 🤖 AI-powered root cause analysis
- 📥 Export intelligence reports (JSON)
- 🌐 Works with any Git repository

## Supported Report Formats

- Cucumber JSON
- TestNG XML

## Installation

```bash
# Clone this repo
git clone <your-agent-repo-url>
cd qa-intelligence-agent

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Mac/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt