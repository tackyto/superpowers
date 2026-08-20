# Fork-specific hooks

Hooks that exist only in this fork live here, as **new files**. Nothing upstream maintains lives
in this directory, so nothing in it can ever produce a merge conflict.

## Adding a hook

1. Write the hook script in this directory and `chmod +x` it.
2. Register it in `hooks/hooks.json` (and `hooks/hooks-cursor.json` if it should run under
   Cursor). Keep that edit as small as possible — those two files are the only shared conflict
   surface between fork hooks and upstream.
3. Add a row to the custom-hooks table in `docs/fork/DIVERGENCE.md`.

## Invocation

Hook commands are resolved against `${CLAUDE_PLUGIN_ROOT}`, so reference scripts here as:

```json
{
  "type": "command",
  "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/custom/<name>\"",
  "shell": "bash",
  "async": false
}
```

Upstream's `hooks/run-hook.cmd` is a polyglot cmd/bash wrapper used to make the bundled
`session-start` hook work on Windows. Route through it the same way if a fork hook needs to run
on Windows:

```json
"command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" custom/<name>"
```

Note that `run-hook.cmd` is an upstream file — prefer calling your script directly unless Windows
support is actually needed, so there is one less reason to modify it.
