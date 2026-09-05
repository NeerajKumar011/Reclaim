# Contributing to RECLAIM

Thank you for your interest in contributing to RECLAIM! We welcome contributions to our failure diagnosis models, deterministic policy rules, evaluation harness, and integration adapters.

---

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/NeerajKumar011/Reclaim.git
   cd Reclaim
   ```

2. **Set up virtual environment & install dependencies**:
   - **🪟 Windows**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     pip install -r requirements.txt
     copy .env.example .env
     ```
   - **🐧 Linux (Kali Linux / Ubuntu)**:
     ```bash
     sudo apt update && sudo apt install -y python3-venv python3-pip
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     cp .env.example .env
     ```
   - **🍎 macOS**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     cp .env.example .env
     ```

3. **Configure Environment Variables**:
   Edit `.env` and set `GEMINI_API_KEY` or `GROQ_API_KEY`.

4. **Initialize Database & Models**:
   ```bash
   python -m alembic upgrade head
   python -m reclaim.synthetic_data.seed_db
   ```

---

## Code Architecture & Core Principles

1. **The LLM-Proposes / Code-Decides Boundary**:
   - The LLM is strictly an untrusted advisor for root-cause classification and Hinglish conversational phrasing.
   - The LLM **never** decides whether to contact a customer, what channel to use, what discount to authorize, or when to retry.
   - All financial and dispatch rules **must** reside in deterministic Python code (`reclaim/policy/rules.py`).

2. **Zero Ground-Truth Leaks**:
   - Code inside `reclaim/eval/replay.py` and downstream evaluation must strip all `ground_truth` fields prior to diagnosis and policy evaluation.

3. **Invariants & Testing**:
   - Every pull request must maintain 100% test suite pass rate:
     ```bash
     pytest -v
     ```
   - Decision distribution invariant must hold: **ACT + WAIT + STOP = Total Records**.

---

## Submitting Pull Requests

1. Fork the repo and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Ensure all tests pass (`pytest -v`).
3. Commit your changes with clear, descriptive commit messages.
4. Open a Pull Request explaining the rationale, test evidence, and any policy impact.
