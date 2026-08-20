#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK_UNDER_TEST="$REPO_ROOT/hooks/custom/telemetry"

FAILURES=0
TEST_ROOT="$(mktemp -d)"

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

pass() {
    echo "  [PASS] $1"
}

fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}

# Build a transcript with one turn that switches skills partway through.
make_transcript() {
    local path="$1"
    python3 - "$path" <<'PY'
import json, sys

def assistant(ts, uuid, out, tools=(), stop="tool_use"):
    return {"type": "assistant", "uuid": uuid, "timestamp": ts, "gitBranch": "feat/telemetry-hook",
            "version": "2.1.4", "effort": "high",
            "message": {"model": "claude-opus-5", "stop_reason": stop,
                        "content": [{"type": "tool_use", "name": n, "input": i, "id": "t"}
                                    for n, i in tools],
                        "usage": {"input_tokens": 2, "output_tokens": out,
                                  "output_tokens_details": {"thinking_tokens": 0},
                                  "cache_read_input_tokens": 0,
                                  "cache_creation": {"ephemeral_1h_input_tokens": 0,
                                                     "ephemeral_5m_input_tokens": 0}}}}

records = [
    {"type": "mode", "mode": "normal"},
    {"type": "permission-mode", "permissionMode": "auto"},
    {"type": "user", "timestamp": "2026-08-21T04:00:00Z", "message": {"content": "go"}},
    assistant("2026-08-21T04:00:01Z", "u1", 10,
              tools=[("Skill", {"skill": "superpowers:test-driven-development"})]),
    assistant("2026-08-21T04:00:31Z", "u2", 8100, tools=[("Bash", {})]),
    assistant("2026-08-21T04:00:41Z", "u3", 100,
              tools=[("Skill", {"skill": "superpowers:requesting-code-review"})]),
    assistant("2026-08-21T04:01:11Z", "u4", 2400, stop="end_turn"),
]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    for record in records:
        handle.write(json.dumps(record) + "\n")
PY
}

run_hook() {
    local home="$1" outdir="$2" payload="$3"
    printf '%s' "$payload" | env -i PATH="${PATH:-}" HOME="$home" \
        SUPERPOWERS_TELEMETRY_DIR="$outdir" \
        CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
        bash "$HOOK_UNDER_TEST"
}

echo "test-telemetry.sh"

# --- 1. a skill switch inside one turn produces two rows -------------------
CASE="$TEST_ROOT/case1"
mkdir -p "$CASE/home" "$CASE/out"
make_transcript "$CASE/transcript.jsonl"
PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({
  "session_id": "sess-1", "hook_event_name": "Stop",
  "transcript_path": sys.argv[1], "cwd": sys.argv[2]}))' \
  "$CASE/transcript.jsonl" "$REPO_ROOT")"

STDOUT="$(run_hook "$CASE/home" "$CASE/out" "$PAYLOAD")"
STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    pass "hook exits 0"
else
    fail "hook exits 0 (got $STATUS)"
fi

if [ -z "$STDOUT" ]; then
    pass "hook writes nothing to stdout"
else
    fail "hook writes nothing to stdout"
    printf '%s\n' "$STDOUT" | sed 's/^/      /'
fi

OUT_FILE="$CASE/out/2026-08.jsonl"
if [ -f "$OUT_FILE" ]; then
    pass "monthly jsonl is created"
else
    fail "monthly jsonl is created"
fi

RESULT="$(python3 - "$OUT_FILE" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
by_skill = {r["skill"]: r for r in rows}
checks = [
    ("row count is 3", len(rows) == 3),
    ("tdd row exists", "superpowers:test-driven-development" in by_skill),
    ("review row exists", "superpowers:requesting-code-review" in by_skill),
    ("all rows share turn 1", {r["turn"] for r in rows} == {1}),
    ("tdd tokens isolated",
     by_skill.get("superpowers:test-driven-development", {}).get("tokens", {}).get("out") == 8200),
    ("review tokens isolated",
     by_skill.get("superpowers:requesting-code-review", {}).get("tokens", {}).get("out") == 2400),
    ("tdd exec_ms isolated",
     by_skill.get("superpowers:test-driven-development", {}).get("exec_ms") == 40000),
    ("review exec_ms isolated",
     by_skill.get("superpowers:requesting-code-review", {}).get("exec_ms") == 30000),
    ("phase mapped",
     by_skill.get("superpowers:requesting-code-review", {}).get("phase") == "reviewing"),
    ("branch taken from transcript", rows[0]["branch"] == "feat/telemetry-hook"),
    ("schema_version stamped", {r["schema_version"] for r in rows} == {1}),
    ("skill_rev resolved",
     by_skill.get("superpowers:test-driven-development", {}).get("skill_rev") is not None),
]
for label, ok in checks:
    print(("OK " if ok else "NG ") + label)
PY
)"
while IFS= read -r line; do
    case "$line" in
        OK\ *) pass "${line#OK }" ;;
        NG\ *) fail "${line#NG }" ;;
    esac
done <<<"$RESULT"

# --- 2. re-running the hook does not duplicate rows ------------------------
run_hook "$CASE/home" "$CASE/out" "$PAYLOAD" >/dev/null
LINES="$(wc -l <"$OUT_FILE")"
if [ "$LINES" -eq 3 ]; then
    pass "second run adds no duplicate rows"
else
    fail "second run adds no duplicate rows (got $LINES)"
fi

# --- 3. a missing transcript is silent ------------------------------------
CASE2="$TEST_ROOT/case2"
mkdir -p "$CASE2/home" "$CASE2/out"
PAYLOAD2='{"session_id":"sess-2","hook_event_name":"Stop","transcript_path":"/nonexistent","cwd":"/tmp"}'
STDOUT2="$(run_hook "$CASE2/home" "$CASE2/out" "$PAYLOAD2")"
if [ $? -eq 0 ] && [ -z "$STDOUT2" ]; then
    pass "missing transcript exits 0 with no output"
else
    fail "missing transcript exits 0 with no output"
fi

# --- 4. garbage on stdin is silent ----------------------------------------
STDOUT3="$(run_hook "$CASE2/home" "$CASE2/out" 'not json at all')"
if [ $? -eq 0 ] && [ -z "$STDOUT3" ]; then
    pass "garbage stdin exits 0 with no output"
else
    fail "garbage stdin exits 0 with no output"
fi

# --- 5. a broken transcript line does not stop the rest -------------------
CASE3="$TEST_ROOT/case3"
mkdir -p "$CASE3/home" "$CASE3/out"
make_transcript "$CASE3/transcript.jsonl"
sed -i '4i {broken json' "$CASE3/transcript.jsonl"
PAYLOAD3="$(python3 -c 'import json,sys; print(json.dumps({
  "session_id": "sess-3", "hook_event_name": "Stop",
  "transcript_path": sys.argv[1], "cwd": sys.argv[2]}))' \
  "$CASE3/transcript.jsonl" "$REPO_ROOT")"
run_hook "$CASE3/home" "$CASE3/out" "$PAYLOAD3" >/dev/null
if [ -f "$CASE3/out/2026-08.jsonl" ] && [ "$(wc -l <"$CASE3/out/2026-08.jsonl")" -ge 2 ]; then
    pass "a broken line does not stop the rest"
else
    fail "a broken line does not stop the rest"
fi

# --- 6. no python3 on PATH is silent --------------------------------------
# PATH gets a directory holding bash and nothing else, so `command -v python3`
# inside the wrapper fails. bash is invoked by absolute path, because `env`
# would otherwise have to find it on the PATH we just emptied.
CASE4="$TEST_ROOT/case4"
mkdir -p "$CASE4/home" "$CASE4/out" "$TEST_ROOT/nopython"
BASH_BIN="$(command -v bash)"
ln -sf "$BASH_BIN" "$TEST_ROOT/nopython/bash"
STDOUT4="$(printf '%s' "$PAYLOAD" | env -i PATH="$TEST_ROOT/nopython" HOME="$CASE4/home" \
    SUPERPOWERS_TELEMETRY_DIR="$CASE4/out" "$BASH_BIN" "$HOOK_UNDER_TEST")"
if [ $? -eq 0 ] && [ -z "$STDOUT4" ]; then
    pass "no python3 exits 0 with no output"
else
    fail "no python3 exits 0 with no output"
fi

# --- 7. no prompt text reaches the output ---------------------------------
if grep -q '"go"' "$OUT_FILE"; then
    fail "prompt text does not leak into the output"
else
    pass "prompt text does not leak into the output"
fi

# --- 8. the python unit test suite ------------------------------------------
UNIT_LOG="$TEST_ROOT/unittest.log"
if python3 -m unittest discover -s "$REPO_ROOT/tests/hooks/telemetry" -p 'test_*.py' \
        >"$UNIT_LOG" 2>&1; then
    pass "python unit test suite passes"
else
    fail "python unit test suite passes"
    sed 's/^/      /' "$UNIT_LOG"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "All telemetry hook tests passed."
    exit 0
fi
echo "$FAILURES test(s) failed."
exit 1
