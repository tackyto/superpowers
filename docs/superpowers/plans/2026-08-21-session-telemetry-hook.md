# Session Telemetry Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code のセッションとサブエージェントについて、`(ターン × skill)` を 1 行とする JSONL テレメトリをローカルに記録するフックを追加する。

**Architecture:** `Stop` と `SubagentStop` の 2 フックのみを登録する。フックは bash の薄いラッパ経由で python3 スクリプトを起動し、フックが渡す `transcript_path` の JSONL を**前回の続きから増分で**読み、`Skill` ツール呼び出しを境界として skill セグメントに分割し、時間とトークンを割り当てて `~/.claude/superpowers/telemetry/YYYY-MM.jsonl` に追記する。トークンはフック入力に無いため transcript が唯一の情報源であり、ブランチ名・Claude Code バージョン・モデルも transcript の実値を使うので git サブプロセスは一切起動しない。

**Tech Stack:** bash / python3 標準ライブラリのみ(`json`, `hashlib`, `fcntl`, `datetime`, `os`, `sys`, `time`)。テストは python3 の `unittest`(標準ライブラリ)と bash。

**Spec:** `docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md`

## Global Constraints

これらは全タスクの要件に暗黙に含まれる。

- **python3 標準ライブラリのみ。** pip パッケージを追加しない。`pytest` も使わない(この環境に未インストール。テストは `unittest`)
- **bash ラッパは stdout に一切出力せず、常に `exit 0`。** `Stop` フックの stdout は harness に解釈される
- **git サブプロセスを起動しない。** ブランチ名・バージョンは transcript の実値を使い、リポジトリルートは `.git` をファイルシステム上で探して求める
- `hooks/hooks.json` への変更は `Stop` / `SubagentStop` の 2 ブロック追加のみ。このファイルは upstream との唯一の共有コンフリクト面
- `hooks/hooks-cursor.json` は変更しない
- **プロンプト本文・ファイル内容・ツール引数は記録しない。** 記録するのは skill 名、ツール名と回数、数値、プロジェクト名、ブランチ名のみ
- 出力レコードの `schema_version` は `1`
- 新規ファイルは `hooks/custom/` 配下に置く(`hooks/custom/README.md` の方針)
- 全ての python モジュールは `hooks/custom/telemetry_lib/` パッケージに置き、`hooks/custom/telemetry.py` から `sys.path` 経由で読む
- コミットメッセージは英語。末尾に次の 2 行を付ける:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` と
  `Claude-Session: https://claude.ai/code/session_01JEbHcXv1JKsRSuQBS6ZHk6`
- 作業ブランチは `feat/telemetry-hook`(既存。仕様書のコミット `f5b4dbb` が載っている)

## File Structure

| ファイル | 責務 |
|---|---|
| `hooks/custom/telemetry` | bash 薄ラッパ。python3 の有無を確認し、失敗を握り潰して `exit 0` |
| `hooks/custom/telemetry.py` | エントリポイント。stdin のフック payload を読み、各モジュールを繋ぎ、例外を全て捕捉 |
| `hooks/custom/telemetry_lib/__init__.py` | 空。パッケージ宣言のみ |
| `hooks/custom/telemetry_lib/transcript.py` | transcript 行の分類・増分読み・usage 正規化。純粋関数のみ |
| `hooks/custom/telemetry_lib/skills.py` | skill 名 → phase 写像、`SKILL.md` のハッシュ、`invoked_by` 判定 |
| `hooks/custom/telemetry_lib/segments.py` | セグメント分割と集計。このプロジェクトの中核 |
| `hooks/custom/telemetry_lib/store.py` | JSONL 追記(flock)、状態ファイル、`errors.log`、古い状態の掃除 |
| `tests/hooks/telemetry/fixtures.py` | 合成 transcript レコードのビルダ |
| `tests/hooks/telemetry/test_transcript.py` | `transcript.py` の単体テスト |
| `tests/hooks/telemetry/test_skills.py` | `skills.py` の単体テスト |
| `tests/hooks/telemetry/test_segments.py` | `segments.py` の単体テスト。中核要件の検証を含む |
| `tests/hooks/telemetry/test_store.py` | `store.py` の単体テスト |
| `tests/hooks/test-telemetry.sh` | エンドツーエンド。既存 `test-session-start.sh` の作法に倣う |
| `docs/fork/telemetry.md` | スキーマ、限界、jq レシピ |

分割の理由: `transcript.py` は「Claude Code の transcript 形式を知っている唯一の場所」、`segments.py` は「時間とトークンの帰属ロジックだけを持つ場所」、`store.py` は「ファイルシステムに触る唯一の場所」。この 3 つが混ざると、中核要件のテストがファイル I/O を必要としてしまう。

---

### Task 1: 未検証点の実測と仕様の補正

仕様 §15 の未検証リスクを実測し、実装が依存する前提を確定させる。**このタスクでは製品コードを書かない。** 成果物は仕様書への追記コミット。

**Files:**
- Modify: `docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md`

**Interfaces:**
- Consumes: なし
- Produces: 仕様 §15 に「実測結果」節。Task 4 と Task 6 はこの節に書かれた結論を前提にする

- [ ] **Step 1: サブエージェントの transcript の所在を実測する**

サブエージェントを 1 回起動し、その前後で transcript ファイル群がどう変化するかを見る。

```bash
BEFORE=$(mktemp)
ls -la ~/.claude/projects/*/ > "$BEFORE"
# ここで Agent ツールでサブエージェントを 1 回起動する（例: Explore で "list the files in hooks/"）
# 起動後:
ls -la ~/.claude/projects/*/ > /tmp/after.txt
diff "$BEFORE" /tmp/after.txt
```

続いて sidechain 行の有無を数える。

```bash
python3 - <<'PY'
import json, glob, collections
side = collections.Counter()
files = set()
for path in glob.glob('/home/ubuntu/.claude/projects/*/*.jsonl'):
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get('isSidechain'):
            side[record.get('type')] += 1
            files.add(path)
print('sidechain lines by type:', dict(side))
print('files containing sidechain:', sorted(files))
PY
```

記録すること: sidechain 行が親ファイルに混ざるか / 別ファイルか、`subagent_type` にあたる値がどこかにあるか、親ターンを特定できる手掛かり(`parentUuid` 等)があるか。

- [ ] **Step 2: `Stop` 発火時点で最終 assistant 行が書き込み済みか実測する**

一時的な観測用フックを `~/.claude/settings.json` ではなく手元のシェルで再現する。フック payload は再現できないので、代わりに「直近セッションの最終行の `stop_reason`」を確認する。

```bash
python3 - <<'PY'
import json, glob, os
newest = max(glob.glob('/home/ubuntu/.claude/projects/*/*.jsonl'), key=os.path.getmtime)
last_assistant = None
for line in open(newest, encoding='utf-8', errors='replace'):
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get('type') == 'assistant':
        last_assistant = record
print('file:', newest)
print('last assistant stop_reason:', (last_assistant or {}).get('message', {}).get('stop_reason'))
print('last assistant ts:', (last_assistant or {}).get('timestamp'))
PY
```

記録すること: 完了済みターンの最終 assistant 行の `stop_reason` が `end_turn` になっているか。なっていれば Task 4 の「バッチ終端でセグメントを閉じてよいかの判定」に `stop_reason != "tool_use"` を使える。

- [ ] **Step 3: スラッシュコマンド起動が transcript にどう残るか実測する**

セッションで `/brainstorming` のようにスキルをスラッシュコマンドで起動し、直後にその transcript の user 行を見る。

```bash
python3 - <<'PY'
import json, glob, os
newest = max(glob.glob('/home/ubuntu/.claude/projects/*/*.jsonl'), key=os.path.getmtime)
for line in open(newest, encoding='utf-8', errors='replace'):
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get('type') != 'user':
        continue
    content = (record.get('message') or {}).get('content')
    text = content if isinstance(content, str) else ''
    if 'command-name' in text or text.lstrip().startswith('/'):
        print(repr(text[:300]))
PY
```

記録すること: `<command-name>` ブロックが現れるか、素の `/name` テキストか、あるいは痕跡が残らないか。

- [ ] **Step 4: コンパクション境界がどの行として残るか実測する**

```bash
python3 - <<'PY'
import json, glob, collections
marks = collections.Counter()
for path in glob.glob('/home/ubuntu/.claude/projects/*/*.jsonl'):
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get('isCompactSummary'):
            marks['isCompactSummary'] += 1
        if record.get('type') in ('summary', 'compact-boundary'):
            marks[record['type']] += 1
        attachment = record.get('attachment') or {}
        if attachment.get('hookEvent') == 'SessionStart':
            marks['SessionStart:' + str(attachment.get('hookName'))] += 1
print(dict(marks))
PY
```

記録すること: コンパクションを示す行が特定できたか。できなければ `compacted` は常に `false` を入れる(フィールドは残す)。

- [ ] **Step 5: `async: true` が `Stop` で尊重されるか確認する**

Claude Code のフック設定ドキュメントを確認し、`Stop` / `SubagentStop` が `async` を受け付けるか調べる。受け付けない場合は Task 7 で `async` を落とす。

```bash
ls ~/.claude/plugins/cache/*/*/*/hooks/hooks.json 2>/dev/null | head
grep -rn '"async"' ~/.claude/plugins/cache/ 2>/dev/null | head
```

記録すること: 他プラグインが `Stop` で `async` を使っている実例があるか。

- [ ] **Step 6: 実測結果を仕様書に追記する**

`docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md` の §15 の末尾に次の節を追加し、Step 1〜5 で得た**実際の値**を書く。「未確認」のまま残さない。確定できなかった項目は「確定できず。フォールバックは X」と書く。

```markdown
### 実測結果 (2026-08-21)

1. サブエージェントの transcript — <実測した内容>
2. `Stop` 発火時点の最終 assistant 行 — <実測した内容>
3. スラッシュコマンドの痕跡 — <実測した内容>
4. コンパクション境界 — <実測した内容>
5. `async` の扱い — <実測した内容>
```

- [ ] **Step 7: 時間定義の欠陥を仕様書で補正する**

§6 は「ターン境界だけで実行と待機を分ける」と書いているが、`AskUserQuestion` と `ExitPlanMode` はターンの内側で人間の回答を待つ。分離しないと、質問の多い skill が「重い skill」に誤判定される。

§6 を次の内容に置き換える。

```markdown
## 6. 時間の定義

セグメント内の連続する 2 レコードの時刻差(ギャップ)を、次の規則で実行と待機に振り分ける。

- 直前のレコードが assistant 行で、かつ **人間の応答を待つツール**
  (`AskUserQuestion`, `ExitPlanMode`)を呼んでいた場合 → そのギャップは `wait_ms`
- それ以外のギャップ → `exec_ms`

これに加えて、ターン先頭セグメント(`seq: 0`)には
「前ターンの最終 assistant 行から、このターンのユーザープロンプト行まで」の
経過を `wait_ms` に加算する。

この分離は必須である。試作では `brainstorming` の経過が 718.8 秒と出たが、
その大半は `AskUserQuestion` の回答を待っていた時間だった。ターン境界だけで
分けると、質問の多い skill を「重い skill」と誤判定する。

**限界**: 権限プロンプトの待ち時間は transcript に行として残らないため分離できず、
`exec_ms` に含まれる。
```

§7 のフィールド定義表の `wait_ms` の行を次に置き換える。

```markdown
| `wait_ms` | int | §6 の定義による待機時間。ターン境界の待ちに加え、`AskUserQuestion` / `ExitPlanMode` の回答待ちを含む |
```

- [ ] **Step 8: コミット**

```bash
git add docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md
git commit -m "docs(spec): record telemetry measurements and split in-turn human waits

Timing was defined at turn boundaries only, but AskUserQuestion and
ExitPlanMode block on a human inside a turn. A prototype measured
brainstorming at 718.8s, most of which was waiting for answers. Left
uncorrected, the skills that ask the most questions look like the
heaviest skills — the opposite of what this data is for.

Also records what the five unverified transcript behaviours actually do,
so the implementation stops guessing."
```

---

### Task 2: transcript モジュール

transcript 行の分類、増分読み、`usage` の正規化。**Claude Code の transcript 形式を知っている唯一の場所**にする。

**Files:**
- Create: `hooks/custom/telemetry_lib/__init__.py`
- Create: `hooks/custom/telemetry_lib/transcript.py`
- Create: `tests/hooks/telemetry/fixtures.py`
- Test: `tests/hooks/telemetry/test_transcript.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - 定数 `USER_PROMPT`, `TOOL_RESULT`, `META`, `ASSISTANT`, `MODE`, `PERMISSION_MODE`, `SESSION_START_HOOK`, `OTHER`(いずれも `str`)
  - `classify(record: dict) -> str`
  - `read_new_records(path: str, start_line: int) -> tuple[list[dict], int]`
  - `usage_of(record: dict) -> dict`(キー: `in`, `out`, `thinking`, `cache_read`, `cache_create_5m`, `cache_create_1h`、値は `int`)
  - `tool_uses(record: dict) -> list[tuple[str, dict]]`
  - `tool_error_count(record: dict) -> int`
  - `prompt_text(record: dict) -> str`
  - `ts_ms(value: str | None) -> int | None`

- [ ] **Step 1: fixture ビルダを書く**

`tests/hooks/telemetry/fixtures.py`:

```python
"""Builders for synthetic Claude Code transcript records.

Kept in one place so every test speaks the same dialect of the transcript
format. Field names mirror what real transcripts carry, verified against
live sessions on 2026-08-21.
"""

import json


def assistant(
    timestamp,
    uuid="u-assistant",
    output=100,
    thinking=0,
    cache_read=0,
    cache_create_1h=0,
    cache_create_5m=0,
    tools=(),
    stop_reason="tool_use",
    model="claude-opus-5",
    effort="high",
    branch="main",
    version="2.1.4",
    sidechain=False,
):
    """One assistant record. `tools` is a sequence of (name, input_dict)."""
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "gitBranch": branch,
        "version": version,
        "effort": effort,
        "message": {
            "model": model,
            "stop_reason": stop_reason,
            "content": [
                {"type": "tool_use", "name": name, "input": params, "id": "t-%d" % index}
                for index, (name, params) in enumerate(tools)
            ],
            "usage": {
                "input_tokens": 2,
                "output_tokens": output,
                "output_tokens_details": {"thinking_tokens": thinking},
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create_1h + cache_create_5m,
                "cache_creation": {
                    "ephemeral_1h_input_tokens": cache_create_1h,
                    "ephemeral_5m_input_tokens": cache_create_5m,
                },
            },
        },
    }


def prompt(timestamp, text="do the thing", sidechain=False):
    """A real human prompt: string content, no isMeta flag."""
    return {
        "type": "user",
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"content": text},
    }


def meta(timestamp, text="injected"):
    """A system-injected user record. Never a turn boundary."""
    return {"type": "user", "timestamp": timestamp, "isMeta": True, "message": {"content": text}}


def tool_result(timestamp, errors=0, ok=1, sidechain=False):
    """A tool_result carrier record. Never a turn boundary."""
    blocks = [{"type": "tool_result", "is_error": True} for _ in range(errors)]
    blocks += [{"type": "tool_result", "is_error": False} for _ in range(ok)]
    return {
        "type": "user",
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"content": blocks},
    }


def mode(value="normal"):
    return {"type": "mode", "mode": value}


def permission_mode(value="auto"):
    return {"type": "permission-mode", "permissionMode": value}


def write_jsonl(path, records, garbage_after=None):
    """Write records as JSONL. `garbage_after` inserts an unparseable line."""
    with open(path, "w", encoding="utf-8") as handle:
        for index, record in enumerate(records):
            handle.write(json.dumps(record) + "\n")
            if garbage_after is not None and index == garbage_after:
                handle.write("{not json at all\n")
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/hooks/telemetry/test_transcript.py`:

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

import fixtures
from telemetry_lib import transcript as tx


class TestClassify(unittest.TestCase):
    def test_assistant_record(self):
        self.assertEqual(tx.classify(fixtures.assistant("2026-08-21T04:00:00Z")), tx.ASSISTANT)

    def test_human_prompt_is_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.prompt("2026-08-21T04:00:00Z")), tx.USER_PROMPT)

    def test_injected_meta_is_not_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.meta("2026-08-21T04:00:00Z")), tx.META)

    def test_tool_result_is_not_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.tool_result("2026-08-21T04:00:00Z")), tx.TOOL_RESULT)

    def test_mode_records(self):
        self.assertEqual(tx.classify(fixtures.mode()), tx.MODE)
        self.assertEqual(tx.classify(fixtures.permission_mode()), tx.PERMISSION_MODE)

    def test_session_start_attachment(self):
        record = {"type": "attachment", "attachment": {"hookEvent": "SessionStart", "stdout": "x"}}
        self.assertEqual(tx.classify(record), tx.SESSION_START_HOOK)

    def test_unknown_type(self):
        self.assertEqual(tx.classify({"type": "ai-title"}), tx.OTHER)


class TestUsage(unittest.TestCase):
    def test_splits_cache_creation_by_ttl(self):
        record = fixtures.assistant(
            "2026-08-21T04:00:00Z", output=555, thinking=221,
            cache_read=22625, cache_create_1h=10860, cache_create_5m=40,
        )
        self.assertEqual(
            tx.usage_of(record),
            {"in": 2, "out": 555, "thinking": 221, "cache_read": 22625,
             "cache_create_5m": 40, "cache_create_1h": 10860},
        )

    def test_missing_usage_is_all_zero(self):
        self.assertEqual(
            tx.usage_of({"type": "assistant", "message": {}}),
            {"in": 0, "out": 0, "thinking": 0, "cache_read": 0,
             "cache_create_5m": 0, "cache_create_1h": 0},
        )


class TestExtraction(unittest.TestCase):
    def test_tool_uses_returns_name_and_input(self):
        record = fixtures.assistant(
            "2026-08-21T04:00:00Z",
            tools=[("Skill", {"skill": "superpowers:brainstorming"}), ("Bash", {"command": "ls"})],
        )
        self.assertEqual(
            tx.tool_uses(record),
            [("Skill", {"skill": "superpowers:brainstorming"}), ("Bash", {"command": "ls"})],
        )

    def test_tool_error_count(self):
        self.assertEqual(tx.tool_error_count(fixtures.tool_result("t", errors=2, ok=3)), 2)

    def test_prompt_text_from_string_content(self):
        self.assertEqual(tx.prompt_text(fixtures.prompt("t", text="hello")), "hello")

    def test_prompt_text_from_text_blocks(self):
        record = {"message": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}}
        self.assertEqual(tx.prompt_text(record), "ab")


class TestIncrementalRead(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "t.jsonl")

    def test_reads_everything_from_zero(self):
        fixtures.write_jsonl(self.path, [fixtures.mode(), fixtures.prompt("t1")])
        records, total = tx.read_new_records(self.path, 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(total, 2)

    def test_resumes_from_offset(self):
        fixtures.write_jsonl(self.path, [fixtures.mode(), fixtures.prompt("t1"), fixtures.prompt("t2")])
        records, total = tx.read_new_records(self.path, 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(total, 3)

    def test_garbage_line_is_skipped_but_counted(self):
        fixtures.write_jsonl(self.path, [fixtures.prompt("t1"), fixtures.prompt("t2")], garbage_after=0)
        records, total = tx.read_new_records(self.path, 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(total, 3)

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            tx.read_new_records(os.path.join(self.dir.name, "nope.jsonl"), 0)


class TestTimestamps(unittest.TestCase):
    def test_parses_zulu(self):
        self.assertEqual(tx.ts_ms("2026-08-21T04:00:00.500Z") - tx.ts_ms("2026-08-21T04:00:00Z"), 500)

    def test_none_and_garbage(self):
        self.assertIsNone(tx.ts_ms(None))
        self.assertIsNone(tx.ts_ms("not a time"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: テストが失敗することを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_transcript.py' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telemetry_lib'`

- [ ] **Step 4: 実装する**

`hooks/custom/telemetry_lib/__init__.py`:

```python
"""Session telemetry hook internals. Standard library only."""
```

`hooks/custom/telemetry_lib/transcript.py`:

```python
"""Classify and read Claude Code transcript records.

This is the only module that knows the transcript's field names. Everything
here is a pure function over an already-parsed record, except the one
incremental reader.
"""

import json
from datetime import datetime

USER_PROMPT = "user_prompt"
TOOL_RESULT = "tool_result"
META = "meta"
ASSISTANT = "assistant"
MODE = "mode"
PERMISSION_MODE = "permission_mode"
SESSION_START_HOOK = "session_start_hook"
OTHER = "other"


def classify(record):
    """Which kind of transcript line this is.

    A `type: "user"` record is three different things depending on its
    content: a real human prompt (a turn boundary), a system-injected note,
    or a carrier for tool results. Only the first starts a turn.
    """
    kind = record.get("type")

    if kind == "assistant":
        return ASSISTANT

    if kind == "user":
        if record.get("isMeta"):
            return META
        content = (record.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return TOOL_RESULT
        return USER_PROMPT

    if kind == "mode":
        return MODE

    if kind == "permission-mode":
        return PERMISSION_MODE

    if kind == "attachment":
        if (record.get("attachment") or {}).get("hookEvent") == "SessionStart":
            return SESSION_START_HOOK

    return OTHER


def read_new_records(path, start_line):
    """Parse lines after `start_line`.

    Returns (records, total_lines). Unparseable lines are skipped but still
    counted, so the offset stays aligned with the file even when a line is
    truncated mid-write.
    """
    records = []
    total = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            total = index + 1
            if index < start_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records, total


def usage_of(record):
    """Token counts from an assistant record, normalised and zero-filled.

    The 5-minute and 1-hour cache writes are kept apart because they are
    priced differently; a single combined number cannot be un-mixed later.
    """
    usage = (record.get("message") or {}).get("usage") or {}
    created = usage.get("cache_creation") or {}
    details = usage.get("output_tokens_details") or {}
    return {
        "in": usage.get("input_tokens") or 0,
        "out": usage.get("output_tokens") or 0,
        "thinking": details.get("thinking_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "cache_create_5m": created.get("ephemeral_5m_input_tokens") or 0,
        "cache_create_1h": created.get("ephemeral_1h_input_tokens") or 0,
    }


def tool_uses(record):
    """[(tool_name, tool_input)] for every tool_use block, in order."""
    found = []
    for block in (record.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            found.append((block.get("name"), block.get("input") or {}))
    return found


def tool_error_count(record):
    """How many tool_result blocks in this record are flagged is_error."""
    count = 0
    for block in (record.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
            count += 1
    return count


def prompt_text(record):
    """The plain text of a user record. Empty string when there is none.

    Only used to decide whether a slash command invoked a skill. The text is
    never written to the telemetry output.
    """
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def ts_ms(value):
    """ISO-8601 timestamp to epoch milliseconds. None when unparseable."""
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, AttributeError):
        return None
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_transcript.py' -v`
Expected: PASS(19 tests)

- [ ] **Step 6: コミット**

```bash
git add hooks/custom/telemetry_lib/__init__.py hooks/custom/telemetry_lib/transcript.py \
        tests/hooks/telemetry/fixtures.py tests/hooks/telemetry/test_transcript.py
git commit -m "feat(telemetry): read and classify transcript records

Isolates every piece of knowledge about the transcript format in one
module, so the segmentation logic can be tested without touching a file.

The subtle part is that a type:\"user\" record is three different things:
a human prompt, a system-injected note, and a carrier for tool results.
Only the first starts a turn, and conflating them would put every tool
call in its own turn."
```

---

### Task 3: skills モジュール

skill 名から phase・リビジョンハッシュ・起動主体を求める。

**Files:**
- Create: `hooks/custom/telemetry_lib/skills.py`
- Test: `tests/hooks/telemetry/test_skills.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `PHASE_BY_SKILL: dict[str, str]`
  - `HUMAN_BLOCKING_TOOLS: frozenset[str]`
  - `short_name(skill: str | None) -> str | None`
  - `phase_for(skill: str | None) -> str`
  - `skill_rev(skill: str | None, plugin_root: str | None) -> str | None`
  - `plugin_version(plugin_root: str | None) -> str | None`
  - `invoked_by(skill: str | None, prompt: str) -> str`(`"user"` / `"model"`)

- [ ] **Step 1: 失敗するテストを書く**

`tests/hooks/telemetry/test_skills.py`:

```python
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

from telemetry_lib import skills as sk


class TestPhaseMapping(unittest.TestCase):
    def test_known_skills(self):
        cases = {
            "superpowers:brainstorming": "brainstorming",
            "superpowers:writing-plans": "planning",
            "superpowers:test-driven-development": "implementing",
            "superpowers:executing-plans": "implementing",
            "superpowers:subagent-driven-development": "implementing",
            "superpowers:systematic-debugging": "debugging",
            "superpowers:requesting-code-review": "reviewing",
            "superpowers:receiving-code-review": "reviewing",
            "superpowers:verification-before-completion": "reviewing",
            "superpowers:finishing-a-development-branch": "finishing",
        }
        for skill, expected in cases.items():
            self.assertEqual(sk.phase_for(skill), expected, skill)

    def test_unknown_skill_and_none(self):
        self.assertEqual(sk.phase_for("superpowers:writing-skills"), "unknown")
        self.assertEqual(sk.phase_for("other-plugin:whatever"), "unknown")
        self.assertEqual(sk.phase_for(None), "unknown")

    def test_bare_name_without_plugin_prefix(self):
        self.assertEqual(sk.phase_for("brainstorming"), "brainstorming")


class TestSkillRev(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name
        skill_dir = os.path.join(self.root, "skills", "brainstorming")
        os.makedirs(skill_dir)
        self.body = b"---\nname: brainstorming\n---\nbody\n"
        with open(os.path.join(skill_dir, "SKILL.md"), "wb") as handle:
            handle.write(self.body)

    def test_hashes_skill_md(self):
        self.assertEqual(
            sk.skill_rev("superpowers:brainstorming", self.root),
            hashlib.sha256(self.body).hexdigest()[:8],
        )

    def test_changes_when_the_skill_changes(self):
        before = sk.skill_rev("superpowers:brainstorming", self.root)
        with open(os.path.join(self.root, "skills", "brainstorming", "SKILL.md"), "ab") as handle:
            handle.write(b"more\n")
        self.assertNotEqual(before, sk.skill_rev("superpowers:brainstorming", self.root))

    def test_unresolvable_returns_none(self):
        self.assertIsNone(sk.skill_rev("superpowers:nonexistent", self.root))
        self.assertIsNone(sk.skill_rev("other-plugin:thing", self.root))
        self.assertIsNone(sk.skill_rev(None, self.root))
        self.assertIsNone(sk.skill_rev("superpowers:brainstorming", None))


class TestPluginVersion(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        os.makedirs(os.path.join(self.dir.name, ".claude-plugin"))

    def test_reads_version(self):
        path = os.path.join(self.dir.name, ".claude-plugin", "plugin.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"name": "superpowers", "version": "1.0.0"}, handle)
        self.assertEqual(sk.plugin_version(self.dir.name), "1.0.0")

    def test_missing_file_returns_none(self):
        self.assertIsNone(sk.plugin_version(self.dir.name))
        self.assertIsNone(sk.plugin_version(None))


class TestInvokedBy(unittest.TestCase):
    def test_slash_command_is_user(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "/brainstorming let's go"), "user")

    def test_command_name_block_is_user(self):
        text = "<command-name>/brainstorming</command-name>\n<command-args>x</command-args>"
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", text), "user")

    def test_plain_prompt_is_model(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "help me design a hook"), "model")

    def test_different_skill_named_in_prompt_is_model(self):
        self.assertEqual(sk.invoked_by("superpowers:writing-plans", "/brainstorming go"), "model")

    def test_no_prompt_or_no_skill(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", ""), "model")
        self.assertEqual(sk.invoked_by(None, "/brainstorming"), "model")


class TestBlockingTools(unittest.TestCase):
    def test_human_blocking_tools(self):
        self.assertIn("AskUserQuestion", sk.HUMAN_BLOCKING_TOOLS)
        self.assertIn("ExitPlanMode", sk.HUMAN_BLOCKING_TOOLS)
        self.assertNotIn("Bash", sk.HUMAN_BLOCKING_TOOLS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_skills.py' -v`
Expected: FAIL — `ImportError: cannot import name 'skills'`

- [ ] **Step 3: 実装する**

`hooks/custom/telemetry_lib/skills.py`:

```python
"""Map a skill name to its phase, its revision, and how it was invoked."""

import hashlib
import json
import os

# The work phase each skill represents. Adding a skill means adding one line.
# Anything absent falls through to "unknown" rather than guessing.
PHASE_BY_SKILL = {
    "brainstorming": "brainstorming",
    "writing-plans": "planning",
    "test-driven-development": "implementing",
    "executing-plans": "implementing",
    "subagent-driven-development": "implementing",
    "systematic-debugging": "debugging",
    "requesting-code-review": "reviewing",
    "receiving-code-review": "reviewing",
    "verification-before-completion": "reviewing",
    "finishing-a-development-branch": "finishing",
}

# Tools that stop and wait for a person. Time spent after one of these is
# the human's, not the skill's — see the timing rules in the design doc.
HUMAN_BLOCKING_TOOLS = frozenset({"AskUserQuestion", "ExitPlanMode"})


def short_name(skill):
    """"superpowers:brainstorming" -> "brainstorming"."""
    if not skill:
        return None
    return skill.split(":", 1)[1] if ":" in skill else skill


def phase_for(skill):
    return PHASE_BY_SKILL.get(short_name(skill) or "", "unknown")


def skill_rev(skill, plugin_root):
    """First 8 hex chars of sha256(SKILL.md). None when unresolvable.

    This is the skill's version. Skills carry no version number of their
    own, and the plugin version does not move when a SKILL.md is edited —
    so without this hash, before-and-after comparisons are impossible.
    """
    if not skill or not plugin_root or not skill.startswith("superpowers:"):
        return None
    path = os.path.join(plugin_root, "skills", short_name(skill), "SKILL.md")
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()[:8]
    except OSError:
        return None


def plugin_version(plugin_root):
    if not plugin_root:
        return None
    path = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return (json.load(handle) or {}).get("version")
    except (OSError, ValueError):
        return None


def invoked_by(skill, prompt):
    """"user" when the turn's prompt invoked this exact skill by slash command.

    A skill that only ever runs because a human typed its name is a skill
    that is failing to trigger on its own — which is the whole point of
    recording this.
    """
    name = short_name(skill)
    if not name or not prompt:
        return "model"
    if "<command-name>/%s</command-name>" % name in prompt:
        return "user"
    if prompt.lstrip().startswith("/" + name):
        return "user"
    return "model"
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_skills.py' -v`
Expected: PASS(14 tests)

- [ ] **Step 5: 実在の skill 名と写像表が一致することを確認する**

写像表のキーが実際のディレクトリ名と一致していなければ、全レコードが `unknown` になる。

```bash
cd /home/ubuntu/projects/superpowers
python3 - <<'PY'
import os, sys
sys.path.insert(0, "hooks/custom")
from telemetry_lib import skills as sk
actual = set(os.listdir("skills"))
mapped = set(sk.PHASE_BY_SKILL)
missing = sorted(mapped - actual)
print("写像表にあるが skills/ に無い:", missing or "なし")
print("skills/ にあって未分類:", sorted(actual - mapped))
PY
```

Expected: 「写像表にあるが skills/ に無い: なし」。1 つでも出たら綴りを直す。

- [ ] **Step 6: コミット**

```bash
git add hooks/custom/telemetry_lib/skills.py tests/hooks/telemetry/test_skills.py
git commit -m "feat(telemetry): resolve skill phase, revision, and invoker

Skills carry no version number, and the plugin version does not move when
a SKILL.md is edited — so comparing a skill before and after a change
needs a hash of the file itself.

invoked_by separates a skill the model reached for from one a human had to
ask for by name. A skill that only ever runs on request is failing to
trigger, and that failure leaves no other trace."
```

---

### Task 4: segments モジュール（中核）

transcript のレコード列を `(ターン × skill)` セグメントに分割し、時間とトークンを帰属させる。**このプロジェクトの中核要件はここで満たされる。**

**Files:**
- Create: `hooks/custom/telemetry_lib/segments.py`
- Test: `tests/hooks/telemetry/test_segments.py`

**Interfaces:**
- Consumes: `telemetry_lib.transcript`, `telemetry_lib.skills`
- Produces:
  - `new_state() -> dict`
  - `build_segments(records: list[dict], state: dict, ctx: dict) -> tuple[list[dict], dict]`
    - `ctx` のキー: `session`(str), `default_agent`(`"main"` / `"subagent"`。sidechain 行は常に `"subagent"` になる), `project`(str), `plugin_root`(str | None), `plugin_version`(str | None), `subagent_type`(str | None), `parent_turn`(int | None)
    - 戻り値の各セグメントは仕様 §7 の全フィールドを持つ完成レコード

- [ ] **Step 1: 失敗するテストを書く**

`tests/hooks/telemetry/test_segments.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

import fixtures
from telemetry_lib import segments as sg

CTX = {
    "session": "s-1",
    "default_agent": "main",
    "project": "superpowers",
    "plugin_root": None,
    "plugin_version": "1.0.0",
    "subagent_type": None,
    "parent_turn": None,
}


def run(records, state=None, ctx=None):
    return sg.build_segments(records, state or sg.new_state(), dict(ctx or CTX))


class TestSingleSkillTurn(unittest.TestCase):
    def test_one_turn_one_skill_makes_one_row(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:02Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:10Z", output=500, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        skills = [(s["skill"], s["seq"]) for s in segments]
        self.assertEqual(skills, [(None, 0), ("superpowers:brainstorming", 1)])
        self.assertEqual(segments[1]["turn"], 1)
        self.assertEqual(segments[1]["tokens"]["out"], 500)

    def test_record_carrying_the_skill_call_bills_the_previous_skill(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:02Z", output=77,
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:10Z", output=500, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["tokens"]["out"], 77)
        self.assertEqual(segments[1]["tokens"]["out"], 500)


class TestSkillSwitchWithinOneTurn(unittest.TestCase):
    """The core requirement: coding and review must not blend together."""

    def setUp(self):
        self.records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=10,
                               tools=[("Skill", {"skill": "superpowers:test-driven-development"})]),
            fixtures.assistant("2026-08-21T04:00:31Z", output=8100,
                               cache_create_1h=10860, tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:33Z"),
            fixtures.assistant("2026-08-21T04:00:41Z", output=100,
                               tools=[("Skill", {"skill": "superpowers:requesting-code-review"})]),
            fixtures.assistant("2026-08-21T04:01:11Z", output=2400,
                               stop_reason="end_turn"),
        ]

    def test_produces_one_row_per_skill(self):
        segments, _ = run(self.records)
        self.assertEqual(
            [s["skill"] for s in segments],
            [None, "superpowers:test-driven-development", "superpowers:requesting-code-review"],
        )

    def test_all_rows_share_the_turn(self):
        segments, _ = run(self.records)
        self.assertEqual([s["turn"] for s in segments], [1, 1, 1])
        self.assertEqual([s["seq"] for s in segments], [0, 1, 2])

    def test_tokens_are_separated(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        self.assertEqual(by_skill["superpowers:test-driven-development"]["tokens"]["out"], 8200)
        self.assertEqual(by_skill["superpowers:requesting-code-review"]["tokens"]["out"], 2400)

    def test_time_is_separated(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        # TDD: 04:00:01 -> 04:00:41 = 40s
        self.assertEqual(by_skill["superpowers:test-driven-development"]["exec_ms"], 40000)
        # review: 04:00:41 -> 04:01:11 = 30s
        self.assertEqual(by_skill["superpowers:requesting-code-review"]["exec_ms"], 30000)

    def test_cache_creation_ttl_split_survives(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        self.assertEqual(
            by_skill["superpowers:test-driven-development"]["tokens"]["cache_create_1h"], 10860)
        self.assertEqual(
            by_skill["superpowers:test-driven-development"]["tokens"]["cache_create_5m"], 0)


class TestWaitTime(unittest.TestCase):
    def test_between_turns_lands_on_seq_zero(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:10Z", stop_reason="end_turn"),
            fixtures.prompt("2026-08-21T04:02:10Z"),
            fixtures.assistant("2026-08-21T04:02:15Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["wait_ms"], 0)
        self.assertEqual(segments[1]["turn"], 2)
        self.assertEqual(segments[1]["seq"], 0)
        self.assertEqual(segments[1]["wait_ms"], 120000)

    def test_ask_user_question_inside_a_turn_counts_as_wait(self):
        """The 718.8s problem: a question's answer time is not the skill's cost."""
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:05Z", tools=[("AskUserQuestion", {})]),
            fixtures.tool_result("2026-08-21T04:05:05Z"),
            fixtures.assistant("2026-08-21T04:05:10Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        brainstorm = [s for s in segments if s["skill"] == "superpowers:brainstorming"][0]
        self.assertEqual(brainstorm["wait_ms"], 300000)
        self.assertEqual(brainstorm["exec_ms"], 9000)

    def test_ordinary_tool_gap_counts_as_exec(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:31Z"),
            fixtures.assistant("2026-08-21T04:00:32Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["wait_ms"], 0)
        self.assertEqual(segments[0]["exec_ms"], 32000)


class TestBoundaryHandling(unittest.TestCase):
    def test_meta_records_do_not_start_a_turn(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.meta("2026-08-21T04:00:01Z"),
            fixtures.assistant("2026-08-21T04:00:02Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["turn"], 1)

    def test_tool_results_do_not_start_a_turn(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:02Z"),
            fixtures.assistant("2026-08-21T04:00:03Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(len(segments), 1)

    def test_empty_segment_is_not_emitted(self):
        """A skill called as the turn's last act carries over instead."""
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:05Z", output=50, stop_reason="end_turn",
                               tools=[("Skill", {"skill": "superpowers:writing-plans"})]),
        ]
        segments, state = run(records)
        self.assertEqual([s["skill"] for s in segments], [None])
        self.assertEqual(state["main"]["active_skill"], "superpowers:writing-plans")

    def test_open_segment_is_held_when_the_model_has_not_stopped(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=40, tools=[("Bash", {})]),
        ]
        segments, state = run(records)
        self.assertEqual(segments, [])
        self.assertIsNotNone(state["main"]["open"])

    def test_held_segment_completes_on_the_next_batch(self):
        first = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=40, tools=[("Bash", {})]),
        ]
        _, state = run(first)
        second = [
            fixtures.tool_result("2026-08-21T04:00:02Z"),
            fixtures.assistant("2026-08-21T04:00:03Z", output=60, stop_reason="end_turn"),
        ]
        segments, _ = run(second, state=state)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["tokens"]["out"], 100)
        self.assertEqual(segments[0]["turn"], 1)


class TestSkillCarryOver(unittest.TestCase):
    def test_active_skill_survives_into_the_next_turn(self):
        first = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:05Z", output=10, stop_reason="end_turn"),
        ]
        _, state = run(first)
        second = [
            fixtures.prompt("2026-08-21T04:01:00Z"),
            fixtures.assistant("2026-08-21T04:01:05Z", output=20, stop_reason="end_turn"),
        ]
        segments, _ = run(second, state=state)
        self.assertEqual(segments[0]["skill"], "superpowers:brainstorming")
        self.assertEqual(segments[0]["turn"], 2)
        self.assertEqual(segments[0]["seq"], 0)


class TestSidechainIsolation(unittest.TestCase):
    def test_subagent_records_do_not_pollute_the_main_stream(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=10, tools=[("Bash", {})]),
            fixtures.prompt("2026-08-21T04:00:02Z", sidechain=True),
            fixtures.assistant("2026-08-21T04:00:03Z", output=999, stop_reason="end_turn",
                               sidechain=True),
            fixtures.tool_result("2026-08-21T04:00:04Z"),
            fixtures.assistant("2026-08-21T04:00:05Z", output=20, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        main = [s for s in segments if s["agent"] == "main"]
        sub = [s for s in segments if s["agent"] == "subagent"]
        self.assertEqual(len(main), 1)
        self.assertEqual(main[0]["tokens"]["out"], 30)
        self.assertEqual(len(sub), 1)
        self.assertEqual(sub[0]["tokens"]["out"], 999)


class TestRecordShape(unittest.TestCase):
    def test_every_spec_field_is_present(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.mode("normal"),
            fixtures.permission_mode("auto"),
            fixtures.assistant("2026-08-21T04:00:05Z", uuid="u-9", output=50,
                               tools=[("Bash", {})], stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        expected = {
            "schema_version", "kind", "ts", "ts_end", "session", "turn", "seq", "agent",
            "subagent_type", "parent_turn", "first_uuid", "skill", "skill_rev", "invoked_by",
            "phase", "project", "branch", "cc_version", "plugin_version", "model", "effort",
            "mode", "permission_mode", "exec_ms", "wait_ms", "api_calls", "tokens", "tools",
            "tool_errors", "stop_reason", "compacted",
        }
        self.assertEqual(set(segments[0]), expected)
        self.assertEqual(segments[0]["schema_version"], 1)
        self.assertEqual(segments[0]["kind"], "seg")
        self.assertEqual(segments[0]["first_uuid"], "u-9")
        self.assertEqual(segments[0]["branch"], "main")
        self.assertEqual(segments[0]["cc_version"], "2.1.4")
        self.assertEqual(segments[0]["model"], "claude-opus-5")
        self.assertEqual(segments[0]["mode"], "normal")
        self.assertEqual(segments[0]["permission_mode"], "auto")
        self.assertEqual(segments[0]["tools"], {"Bash": 1})
        self.assertEqual(segments[0]["api_calls"], 1)

    def test_tool_errors_are_counted(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:02Z", errors=2, ok=1),
            fixtures.assistant("2026-08-21T04:00:03Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["tool_errors"], 2)

    def test_no_prompt_text_leaks_into_the_record(self):
        secret = "my password is hunter2"
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z", text=secret),
            fixtures.assistant("2026-08-21T04:00:01Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        import json as _json
        self.assertNotIn("hunter2", _json.dumps(segments))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_segments.py' -v`
Expected: FAIL — `ImportError: cannot import name 'segments'`

- [ ] **Step 3: 実装する**

`hooks/custom/telemetry_lib/segments.py`:

```python
"""Split a transcript into (turn x skill) segments.

A turn is one human prompt and everything the agent does before it stops.
Within a turn the agent switches skills on its own, so a per-turn total
blends those skills together — which is exactly the comparison this data
exists to support. The unit of record is therefore the segment.

Main-agent and subagent records are accumulated separately, so interleaved
sidechain lines can never pollute the main stream.
"""

from . import skills as sk
from . import transcript as tx

SCHEMA_VERSION = 1

_ZERO_TOKENS = ("in", "out", "thinking", "cache_read", "cache_create_5m", "cache_create_1h")


def _new_stream():
    return {
        "turn": 0,
        "seq": 0,
        "active_skill": None,
        "active_skill_rev": None,
        "invoked_by": "model",
        "prompt": "",
        "prev_turn_end_ms": None,
        "last_ms": None,
        "last_blocking": False,
        "mode": None,
        "permission_mode": None,
        "open": None,
    }


def new_state():
    """State carried between hook invocations, stored per session."""
    return {"line": 0, "main": _new_stream(), "sub": _new_stream()}


def _open_segment(stream, ts, wait_ms):
    stream["open"] = {
        "ts": ts,
        "ts_end": ts,
        "turn": stream["turn"],
        "seq": stream["seq"],
        "skill": stream["active_skill"],
        "skill_rev": stream["active_skill_rev"],
        "invoked_by": stream["invoked_by"],
        "first_uuid": None,
        "exec_ms": 0,
        "wait_ms": wait_ms,
        "api_calls": 0,
        "tokens": dict.fromkeys(_ZERO_TOKENS, 0),
        "tools": {},
        "tool_errors": 0,
        "stop_reason": None,
        "compacted": False,
        "model": None,
        "effort": None,
        "branch": None,
        "cc_version": None,
    }


def _advance(stream, ts):
    """Move the clock to `ts`, billing the gap to exec or wait."""
    now = tx.ts_ms(ts)
    if now is None:
        return
    segment = stream["open"]
    previous = stream["last_ms"]
    if segment is not None and previous is not None and now > previous:
        gap = now - previous
        if stream["last_blocking"]:
            segment["wait_ms"] += gap
        else:
            segment["exec_ms"] += gap
        segment["ts_end"] = ts
    stream["last_ms"] = now


def _close(stream, out, ctx):
    """Emit the open segment unless it is empty, then clear it."""
    segment = stream["open"]
    stream["open"] = None
    if segment is None:
        return
    if segment["api_calls"] == 0 and segment["exec_ms"] == 0 and segment["wait_ms"] == 0:
        return
    out.append(_finish(segment, ctx))


def _finish(segment, ctx):
    """Turn an accumulator into a complete telemetry record."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "seg",
        "ts": segment["ts"],
        "ts_end": segment["ts_end"],
        "session": ctx.get("session"),
        "turn": segment["turn"],
        "seq": segment["seq"],
        "agent": ctx.get("agent"),
        "subagent_type": ctx.get("subagent_type"),
        "parent_turn": ctx.get("parent_turn"),
        "first_uuid": segment["first_uuid"],
        "skill": segment["skill"],
        "skill_rev": segment["skill_rev"],
        "invoked_by": segment["invoked_by"],
        "phase": sk.phase_for(segment["skill"]),
        "project": ctx.get("project"),
        "branch": segment["branch"],
        "cc_version": segment["cc_version"],
        "plugin_version": ctx.get("plugin_version"),
        "model": segment["model"],
        "effort": segment["effort"],
        "mode": segment["mode"],
        "permission_mode": segment["permission_mode"],
        "exec_ms": segment["exec_ms"],
        "wait_ms": segment["wait_ms"],
        "api_calls": segment["api_calls"],
        "tokens": segment["tokens"],
        "tools": segment["tools"],
        "tool_errors": segment["tool_errors"],
        "stop_reason": segment["stop_reason"],
        "compacted": segment["compacted"],
    }


def _feed(stream, records, out, ctx):
    for record in records:
        kind = tx.classify(record)
        ts = record.get("timestamp")

        if kind == tx.MODE:
            stream["mode"] = record.get("mode")
            continue

        if kind == tx.PERMISSION_MODE:
            stream["permission_mode"] = record.get("permissionMode")
            continue

        if kind == tx.USER_PROMPT:
            _close(stream, out, ctx)
            now = tx.ts_ms(ts)
            wait = 0
            if now is not None and stream["prev_turn_end_ms"] is not None:
                wait = max(0, now - stream["prev_turn_end_ms"])
            stream["turn"] += 1
            stream["seq"] = 0
            stream["prompt"] = tx.prompt_text(record)
            stream["invoked_by"] = sk.invoked_by(stream["active_skill"], stream["prompt"])
            stream["last_ms"] = now
            stream["last_blocking"] = False
            _open_segment(stream, ts, wait)
            continue

        if kind == tx.META or kind == tx.OTHER or kind == tx.SESSION_START_HOOK:
            continue

        if kind == tx.TOOL_RESULT:
            _advance(stream, ts)
            if stream["open"] is not None:
                stream["open"]["tool_errors"] += tx.tool_error_count(record)
            stream["last_blocking"] = False
            continue

        # kind == tx.ASSISTANT
        if stream["open"] is None:
            stream["last_ms"] = tx.ts_ms(ts)
            _open_segment(stream, ts, 0)
        _advance(stream, ts)

        segment = stream["open"]
        segment["api_calls"] += 1
        segment["ts_end"] = ts
        if segment["first_uuid"] is None:
            segment["first_uuid"] = record.get("uuid")
        segment["branch"] = record.get("gitBranch") or segment["branch"]
        segment["cc_version"] = record.get("version") or segment["cc_version"]
        segment["effort"] = record.get("effort") or segment["effort"]
        segment["mode"] = stream["mode"]
        segment["permission_mode"] = stream["permission_mode"]
        message = record.get("message") or {}
        segment["model"] = message.get("model") or segment["model"]
        segment["stop_reason"] = message.get("stop_reason")

        usage = tx.usage_of(record)
        for key in _ZERO_TOKENS:
            segment["tokens"][key] += usage[key]

        uses = tx.tool_uses(record)
        for name, _params in uses:
            segment["tools"][name] = segment["tools"].get(name, 0) + 1

        for name, params in uses:
            if name != "Skill":
                continue
            _close(stream, out, ctx)
            stream["active_skill"] = params.get("skill")
            stream["active_skill_rev"] = sk.skill_rev(
                stream["active_skill"], ctx.get("plugin_root"))
            stream["invoked_by"] = sk.invoked_by(stream["active_skill"], stream["prompt"])
            stream["seq"] += 1
            _open_segment(stream, ts, 0)
            stream["open"]["mode"] = stream["mode"]
            stream["open"]["permission_mode"] = stream["permission_mode"]

        stream["last_blocking"] = any(
            name in sk.HUMAN_BLOCKING_TOOLS for name, _params in uses)

        if message.get("stop_reason") not in (None, "tool_use"):
            stream["prev_turn_end_ms"] = tx.ts_ms(ts)


def _flush_if_stopped(stream, records, out, ctx):
    """Close the open segment only when the model actually stopped.

    The Stop hook may fire before the last assistant line reaches the file.
    Holding the segment open until a non-tool_use stop_reason appears means
    the tail arrives in the next batch instead of being lost or double-counted.
    """
    last_assistant = None
    for record in records:
        if tx.classify(record) == tx.ASSISTANT:
            last_assistant = record
    if last_assistant is None:
        return
    stop_reason = (last_assistant.get("message") or {}).get("stop_reason")
    if stop_reason not in (None, "tool_use"):
        _close(stream, out, ctx)


def build_segments(records, state, ctx):
    """Fold a batch of transcript records into finished segment records."""
    main_records = [r for r in records if not r.get("isSidechain")]
    sub_records = [r for r in records if r.get("isSidechain")]

    out = []

    main_ctx = dict(ctx)
    main_ctx["agent"] = ctx.get("default_agent") or "main"
    _feed(state["main"], main_records, out, main_ctx)
    _flush_if_stopped(state["main"], main_records, out, main_ctx)

    if sub_records:
        sub_ctx = dict(ctx)
        sub_ctx["agent"] = "subagent"
        _feed(state["sub"], sub_records, out, sub_ctx)
        _flush_if_stopped(state["sub"], sub_records, out, sub_ctx)

    out.sort(key=lambda record: (record["ts"] or "", record["turn"], record["seq"]))
    return out, state
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_segments.py' -v`
Expected: PASS(20 tests)

- [ ] **Step 5: 実際のトランスクリプトで健全性を確認する**

合成データだけでなく、本物の transcript でクラッシュしないことと、値が妥当であることを見る。

```bash
cd /home/ubuntu/projects/superpowers
python3 - <<'PY'
import glob, os, sys
sys.path.insert(0, "hooks/custom")
from telemetry_lib import segments as sg, transcript as tx

newest = max(glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl')), key=os.path.getmtime)
records, total = tx.read_new_records(newest, 0)
ctx = {"session": "probe", "agent": "main", "project": "superpowers",
       "plugin_root": ".", "plugin_version": "1.0.0",
       "subagent_type": None, "parent_turn": None}
rows, _ = sg.build_segments(records, sg.new_state(), ctx)
print("file:", os.path.basename(newest), "lines:", total, "segments:", len(rows))
for row in rows[:12]:
    print("  turn=%-3s seq=%-2s skill=%-42s exec=%-8s wait=%-8s out=%s" % (
        row["turn"], row["seq"], row["skill"], row["exec_ms"], row["wait_ms"],
        row["tokens"]["out"]))
PY
```

Expected: 例外なく完走し、`exec_ms` と `wait_ms` がいずれも非負で、`AskUserQuestion` を含むターンで `wait_ms` が立つ。

- [ ] **Step 6: コミット**

```bash
git add hooks/custom/telemetry_lib/segments.py tests/hooks/telemetry/test_segments.py
git commit -m "feat(telemetry): split turns into per-skill segments

This is the requirement the whole feature exists for. Within one turn the
agent moves from test-driven-development to requesting-code-review on its
own; a per-turn row blends their time and tokens, and the blended number
cannot answer which skill is expensive.

Two things the naive version gets wrong. The assistant record that carries
the Skill call is billed to the outgoing skill, because that decision was
made under the old context. And a gap after AskUserQuestion is the human's
time, not the skill's — a prototype measured brainstorming at 718.8s, of
which almost all was waiting for answers.

Sidechain records accumulate in their own stream, so subagent lines
interleaved into the parent transcript cannot corrupt the main totals."
```

---

### Task 5: store モジュール

JSONL 追記、状態ファイル、エラーログ、古い状態の掃除。**ファイルシステムに触る唯一の場所**にする。

**Files:**
- Create: `hooks/custom/telemetry_lib/store.py`
- Test: `tests/hooks/telemetry/test_store.py`

**Interfaces:**
- Consumes: なし(`segments` のデータ形状を知らない。状態の既定値は呼び出し側が渡す)
- Produces:
  - `base_dir() -> str`
  - `append_records(records: list[dict], base: str) -> None`
  - `load_state(session: str, base: str, default: dict) -> dict`
  - `save_state(session: str, state: dict, base: str) -> None`
  - `prune_states(base: str, max_age_days: int = 30) -> int`
  - `log_error(base: str, session: str, message: str) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/hooks/telemetry/test_store.py`:

```python
import fcntl
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

from telemetry_lib import store


def row(ts="2026-08-21T04:00:00Z", **extra):
    record = {"schema_version": 1, "kind": "seg", "ts": ts, "skill": None}
    record.update(extra)
    return record


class TestBaseDir(unittest.TestCase):
    def test_env_override_wins(self):
        os.environ["SUPERPOWERS_TELEMETRY_DIR"] = "/tmp/telemetry-override"
        self.addCleanup(os.environ.pop, "SUPERPOWERS_TELEMETRY_DIR", None)
        self.assertEqual(store.base_dir(), "/tmp/telemetry-override")

    def test_default_lives_under_claude_config(self):
        os.environ.pop("SUPERPOWERS_TELEMETRY_DIR", None)
        os.environ["CLAUDE_CONFIG_DIR"] = "/tmp/cfg"
        self.addCleanup(os.environ.pop, "CLAUDE_CONFIG_DIR", None)
        self.assertEqual(store.base_dir(), "/tmp/cfg/superpowers/telemetry")


class TestAppend(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_writes_one_line_per_record(self):
        store.append_records([row(), row()], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["kind"], "seg")

    def test_appends_rather_than_truncates(self):
        store.append_records([row()], self.base)
        store.append_records([row()], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 2)

    def test_rotates_by_month(self):
        store.append_records([row("2026-08-31T23:59:59Z"), row("2026-09-01T00:00:01Z")], self.base)
        self.assertTrue(os.path.exists(os.path.join(self.base, "2026-08.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(self.base, "2026-09.jsonl")))

    def test_empty_batch_creates_nothing(self):
        store.append_records([], self.base)
        self.assertFalse(os.path.exists(self.base))

    def test_non_ascii_is_written_unescaped(self):
        store.append_records([row(project="日本語")], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            self.assertIn("日本語", handle.read())

    def test_gives_up_when_the_file_stays_locked(self):
        os.makedirs(self.base, exist_ok=True)
        path = os.path.join(self.base, "2026-08.jsonl")
        blocker = open(path, "a", encoding="utf-8")
        fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)
        try:
            with self.assertRaises(OSError):
                store.append_records([row()], self.base)
        finally:
            fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
            blocker.close()


class TestState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_round_trip(self):
        store.save_state("s-1", {"line": 42, "main": {}}, self.base)
        self.assertEqual(store.load_state("s-1", self.base, {"line": 0}), {"line": 42, "main": {}})

    def test_missing_state_returns_the_default(self):
        self.assertEqual(store.load_state("nope", self.base, {"line": 0}), {"line": 0})

    def test_corrupt_state_returns_the_default(self):
        os.makedirs(os.path.join(self.base, ".state"), exist_ok=True)
        with open(os.path.join(self.base, ".state", "s-2.json"), "w", encoding="utf-8") as handle:
            handle.write("{ broken")
        self.assertEqual(store.load_state("s-2", self.base, {"line": 0}), {"line": 0})

    def test_state_without_line_key_returns_the_default(self):
        store.save_state("s-3", {"unexpected": True}, self.base)
        self.assertEqual(store.load_state("s-3", self.base, {"line": 0}), {"line": 0})

    def test_session_id_cannot_escape_the_state_directory(self):
        store.save_state("../../escape", {"line": 1}, self.base)
        entries = os.listdir(os.path.join(self.base, ".state"))
        self.assertEqual(len(entries), 1)
        self.assertNotIn("..", entries[0])


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_removes_only_stale_state(self):
        store.save_state("fresh", {"line": 1}, self.base)
        store.save_state("stale", {"line": 1}, self.base)
        stale = os.path.join(self.base, ".state", "stale.json")
        old = time.time() - 31 * 86400
        os.utime(stale, (old, old))
        self.assertEqual(store.prune_states(self.base), 1)
        remaining = os.listdir(os.path.join(self.base, ".state"))
        self.assertEqual(remaining, ["fresh.json"])

    def test_missing_directory_is_not_an_error(self):
        self.assertEqual(store.prune_states(self.base), 0)


class TestErrorLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_writes_one_json_line(self):
        store.log_error(self.base, "s-1", "ValueError: boom")
        with open(os.path.join(self.base, "errors.log"), encoding="utf-8") as handle:
            entry = json.loads(handle.read().splitlines()[0])
        self.assertEqual(entry["session"], "s-1")
        self.assertIn("boom", entry["error"])

    def test_never_raises(self):
        store.log_error("/proc/cannot/write/here", "s-1", "boom")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `python3 -m unittest discover -s tests/hooks/telemetry -p 'test_store.py' -v`
Expected: FAIL — `ImportError: cannot import name 'store'`

- [ ] **Step 3: 実装する**

`hooks/custom/telemetry_lib/store.py`:

```python
"""Where telemetry lands: the monthly JSONL, the state files, the error log.

The only module that writes to the filesystem. It deliberately knows nothing
about the shape of a segment or of the state — callers supply both — so the
segmentation logic stays testable without touching a disk.
"""

import fcntl
import json
import os
import time
from datetime import datetime, timezone

STATE_MAX_AGE_DAYS = 30
LOCK_ATTEMPTS = 3
LOCK_WAIT_SECONDS = 0.2


def base_dir():
    """Directory holding the telemetry. SUPERPOWERS_TELEMETRY_DIR overrides it."""
    override = os.environ.get("SUPERPOWERS_TELEMETRY_DIR")
    if override:
        return override
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(config, "superpowers", "telemetry")


def _safe(name):
    """A filename component that cannot escape its directory."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in (name or "unknown"))


def _state_dir(base):
    return os.path.join(base, ".state")


def _month_of(record):
    stamp = record.get("ts") or ""
    if len(stamp) >= 7 and stamp[4] == "-":
        return stamp[:7]
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _append_locked(path, payload):
    """Append `payload` under an exclusive lock, or raise after retrying.

    Several sessions and subagents append to the same monthly file. Losing a
    row matters far less than blocking the session, so this gives up quickly
    and lets the caller log the failure.
    """
    last_error = None
    for attempt in range(LOCK_ATTEMPTS):
        handle = open(path, "a", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            last_error = error
            if attempt < LOCK_ATTEMPTS - 1:
                time.sleep(LOCK_WAIT_SECONDS)
            continue
        try:
            handle.write(payload)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return
    raise last_error


def append_records(records, base):
    """Append records to their month's file. One lock per file."""
    if not records:
        return
    os.makedirs(base, exist_ok=True)
    grouped = {}
    for record in records:
        grouped.setdefault(_month_of(record), []).append(record)
    for month, rows in sorted(grouped.items()):
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        _append_locked(os.path.join(base, month + ".jsonl"), payload)


def load_state(session, base, default):
    """Stored state for a session, or `default` when absent or unusable."""
    path = os.path.join(_state_dir(base), _safe(session) + ".json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return default
    if not isinstance(loaded, dict) or "line" not in loaded:
        return default
    return loaded


def save_state(session, state, base):
    """Write state atomically, so a killed hook cannot leave a torn file."""
    directory = _state_dir(base)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _safe(session) + ".json")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(temporary, path)


def prune_states(base, max_age_days=STATE_MAX_AGE_DAYS):
    """Delete state files untouched for `max_age_days`. Returns the count."""
    directory = _state_dir(base)
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def log_error(base, session, message):
    """Record a failure without ever raising one of its own."""
    try:
        os.makedirs(base, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        entry = json.dumps(
            {"ts": stamp, "session": session, "error": str(message)[:500]}, ensure_ascii=False)
        with open(os.path.join(base, "errors.log"), "a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
    except Exception:
        pass
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_store.py' -v`
Expected: PASS(17 tests)

- [ ] **Step 5: コミット**

```bash
git add hooks/custom/telemetry_lib/store.py tests/hooks/telemetry/test_store.py
git commit -m "feat(telemetry): persist segments, state, and failures

Keeps every filesystem touch in one module so the segmentation logic can be
tested without a disk, and so the concurrency rules live in one place.

Sessions and subagents all append to the same monthly file, so writes take
an exclusive lock. It retries three times and then gives up: losing one row
costs a data point, while blocking on a lock costs the session."
```

---

### Task 6: エントリポイントと bash ラッパ

フック payload を受け取って全体を繋ぎ、**何があっても stdout を汚さず exit 0** する。

**Files:**
- Create: `hooks/custom/telemetry.py`
- Create: `hooks/custom/telemetry` (chmod +x)
- Test: `tests/hooks/test-telemetry.sh`

**Interfaces:**
- Consumes: `telemetry_lib.transcript`, `telemetry_lib.skills`, `telemetry_lib.segments`, `telemetry_lib.store`
- Produces:
  - `project_of(cwd: str | None) -> str | None`
  - `plugin_root() -> str`
  - `run(payload: dict, base: str) -> int`(書き出したレコード数)
  - `main() -> int`(常に `0`)

- [ ] **Step 1: エントリポイントを実装する**

`hooks/custom/telemetry.py`:

```python
#!/usr/bin/env python3
"""Session telemetry hook: Stop and SubagentStop.

Folds the new part of the session transcript into (turn x skill) segments
and appends them as JSONL.

This hook never writes to stdout and never exits non-zero. A Stop hook that
says anything can change what the harness does, and one that fails would
break the session it exists only to observe.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telemetry_lib import segments as sg  # noqa: E402
from telemetry_lib import skills as sk  # noqa: E402
from telemetry_lib import store  # noqa: E402
from telemetry_lib import transcript as tx  # noqa: E402


def project_of(cwd):
    """Repository name for `cwd`, by walking up to a .git — no git process.

    Shelling out to git would add a subprocess to every turn for a value the
    filesystem already answers.
    """
    if not cwd:
        return None
    start = os.path.abspath(cwd)
    path = start
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return os.path.basename(path)
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.basename(start)
        path = parent


def plugin_root():
    """The installed plugin directory: hooks/custom/telemetry.py is two down."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return root
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def run(payload, base):
    """Process one hook invocation. Returns how many segments were written."""
    session = payload.get("session_id") or "unknown"
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0

    state = store.load_state(session, base, sg.new_state())
    records, total = tx.read_new_records(path, state.get("line", 0))
    state["line"] = total
    if not records:
        store.save_state(session, state, base)
        return 0

    root = plugin_root()
    is_subagent = payload.get("hook_event_name") == "SubagentStop"
    ctx = {
        "session": session,
        "default_agent": "subagent" if is_subagent else "main",
        "project": project_of(payload.get("cwd")),
        "plugin_root": root,
        "plugin_version": sk.plugin_version(root),
        "subagent_type": payload.get("subagent_type"),
        "parent_turn": None,
    }

    rows, state = sg.build_segments(records, state, ctx)
    store.append_records(rows, base)
    store.save_state(session, state, base)
    store.prune_states(base)
    return len(rows)


def main():
    base = store.base_dir()
    session = "unknown"
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        session = payload.get("session_id") or "unknown"
        run(payload, base)
    except Exception as error:
        store.log_error(base, session, "%s: %s" % (type(error).__name__, error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: bash ラッパを実装する**

`hooks/custom/telemetry`:

```bash
#!/usr/bin/env bash
#
# Stop / SubagentStop telemetry hook for this fork.
#
# Records (turn x skill) segments of the session as JSONL under
# ~/.claude/superpowers/telemetry/. See docs/fork/telemetry.md.
#
# Deliberately not `set -e`: this hook observes a session, it must never end
# one. Nothing is written to stdout, because a Stop hook's stdout can change
# what the harness does.

set -uo pipefail

command -v python3 >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 "${SCRIPT_DIR}/telemetry.py" >/dev/null 2>&1 || true

exit 0
```

実行権限を付ける:

```bash
chmod +x hooks/custom/telemetry
```

- [ ] **Step 3: エンドツーエンドテストを書く**

`tests/hooks/test-telemetry.sh`:

```bash
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

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "All telemetry hook tests passed."
    exit 0
fi
echo "$FAILURES test(s) failed."
exit 1
```

実行権限を付ける:

```bash
chmod +x tests/hooks/test-telemetry.sh
```

- [ ] **Step 4: エンドツーエンドテストを実行する**

Run: `cd /home/ubuntu/projects/superpowers && bash tests/hooks/test-telemetry.sh`
Expected: PASS(全チェックが `[PASS]`、`All telemetry hook tests passed.`)

失敗した場合、まず単体テストを全部走らせて原因の層を切り分ける:
`python3 -m unittest discover -s tests/hooks/telemetry -p 'test_*.py' -v`

- [ ] **Step 5: 単体テストを全て実行する**

Run: `cd /home/ubuntu/projects/superpowers && python3 -m unittest discover -s tests/hooks/telemetry -p 'test_*.py'`
Expected: PASS(70 tests, `OK`)

- [ ] **Step 6: コミット**

```bash
git add hooks/custom/telemetry.py hooks/custom/telemetry tests/hooks/test-telemetry.sh
git commit -m "feat(telemetry): wire the hook entry point and its wrapper

The wrapper is deliberately not 'set -e' and writes nothing to stdout. A
Stop hook's stdout is interpreted by the harness, and a hook that exists
only to observe a session must never be able to end one — so every failure
path lands in errors.log instead.

The project name comes from walking up to a .git rather than shelling out,
keeping the per-turn cost to a filesystem check."
```

---

### Task 7: フック登録と実セッション確認

`hooks/hooks.json` に 2 ブロック追加し、本物のセッションで記録されることを確認する。

**Files:**
- Modify: `hooks/hooks.json`

**Interfaces:**
- Consumes: `hooks/custom/telemetry`
- Produces: なし(最終タスクは Task 8 の文書のみ)

- [ ] **Step 1: 変更前の状態を記録する**

```bash
cd /home/ubuntu/projects/superpowers
cat hooks/hooks.json
bash tests/hooks/test-session-start.sh
```

Expected: 既存テストが全て PASS(この後の変更で壊れていないことを比較するための基準)

- [ ] **Step 2: `hooks/hooks.json` を書き換える**

`SessionStart` ブロックはそのまま残し、`Stop` と `SubagentStop` を追加する。**このファイルは upstream との唯一の共有コンフリクト面なので、既存の行には一切触れない。**

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
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/custom/telemetry\"",
            "shell": "bash",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/custom/telemetry\"",
            "shell": "bash",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Task 1 Step 5 で `async` が `Stop` に効かないと分かっていた場合は、両ブロックから `"async": true` の行を削除する。** 処理は数十ミリ秒で終わるため同期実行でも実害はない。

- [ ] **Step 3: JSON として妥当であることを確認する**

```bash
cd /home/ubuntu/projects/superpowers
python3 -m json.tool hooks/hooks.json >/dev/null && echo "valid JSON"
python3 -c "
import json
data = json.load(open('hooks/hooks.json'))
events = sorted(data['hooks'])
print('events:', events)
assert events == ['SessionStart', 'Stop', 'SubagentStop'], events
print('SessionStart untouched:', data['hooks']['SessionStart'][0]['matcher'])
"
```

Expected: `valid JSON` と `events: ['SessionStart', 'Stop', 'SubagentStop']`、`SessionStart untouched: startup|clear|compact`

- [ ] **Step 4: 既存フックが壊れていないことを確認する**

Run: `cd /home/ubuntu/projects/superpowers && bash tests/hooks/test-session-start.sh`
Expected: PASS(Step 1 と同じ結果)

- [ ] **Step 5: 本物のセッションで記録を確認する**

このリポジトリをプラグインとして読み込んでいる Claude Code を再起動し(`/plugin` で再読み込み、または新しいセッションを開始)、何かひとつ skill を呼ぶやり取りをしてから確認する。

```bash
ls -la ~/.claude/superpowers/telemetry/
tail -3 ~/.claude/superpowers/telemetry/*.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('{'):
        continue
    row = json.loads(line)
    print('turn=%s seq=%s skill=%s phase=%s exec_ms=%s wait_ms=%s out=%s project=%s branch=%s' % (
        row['turn'], row['seq'], row['skill'], row['phase'], row['exec_ms'], row['wait_ms'],
        row['tokens']['out'], row['project'], row['branch']))
"
cat ~/.claude/superpowers/telemetry/errors.log 2>/dev/null || echo "no errors logged"
```

Expected: 行が出力され、`project` が `superpowers`、`branch` が `feat/telemetry-hook`、`errors.log` が空か存在しない。

**`errors.log` に行があれば、そこに原因が書かれている。** 直してから次に進む。

- [ ] **Step 6: サブエージェントが記録されることを確認する**

セッション内でサブエージェントを 1 回起動してから確認する。

```bash
python3 - <<'PY'
import glob, json
rows = []
for path in glob.glob('/home/ubuntu/.claude/superpowers/telemetry/*.jsonl'):
    for line in open(path, encoding='utf-8'):
        rows.append(json.loads(line))
agents = {}
for row in rows:
    agents[row['agent']] = agents.get(row['agent'], 0) + 1
print('rows by agent:', agents)
for row in rows:
    if row['agent'] == 'subagent':
        print('subagent row:', json.dumps(row, ensure_ascii=False)[:300])
        break
PY
```

Expected: `subagent` の行が 1 つ以上ある。**0 件だった場合は Task 1 Step 1 の実測結果に立ち返る** — サブエージェントが別 transcript を持つなら、`SubagentStop` の payload に別の `transcript_path` が来ているはずで、それが処理されているかを `errors.log` と状態ファイルで確認する。

- [ ] **Step 7: コミット**

```bash
git add hooks/hooks.json
git commit -m "feat(telemetry): register the hook on Stop and SubagentStop

Two blocks appended, nothing existing touched. hooks/hooks.json is the only
file where this fork's hooks can collide with upstream's, so every edit here
is kept to the smallest possible addition."
```

---

### Task 8: 利用者向け文書と分岐台帳

データの読み手が知る必要のあること(スキーマ、限界、集計方法)を書き、フォークの分岐台帳に記録する。

**Files:**
- Create: `docs/fork/telemetry.md`
- Modify: `docs/fork/DIVERGENCE.md`(Custom hooks 表)

**Interfaces:**
- Consumes: なし
- Produces: なし

- [ ] **Step 1: `docs/fork/telemetry.md` を書く**

````markdown
# セッションテレメトリ

このフォークは、セッションとサブエージェントの活動を
`~/.claude/superpowers/telemetry/YYYY-MM.jsonl` に記録する。

設計の経緯は
[docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md](../superpowers/specs/2026-08-21-session-telemetry-hook-design.md)
にある。

## 何が記録されるか

**1 行 = 1 セグメント = (セッション, ターン, skill)。**

1 ターンの中でエージェントは自分の判断で skill を切り替える。ターン単位で
集計するとその時間とトークンが混ざるため、`Skill` の呼び出しごとに行を分ける。

```jsonc
{
  "schema_version": 1,
  "kind": "seg",
  "ts": "2026-08-21T04:12:33.412Z", "ts_end": "2026-08-21T04:13:04.417Z",
  "session": "5f655673-…", "turn": 7, "seq": 1,
  "agent": "main", "subagent_type": null, "parent_turn": null,
  "first_uuid": "9c1f…",
  "skill": "superpowers:requesting-code-review", "skill_rev": "7c20be11",
  "invoked_by": "model", "phase": "reviewing",
  "project": "superpowers", "branch": "feat/telemetry-hook",
  "cc_version": "2.1.4", "plugin_version": "1.0.0",
  "model": "claude-opus-5", "effort": "high",
  "mode": "normal", "permission_mode": "auto",
  "exec_ms": 31005, "wait_ms": 0, "api_calls": 12,
  "tokens": { "in": 2, "out": 8100, "thinking": 2210, "cache_read": 220625,
              "cache_create_5m": 0, "cache_create_1h": 10860 },
  "tools": { "Bash": 6, "Edit": 2 },
  "tool_errors": 1, "stop_reason": "end_turn", "compacted": false
}
```

`skill_rev` は `SKILL.md` の sha256 の先頭 8 桁。skill にバージョン番号は無く、
プラグインのバージョンは `SKILL.md` を編集しても動かないため、改修の前後を
比較するにはこのハッシュが要る。

`first_uuid` はトランスクリプトへの逆引きアンカー。ある行が不審なとき、
`grep <first_uuid> ~/.claude/projects/*/*.jsonl` で当時の様子に戻れる。

## 記録されないもの

**プロンプト本文、ファイルの内容、ツールの引数は記録しない。** 残るのは
skill 名、ツール名と回数、数値、プロジェクト名、ブランチ名だけ。送信先は無い。

## 読むときに知っておくべき限界

1. **skill のネストは表現されない。** `brainstorming` が `writing-plans` を
   呼ぶと、以後は `writing-plans` が有効なままになる。skill の *終了* を示す
   信号がトランスクリプトに無いため、親への復帰は観測できない
2. **権限プロンプトの待ち時間は `exec_ms` に含まれる。** `AskUserQuestion` と
   `ExitPlanMode` の回答待ちは `wait_ms` に分離されるが、権限確認の待ちは
   トランスクリプトに行として残らないため分離できない
3. **`invoked_by` と `parent_turn` はベストエフォート。** 判定できない場合は
   それぞれ `"model"` と `null` に倒れる
4. **`cache_read` は請求上の実数。** リクエストごとに課金されるため、
   合算すると「同じコンテキストを何度も読んだ」分が積み上がる。これは
   誤りではなく、実際にそう課金される

## 集計

```bash
cd ~/.claude/superpowers/telemetry

# skill 別の合計実行時間・出力トークン・ツール失敗数
cat 2026-*.jsonl | jq -s '
  group_by(.skill)[] |
  { skill: .[0].skill,
    segments: length,
    exec_min: (map(.exec_ms) | add / 60000 | floor),
    out: (map(.tokens.out) | add),
    errors: (map(.tool_errors) | add) }'

# skill が自発的に発火した割合 — 呼ばれない skill を探す
cat 2026-*.jsonl | jq -s '
  map(select(.skill != null)) | group_by(.skill)[] |
  { skill: .[0].skill,
    by_model: (map(select(.invoked_by == "model")) | length),
    by_user:  (map(select(.invoked_by == "user"))  | length) }'

# skill の版ごとの比較 — 改修の前後
cat 2026-*.jsonl | jq -s '
  map(select(.skill == "superpowers:brainstorming")) |
  group_by(.skill_rev)[] |
  { rev: .[0].skill_rev,
    n: length,
    avg_exec_s: (map(.exec_ms) | add / length / 1000 | floor),
    avg_out: (map(.tokens.out) | add / length | floor) }'

# プロジェクト別トークン
cat 2026-*.jsonl | jq -s '
  group_by(.project)[] |
  { project: .[0].project,
    in: (map(.tokens.in) | add),
    out: (map(.tokens.out) | add),
    cache_read: (map(.tokens.cache_read) | add),
    cache_create: (map(.tokens.cache_create_5m + .tokens.cache_create_1h) | add) }'

# 実行時間 対 待機時間
cat 2026-*.jsonl | jq -s '
  { exec_h: (map(.exec_ms) | add / 3600000),
    wait_h: (map(.wait_ms) | add / 3600000) }'
```

## 止めかた・消しかた

`hooks/hooks.json` から `Stop` と `SubagentStop` のブロックを消せば止まる。
記録済みのデータは `rm -rf ~/.claude/superpowers/telemetry/` で消える。

出力先は `SUPERPOWERS_TELEMETRY_DIR` で変更できる。

## 動かないときは

`~/.claude/superpowers/telemetry/errors.log` に理由が 1 行ずつ入る。
ファイルが無く、JSONL も増えていない場合は、`python3` が PATH にあるか確認する
(無い場合、フックは何もせずに終了する)。
````

- [ ] **Step 2: `docs/fork/DIVERGENCE.md` の Custom hooks 表に行を追加する**

`| _(none yet)_ | | | |` の行を次で置き換える。

```markdown
| Session telemetry | `hooks/custom/telemetry`, `hooks/custom/telemetry.py`, `hooks/custom/telemetry_lib/` | `Stop`, `SubagentStop` | Records one JSONL row per (turn × skill) under `~/.claude/superpowers/telemetry/`, for skill-improvement, cost and time analysis. New files only; `hooks/hooks.json` gains two blocks and nothing existing is touched. Python 3 standard library only, no new dependencies. See [telemetry.md](telemetry.md). |
```

- [ ] **Step 3: リンクが壊れていないことを確認する**

```bash
cd /home/ubuntu/projects/superpowers
test -f docs/fork/telemetry.md && echo "telemetry.md exists"
test -f docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md && echo "spec exists"
grep -c "telemetry" docs/fork/DIVERGENCE.md
```

Expected: 両方 exist、`DIVERGENCE.md` に `telemetry` が 2 回以上

- [ ] **Step 4: 全テストを最終確認する**

```bash
cd /home/ubuntu/projects/superpowers
python3 -m unittest discover -s tests/hooks/telemetry -p 'test_*.py'
bash tests/hooks/test-telemetry.sh
bash tests/hooks/test-session-start.sh
```

Expected: 3 つとも成功。**出力を実際に読んでから完了と言うこと。**

- [ ] **Step 5: コミット**

```bash
git add docs/fork/telemetry.md docs/fork/DIVERGENCE.md
git commit -m "docs(fork): document the telemetry schema and its limits

The numbers are only usable by someone who knows what they exclude: skill
nesting is not represented, permission-prompt waits land in exec_ms, and
cache_read sums the way it bills rather than the way context is read.

Records the hook in the divergence ledger so the next upstream merge knows
what these files are."
```

---

## Self-Review

このセクションは計画作成者が実施済み。実装者は読むだけでよい。

**1. 仕様カバレッジ**

| 仕様の節 | 対応タスク |
|---|---|
| §1 背景と目的 / 中核要件 | Task 4 の `TestSkillSwitchWithinOneTurn` |
| §2 非目標 | 集計 CLI を作るタスクは無い。Task 8 で jq レシピのみ |
| §3 アーキテクチャ | Task 2〜6 のファイル構成、Task 7 の 2 フック登録 |
| §4 データ源 | Task 2 `transcript.py`、Task 6 `project_of`(git 非依存) |
| §5 セグメント分割 | Task 4。空セグメントは `TestBoundaryHandling` |
| §6 時間の定義 | Task 1 Step 7 で補正、Task 4 `TestWaitTime` |
| §7 スキーマ | Task 4 `TestRecordShape` が全 31 フィールドを検証 |
| §8 phase 写像 | Task 3 `TestPhaseMapping` + Step 5 の実在名照合 |
| §9 状態管理と増分読み | Task 2 `TestIncrementalRead`、Task 5 `TestState` |
| §10 保存先とローテーション | Task 5 `TestAppend.test_rotates_by_month` |
| §11 失敗時の挙動 / 書き込み競合 | Task 5 `test_gives_up_when_the_file_stays_locked`、Task 6 e2e 3〜6 |
| §12 プライバシー | Task 4 `test_no_prompt_text_leaks_into_the_record`、Task 6 e2e 7 |
| §13 ファイル構成 | Task 7、Task 8 |
| §14 テスト計画(12 項目) | Task 2〜6 に分散。全 12 項目に対応するテストがある |
| §15 未検証リスク | Task 1 |
| §16 集計レシピ | Task 8 Step 1 |

**2. プレースホルダ走査**

`TBD` / `TODO` / 「後で」/「適切に」の類は無い。全ステップに実行可能なコマンドか完全なコードが入っている。Task 1 Step 6 の仕様追記だけは実測値を埋める作業であり、埋めるべき内容と「確定できなかった場合の書き方」を明示している。

**3. 型と名前の整合**

- `transcript.py` の定数名(`USER_PROMPT` 他)は Task 4 の `tx.USER_PROMPT` と一致
- `usage_of` の返すキー(`in`/`out`/`thinking`/`cache_read`/`cache_create_5m`/`cache_create_1h`)は `segments.py` の `_ZERO_TOKENS` と一致
- `skills.py` の `HUMAN_BLOCKING_TOOLS` は Task 4 の `sk.HUMAN_BLOCKING_TOOLS` と一致
- `store.load_state(session, base, default)` の 3 引数は Task 6 の呼び出しと一致
- `build_segments` の `ctx` キー(`session`/`default_agent`/`project`/`plugin_root`/`plugin_version`/`subagent_type`/`parent_turn`)は Task 6 が組み立てる辞書と一致
