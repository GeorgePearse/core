# MCP Server Integration

Genesis includes a **Model Context Protocol (MCP)** server that allows AI coding assistants (like Claude Desktop, Cursor, and others) to interact with evolution experiments directly.

## What is MCP?

MCP (Model Context Protocol) is an open standard that enables AI assistants to access external tools and data sources. By exposing Genesis through MCP, you can manage evolution experiments using natural language through your favorite AI assistant.

## Current Capabilities

The Genesis MCP server (`genesis/mcp_server.py`) provides the following tools:

### 1. List Experiments
```
list_experiments(limit: int = 10)
```
Lists recent evolution experiments with their status and scores.

**Example Usage** (via Claude Desktop):
> "Show me my recent Genesis experiments"

### 2. Get Experiment Metrics
```
get_experiment_metrics(run_path: str)
```
Retrieves detailed metrics for a specific experiment run.

**Example Usage**:
> "What are the metrics for my circle packing experiment from yesterday?"

### 3. Launch Experiment
```
launch_experiment(variant: str, generations: int = None, description: str = None)
```
Starts a new evolution experiment in the background.

**Example Usage**:
> "Launch a new circle packing experiment with 50 generations"

### 4. Read Best Code
```
read_best_code(run_path: str)
```
Reads the best discovered code from a completed experiment.

**Example Usage**:
> "Show me the best code from my HNSW optimization run"

---

## Setup Instructions

### For Claude Desktop

1. **Locate your Claude config file**:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. **Add Genesis MCP server**:
```json
{
  "mcpServers": {
    "genesis": {
      "command": "python3",
      "args": ["-m", "genesis.mcp_server"],
      "cwd": "/absolute/path/to/Genesis"
    }
  }
}
```

3. **Restart Claude Desktop**

4. **Test the integration**:
   - Open Claude Desktop
   - Type: "List my recent Genesis experiments"
   - Claude should now have access to the Genesis MCP tools

### For Cursor

Cursor supports MCP through its settings. Add the same configuration to Cursor's MCP settings.

### For Other MCP Clients

Any MCP-compatible client can connect to the Genesis server using the configuration above.

---

## Example Workflows

### Workflow 1: Monitor Evolution Progress

```
You: "List my recent Genesis experiments"
Claude: [Shows list of experiments with status and scores]

You: "Get metrics for the circle_packing run from 2025-01-15"
Claude: [Displays detailed metrics including fitness scores, generations, etc.]

You: "Show me the best code from that run"
Claude: [Displays the evolved Python/Rust code]
```

### Workflow 2: Launch and Track Experiments

```
You: "Launch a new mask_to_seg experiment with 100 generations"
Claude: [Starts experiment in background, provides PID and log file location]

You: "Check if it's finished yet"
Claude: [Lists experiments, shows status]
```

### Workflow 3: Compare Solutions

```
You: "Show me the best circle packing solutions from my last 3 runs"
Claude: [Retrieves and displays code from multiple experiments]

You: "Which one has the highest fitness?"
Claude: [Analyzes metrics and reports the winner]
```

---

## Architecture

```
┌─────────────────┐
│ AI Assistant    │
│ (Claude/Cursor) │
└────────┬────────┘
         │ MCP Protocol
         │ (stdio)
         ▼
┌─────────────────┐
│ genesis.mcp     │
│ _server.py      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Genesis         │
│ Evolution       │
│ Framework       │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ Results         │
│ Directory       │
│ (experiments,   │
│  metrics, code) │
└─────────────────┘
```

The MCP server acts as a bridge:
1. AI assistant sends natural language request
2. MCP protocol translates to tool calls
3. MCP server interacts with Genesis filesystem/launches processes
4. Results flow back to AI assistant
5. AI assistant presents results in natural language

---

## Troubleshooting

### "Tool not found" errors
- Ensure Genesis is installed: `pip install -e .`
- Check that `genesis.mcp_server` is importable: `python -m genesis.mcp_server`

### "Results not found"
- Verify your `results/` directory exists
- The server looks for results in `$CWD/results` by default
- Ensure experiments have completed (check for `best/` directory)

### Experiments won't launch
- Check that the `variant` name is correct (must exist in `configs/variant/`)
- Verify Python path and Genesis installation
- Check logs at `/tmp/genesis_mcp_<variant>.log`

### Claude Desktop doesn't show Genesis tools
- Restart Claude Desktop after config changes
- Check config file JSON syntax (use a JSON validator)
- Ensure `cwd` path is absolute, not relative
- Check Claude Desktop logs for MCP server errors

---

## Future Enhancements

See [Roadmap - MCP Server Expansion](roadmap.md#mcp-server-expansion) for planned features including:
- Real-time experiment monitoring
- Interactive evolution control (pause/resume/tune)
- Code analysis and comparison tools
- Natural language experiment queries
- Multi-user collaboration

---

## Related Documentation

- [Getting Started](getting_started.md) - Genesis basics
- [Configuration](configuration.md) - Experiment setup
- [WebUI](webui.md) - Web-based visualization
- [Developer Guide](developer_guide.md) - Contributing to MCP server

---

## Example: Using Genesis from Claude Desktop

**Screenshot workflow** (conceptual):

```
╭──────────────────────────────────────────────╮
│ Claude Desktop                               │
├──────────────────────────────────────────────┤
│ You: Show me my recent Genesis experiments  │
│                                              │
│ Claude: I can see 5 recent experiments:     │
│                                              │
│ 1. circle_packing (2025-01-15)              │
│    Status: Completed                         │
│    Best Score: 0.892                         │
│                                              │
│ 2. mask_to_seg_rust (2025-01-14)            │
│    Status: Running                           │
│    Current Gen: 45/100                       │
│                                              │
│ 3. squeeze_hnsw (2025-01-13)                │
│    Status: Completed                         │
│    Best Score: 0.954                         │
│                                              │
│ Would you like to see details for any?      │
╰──────────────────────────────────────────────╯
```

---

## Security Considerations

The MCP server can:
- Read files from the `results/` directory
- Launch subprocess experiments
- Access experiment configuration

**Recommendations**:
- Only use with trusted AI assistants
- Review launched commands before execution
- Consider running in isolated environment for sensitive workloads
- Set appropriate file permissions on results directory

---

## Contributing

To add new MCP tools to Genesis:

1. **Define the tool** in `handle_list_tools()`:
```python
Tool(
    name="my_new_tool",
    description="What it does",
    inputSchema={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "..."}
        }
    }
)
```

2. **Implement the handler** in `handle_call_tool()`:
```python
elif name == "my_new_tool":
    # Your logic here
    return [TextContent(type="text", text=result)]
```

3. **Test with MCP inspector**:
```bash
npx @modelcontextprotocol/inspector python3 -m genesis.mcp_server
```

4. **Document in this file** and submit a PR!

---

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Guide](https://docs.anthropic.com/claude/docs/model-context-protocol)
