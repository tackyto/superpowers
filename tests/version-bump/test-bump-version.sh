#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT_SOURCE="$REPO_ROOT/scripts/bump-version.sh"
TEST_ROOT="$(mktemp -d)"

cleanup() {
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_fixture() {
  local repo="$1"
  local yaml_body="$2"

  mkdir -p "$repo/scripts" "$repo/.hermes-plugin"
  cp "$SCRIPT_SOURCE" "$repo/scripts/bump-version.sh"
  cat >"$repo/.version-bump.json" <<'JSON'
{
  "files": [
    { "path": "package.json", "field": "version" },
    { "path": ".hermes-plugin/plugin.yaml", "field": "version" }
  ],
  "audit": { "exclude": [] }
}
JSON
  cat >"$repo/package.json" <<'JSON'
{
  "name": "fixture",
  "version": "1.2.3"
}
JSON
  printf '%s\n' "$yaml_body" >"$repo/.hermes-plugin/plugin.yaml"
}

happy_repo="$TEST_ROOT/happy"
make_fixture "$happy_repo" $'name: superpowers\nversion: 1.2.3'

/bin/bash "$happy_repo/scripts/bump-version.sh" --check >"$TEST_ROOT/check.out"
/bin/bash "$happy_repo/scripts/bump-version.sh" --audit >"$TEST_ROOT/audit.out"
/bin/bash "$happy_repo/scripts/bump-version.sh" 2.3.4 >"$TEST_ROOT/bump.out"

[[ "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.4" ]] \
  || fail "JSON manifest was not bumped"
[[ "$(yq -r '.version' "$happy_repo/.hermes-plugin/plugin.yaml")" == "2.3.4" ]] \
  || fail "YAML manifest was not bumped"

jq -e '
  any(.files[];
    .path == ".hermes-plugin/plugin.yaml" and .field == "version")
' "$REPO_ROOT/.version-bump.json" >/dev/null \
  || fail "Hermes manifest is not registered"

invalid_repo="$TEST_ROOT/invalid"
make_fixture "$invalid_repo" $'name: superpowers\nversion: 123'
cp "$invalid_repo/package.json" "$TEST_ROOT/package.before"
cp "$invalid_repo/.hermes-plugin/plugin.yaml" "$TEST_ROOT/plugin.before"

if /bin/bash "$invalid_repo/scripts/bump-version.sh" 2.3.4 \
  >"$TEST_ROOT/invalid.out" 2>&1; then
  fail "bump accepted a non-string YAML version"
fi

cmp -s "$TEST_ROOT/package.before" "$invalid_repo/package.json" \
  || fail "JSON manifest changed before YAML validation failed"
cmp -s "$TEST_ROOT/plugin.before" "$invalid_repo/.hermes-plugin/plugin.yaml" \
  || fail "invalid YAML manifest changed"

# --- a jq that emits CRLF, the way jq.exe does on Windows ------------------
#
# Native jq.exe opens stdout in text mode, so every line it prints ends in
# \r\n. Under Git Bash that puts $'version\r' into the field name -- yq's key
# lookup then misses and the bump aborts -- and sends the JSON manifests
# through a rewrite that leaves CRLF on every line. Neither is visible on a
# platform where jq prints LF, so the shim below reproduces both here.

crlf_repo="$TEST_ROOT/crlf"
make_fixture "$crlf_repo" $'name: superpowers\nversion: 1.2.3'
printf 'v2.3.4 released\n' >"$crlf_repo/CHANGELOG.md"
printf 'pinned at 2.3.4\n' >"$crlf_repo/notes.md"
cat >"$crlf_repo/.version-bump.json" <<'JSON'
{
  "files": [
    { "path": "package.json", "field": "version" },
    { "path": ".hermes-plugin/plugin.yaml", "field": "version" }
  ],
  "audit": { "exclude": ["CHANGELOG.md"] }
}
JSON

shim_dir="$TEST_ROOT/crlf-shim"
mkdir -p "$shim_dir"
real_jq="$(command -v jq)"
cat >"$shim_dir/jq" <<SHIM
#!/usr/bin/env bash
set -o pipefail
"$real_jq" "\$@" | awk '{ printf "%s\r\n", \$0 }'
SHIM
chmod +x "$shim_dir/jq"

PATH="$shim_dir:$PATH" /bin/bash "$crlf_repo/scripts/bump-version.sh" 2.3.4 \
  >"$TEST_ROOT/crlf.out" 2>&1 \
  || fail "bump failed under a CRLF-emitting jq: $(cat "$TEST_ROOT/crlf.out")"

[[ "$(yq -r '.version' "$crlf_repo/.hermes-plugin/plugin.yaml")" == "2.3.4" ]] \
  || fail "YAML manifest was not bumped under a CRLF-emitting jq"

if grep -q $'\r' "$crlf_repo/package.json"; then
  fail "bump rewrote the JSON manifest with CRLF line endings"
fi

if grep -q 'CHANGELOG.md' "$TEST_ROOT/crlf.out"; then
  fail "audit exclusions did not apply under a CRLF-emitting jq"
fi

# A version string carrying a stray CR matches nothing, so the audit would
# report "All clear" while an undeclared file sits right there.
if ! grep -q 'notes.md' "$TEST_ROOT/crlf.out"; then
  fail "audit missed an undeclared file under a CRLF-emitting jq"
fi

echo "Version-bump tests passed"
