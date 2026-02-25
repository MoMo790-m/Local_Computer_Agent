## Local Computer Agent (LCA)

Local-first desktop automation agent focused on supporting developers.  
The agent runs entirely on your machine, controls the desktop, and uses a tiered
verification strategy to keep actions safe and reliable.

- **Tiered visual verification** using perceptual hashing and a future pluggable VLM.
- **Interactive terminal UI** for natural commands (e.g. `click 500 400`, `browser search ...`).
- **High-level command router** for browser, VS Code, filesystem, and dev workflows.
- **Task planner** that turns goals into concrete steps (`plan fix failing tests in module auth.py`).
- **Environment doctor** that detects and repairs many dependency/config/runtime issues automatically.

The Python package lives under `local_computer_agent/` and is managed with `uv`.

---
### Project structure

```text
Local_Computer_Agent/
│
├── .gitignore
├── README.md
├── pyproject.toml          # uv project configuration and dependencies
├── uv.lock                 # uv lockfile
├── .python-version         # Python version pin
│
├── examples/
│   └── wait_action.json    # Example AgentAction payload
│
└── src/
    └── local_computer_agent/
        ├── __init__.py
        ├── main.py                # Entry point and interactive REPL
        ├── command_router.py      # High-level commands: browser, code, file, dev, doctor
        ├── action_orchestrator.py # Executes UI actions and wires verification
        ├── verification.py        # Tier 1 (pHash) + Tier 2 (VLM hook) verification
        ├── schemas.py             # Pydantic models (AgentAction, Tier1Result, Tier2Result)
        ├── planner.py             # Goal->steps planner (`plan ...`)
        └── diagnostics.py         # Environment doctor for deps/config/runtime issues
```

---

### Requirements

- Python `3.13` (managed via `uv`, created automatically).
- Windows desktop (project currently tested on Windows).
- Ability to install Python wheels for:
  - `pyautogui`, `pyscreeze`, `pygetwindow`, `mouseinfo`
  - `opencv-python`, `Pillow`, `ImageHash`
  - `pydantic`, `openai` (VLM integration hook)

> Note: The project uses `uv` to manage dependencies and virtual environments.

---

### Installation

Clone the repository and install dependencies with `uv`:

```bash
git clone https://github.com/MoMo790-m/Local_Computer_Agent.git
cd Local_Computer_Agent/local_computer_agent
uv sync
```

This will create a `.venv` inside `local_computer_agent/` and install all required packages.

---

### Running the agent

From inside `local_computer_agent/`:

```bash
uv run local-computer-agent
```

You should see an interactive shell:

```text
========================================================
 Local-First Computer Agent (Interactive)
 Type 'help' for commands, 'exit' to quit.
========================================================
LCA>
```

Type commands at the `LCA>` prompt. The agent will perform desktop actions and log verification
results in the terminal.

---

### Core concepts

#### Verification manager (Tier 1 + Tier 2)

- **Tier 1 – pHash (fast path)**:
  - Captures `pre` and `post` screenshots around each action.
  - Computes perceptual hashes (pHash) and their Hamming distance.
  - If the distance is above a configurable threshold, Tier 1 passes.
  - If the distance is zero or unexpectedly low, Tier 1 fails and the system can retry or escalate.

- **Tier 2 – VLM visual reasoning (slow path)**:
  - Crops the relevant region around the click/interaction.
  - Currently implemented as a lightweight hook where you can plug in OpenAI or Ollama.
  - Intended to answer questions like: _“Did the login succeed?”_ or _“Is the error banner visible?”_.

Critical actions (e.g. `critical` clicks) always escalate to Tier 2 in addition to Tier 1.

#### Action orchestrator

The `ActionOrchestrator` converts high-level `AgentAction` objects into concrete desktop actions:

- `click (x, y)`
- `type "some text"`
- `drag` relative movements
- `scroll` amounts
- `wait` delays

For each action it:

1. Takes a `pre` screenshot.
2. Performs the UI operation via `pyautogui`.
3. Takes a `post` screenshot and runs Tier 1 verification.
4. If there is no visual change for several retries, it:
   - Sends `Esc`.
   - Clicks a neutral region (to reset focus).
5. If Tier 1 fails or the action is marked `critical`, it calls Tier 2.

---

### Interactive commands

Once the REPL is running (`uv run local-computer-agent`), you can use:

- **Low-level UI actions**

  ```text
  click X Y [critical]      -> click at (X, Y)
  type TEXT                 -> type TEXT at the current focus
  wait SECONDS              -> wait SECONDS (float)
  scroll AMOUNT             -> scroll by AMOUNT (int; negative = up)
  ```

- **High-level desktop automation**

  ```text
  browser open              -> open default browser
  browser search QUERY      -> search QUERY in browser

  code open [PATH]          -> open VS Code on the project or a given file

  file new PATH             -> create empty file
  file write PATH TEXT...   -> overwrite PATH with TEXT
  file append PATH TEXT...  -> append TEXT as a new line to PATH

  dev test                  -> run tests (uv run pytest)
  dev format                -> format code (placeholder: uv run python -m black src)
  dev doctor                -> run environment diagnostics and auto-fixes
  dev cmd ARGS...           -> run arbitrary shell command in project root
  ```

- **Planning**

  ```text
  plan GOAL
  ```

  Example:

  ```text
  LCA> plan fix failing tests in module auth.py
  [PLAN] Steps:
    1. browser search fix failing tests in module auth.py  # Look up documentation or prior art for the goal.
    2. code open                                           # Open the project in VS Code for direct code edits.
    3. file new auth.py                                   # Ensure the target file exists for editing.
    4. dev test                                           # Run the test suite to see the current failure state.
  ...
  ```

  The planner then executes each step automatically, using the command router and orchestrator.

---

### Environment doctor

The **environment doctor** is designed to help developers recover from common local issues
without manual intervention:

- Run:

  ```text
  LCA> dev doctor
  ```

- Behavior:
  1. Executes `uv run pytest`.
  2. If tests pass, it exits.
  3. If tests fail, it parses output for patterns like:
     - `ModuleNotFoundError: No module named 'xyz'`
     - Version conflicts in dependency resolution.
     - `FileNotFoundError` for project-local files.
  4. Applies fixes such as:
     - `uv add xyz`
     - `uv lock --upgrade`
     - Creating missing project files.
  5. Re-runs tests, repeating for several rounds until the issues are resolved or
     no automatic fix can be found.

This makes the agent particularly useful as a **self-healing dev environment assistant**.

---

### One-shot actions (JSON input)

For automation or scripting, you can bypass the REPL and run a single `AgentAction` from the CLI:

```bash
uv run local-computer-agent --action-json '{"action_type":"wait","coordinates":null,"payload":"0.5","expected_outcome":"Short delay completes","critical":false}'
```

Or using a JSON file:

```bash
uv run local-computer-agent --action-file examples/wait_action.json
```

This calls directly into the orchestrator and verification pipeline.

---

### Extensibility

The project is organized so new capabilities can be added with minimal coupling:

- **New commands**: extend `CommandRouter` to add `dev build`, `browser open-url`, etc.
- **New planning patterns**: extend `TaskPlanner` to recognize more goal types and generate richer step lists.
- **Real VLM verification**: implement the Tier 2 hook in `verification.py` using OpenAI or Ollama.
- **Additional diagnostics**: extend `DiagnosticsEngine` with more error patterns and repair strategies.

Because the core pieces (router, planner, orchestrator, verification, diagnostics) are separated,
you can evolve each independently as the agent grows.

