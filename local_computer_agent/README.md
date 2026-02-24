## Local-First Computer Use Agent (LCA)

### Run

Install deps:

```bash
uv sync
```

Run the agent:

```bash
uv run local-computer-agent
```

### Provide an action (recommended: JSON file)

```bash
uv run local-computer-agent --action-file examples/wait_action.json
```

### Provide an action (JSON string)

PowerShell-friendly quoting (single quotes outside, double quotes inside):

```bash
uv run local-computer-agent --action-json '{"action_type":"wait","coordinates":null,"payload":"0.2","expected_outcome":"Warmup wait completes","critical":false}'
```

