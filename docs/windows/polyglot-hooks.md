# Cross-Platform Polyglot Hooks for Claude Code

Claude Code plugins need hooks that work on Windows, macOS, and Linux. This document describes the single generic dispatcher pattern used in `hooks/run-hook.cmd`.

> **Authoritative source:** `hooks/run-hook.cmd` is the canonical implementation. When this document and the code diverge, trust the code.

## The Problem

Claude Code runs hook commands through a shell:
- **macOS/Linux**: bash or sh
- **Windows with Git Bash installed**: Git Bash
- **Windows without Git Bash**: PowerShell (older versions used CMD.exe)

Neither Windows fallback shell can parse our command string: PowerShell treats
a leading quoted path as a string expression and errors on the next bareword,
and CMD.exe's `/c` quoting rules strip the outer quotes when the path contains
a metacharacter such as `(`. Our hooks therefore declare `"shell": "bash"`
(supported since Claude Code 2.1.81; older versions ignore the key), which
forces the Git Bash route and, when Git Bash is absent, produces an actionable
"install Git for Windows" error instead of a shell parser failure.

This creates several challenges:

1. **Script execution**: Windows CMD can't execute `.sh` files directly
2. **Path format**: Windows uses backslashes (`C:\path`), Unix uses forward slashes (`/path`)
3. **Environment variables**: `$VAR` syntax doesn't work in CMD
4. **`.sh` auto-prepend**: Claude Code on Windows automatically prepends `bash` to any command that contains `.sh` in its path — this interferes with the dispatcher if scripts have extensions

## The Solution: Extensionless Scripts + Single Generic Dispatcher

The repo uses one generic `run-hook.cmd` dispatcher for all hooks. Hook scripts are **extensionless** (`session-start`, not `session-start.sh`). This is deliberate: it prevents Claude Code's Windows auto-detection from prepending `bash` to the dispatcher command and breaking it.

### File Structure

```
hooks/
├── hooks.json          # Points to run-hook.cmd with extensionless script name
├── run-hook.cmd        # Cross-platform dispatcher (the polyglot wrapper)
└── session-start       # Actual hook logic — extensionless bash script
```

### hooks.json

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" session-start",
            "shell": "bash",
            "async": false
          }
        ]
      }
    ]
  }
}
```

The path is quoted because `${CLAUDE_PLUGIN_ROOT}` may contain spaces.

## How `run-hook.cmd` Works at a High Level

`run-hook.cmd` is a polyglot script: Windows treats the first block as batch
commands, while Unix shells treat that block as a no-op heredoc and continue
after it.

Do not copy an implementation from this document. Read `hooks/run-hook.cmd`
directly when changing the dispatcher, and run `tests/hooks/test-session-start.sh`
afterward.

### How it works on Windows (CMD.exe)

1. The batch section validates the script name and resolves the hook directory
   from the dispatcher's own location.
2. It picks a bash, in order:
   - `C:\Program Files\Git\bin\bash.exe`
   - `C:\Program Files (x86)\Git\bin\bash.exe`
   - the bash beside whatever `git` is on `PATH` — `<root>\cmd\git.exe` gives
     `<root>\bin\bash.exe` — which covers a Git for Windows installed anywhere
     else
   - `bash` on `PATH`, but only when `uname -o` reports `Msys` or `Cygwin`
     (MSYS2, Cygwin, or a Git Bash reached through `PATH`)
3. If a bash was picked, it runs the named extensionless hook script from the
   hooks directory and exits with **the hook's own** exit code.
4. If no usable bash is found, the dispatcher exits `0` silently — the plugin
   continues working, it just skips the hook.
5. `exit /b` stops CMD before it reaches the Unix section.

The flavour check in the last step is not paranoia. On a machine with WSL
installed, `where bash` finds `C:\Windows\System32\bash.exe` — the WSL
launcher, which cannot open a Windows path. Handing it the hook starts WSL only
to fail, which is neither running the hook nor the silent skip step 4
describes.

### How it works on Unix (bash/sh)

1. `: << 'CMDBLOCK'` opens a heredoc on a no-op command.
2. The entire CMD batch block is consumed by the heredoc and ignored.
3. After `CMDBLOCK`, bash resolves the script directory and `exec`s the named
   extensionless script directly.

### Key design decisions

| Decision | Why |
|----------|-----|
| Extensionless scripts | Prevents Claude Code's Windows `.sh`-auto-prepend from interfering with the dispatcher command |
| No `-l` (login shell) | Not needed; hook scripts should be self-contained and not depend on login-shell PATH setup |
| No `cygpath` | Bash receives the Windows path directly and handles it correctly; `cygpath` was needed by the old `-c "..."` invocation pattern, not by direct exec |
| Silent exit on no-bash | Avoids breaking the plugin for users who don't have Git for Windows; hook context injection is skipped gracefully |
| Reject a `PATH` bash that is not MSYS/Cygwin | With WSL installed, `where bash` finds the WSL launcher, which cannot open a Windows path. Starting WSL to fail on every hook is worse than skipping the hook |
| Derive bash from `git` before consulting `PATH` | Finds a non-default Git for Windows install without guessing at paths, and avoids paying a WSL cold start to discover the `PATH` bash is unusable |
| One invocation site rather than one per branch | `exit /b %ERRORLEVEL%` inside a parenthesised `if` block expands when the block is *parsed*, before the hook has run. With the calls spread across branches, every hook looked like it succeeded no matter how it exited |

## Writing Cross-Platform Hook Scripts

Your hook logic goes in the extensionless script file. A few portable patterns:

### Do
- Use pure bash builtins when possible
- Use `$(command)` instead of backticks
- Quote all variable expansions: `"$VAR"`

### Avoid
- Relying on PATH-dependent tools without fallbacks (the hook runs without `-l`, so login-shell PATH is not set)
- Giving scripts a `.sh` extension — this triggers Claude Code's Windows auto-prepend

### Example: JSON escaping without external tools

```bash
escape_for_json() {
    local input="$1"
    local output=""
    local i char
    for (( i=0; i<${#input}; i++ )); do
        char="${input:$i:1}"
        case "$char" in
            $'\\') output+='\\' ;;
            '"') output+='\"' ;;
            $'\n') output+='\n' ;;
            $'\r') output+='\r' ;;
            $'\t') output+='\t' ;;
            *) output+="$char" ;;
        esac
    done
    printf '%s' "$output"
}
```

## Troubleshooting

### "bash is not recognized"

CMD couldn't find a usable bash in any of the four places the dispatcher looks. It exits silently (0) rather than erroring, so the hook is skipped. Install Git for Windows at the standard path, or put `git` on `PATH` so the dispatcher can find the bash beside it.

Note that having *a* `bash` on `PATH` is not enough on its own: if it is WSL's launcher, the dispatcher rejects it on purpose and skips the hook.

### Hook runs on Unix but does nothing on Windows

Check that the script filename is **extensionless** in `hooks.json`. A command like `run-hook.cmd session-start.sh` can trigger Claude Code's `.sh` auto-detection and bypass the intended CMD dispatcher path, or just try to run a non-existent `session-start.sh` script.

### Hook doesn't fire at all

Verify the `matcher` in `hooks.json` matches the event type your harness emits. Claude Code uses `startup|clear|compact`; Cursor uses `sessionStart`. Check `hooks-cursor.json` for the Cursor variant.

## Related Issues

- [anthropics/claude-code#9758](https://github.com/anthropics/claude-code/issues/9758) — `.sh` scripts open in editor on Windows
- [anthropics/claude-code#3417](https://github.com/anthropics/claude-code/issues/3417) — Hooks don't work on Windows
