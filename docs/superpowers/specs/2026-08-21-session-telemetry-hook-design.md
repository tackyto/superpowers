# セッションテレメトリ フック 設計

- 日付: 2026-08-21
- 状態: 承認済み(実装前)
- 対象: このフォーク専用の新規フック(upstream には送らない)

## 1. 背景と目的

このプラグインを導入したセッション(サブエージェント含む)について、
使用 skill・バージョン・フェーズ・トークン・実行時間・待機時間・プロジェクト名・
ブランチ名を JSONL でローカルに記録する。

収集データの用途は次の3つに限定する。

1. **コスト / トークン消費の可視化** — セッション・プロジェクト・モデル別のトークン集計
2. **skill の遵守と効果の測定** — どの skill がいつ・どの版で発火し、その結果どうなったか
3. **作業時間の分析** — エージェントが動いていた時間と、人間の応答を待っていた時間の内訳

用途 2 が最も重要である。**このデータは skill の改修要否を判断するための材料**であり、
skill 単位で切り分けられないデータには価値がない。

### 中核要件: skill 単位の分離

1 ターンの中でエージェントが自動的に skill を切り替えることがある
(例: `test-driven-development` で実装したあと、同じターン内で
`requesting-code-review` に移る)。ターン単位の集計ではこの2つの時間と
トークンが混ざり、どちらの skill が重いのか判定できない。

したがって **JSONL の 1 行は「ターン × skill」** とする。

### 実現可能性の事前検証

実際のトランスクリプトで検証済み(2026-08-21)。

- `Skill` ツールの呼び出しは skill 名・引数・タイムスタンプ付きで記録される
- assistant 行には `usage`(input / output / cache_read / cache_creation / thinking)、
  `timestamp`、`model`、`effort`、`version`、`gitBranch`、`uuid`、`requestId`、
  `stop_reason` が揃っている
- `type:"user"` 行は、実プロンプト / 注入メタ(`isMeta`) / `tool_result` の 3 種を判別できる
- 試作スクリプトで 1 セッションを skill セグメントに分解し、時間とトークンの
  割り当てに成功している

## 2. 非目標(YAGNI)

- **集計 CLI やダッシュボードは作らない。** §12 の jq レシピに留める
- 送信・アップロード機能は作らない。保存はローカルのみ
- **コストの $ 換算は行わない。** 単価は変動するため、モデル名とトークン実数だけを残し、
  換算は集計時に行う
- git SHA、ホスト名、`service_tier` は記録しない
  (SHA はサブプロセスを要し、他 2 つは現時点で情報量がない)

## 3. 全体アーキテクチャ

フック登録は `Stop` と `SubagentStop` の 2 つのみ。

```
Stop / SubagentStop
  └─ hooks/custom/telemetry          bash 薄ラッパ。python3 が無ければ exit 0
       └─ hooks/custom/telemetry.py  python3 標準ライブラリのみ
            ├─ 入力: フックの stdin JSON (session_id, transcript_path, cwd)
            ├─ 読む: transcript_path の JSONL を前回の続きから増分で
            ├─ 状態: ~/.claude/superpowers/telemetry/.state/<session_id>.json
            └─ 追記: ~/.claude/superpowers/telemetry/YYYY-MM.jsonl
```

### 却下した代替案

**`PreToolUse` / `PostToolUse` を全ツールに掛けてイベントを逐次記録する案。**
トークン数はフックの入力 JSON に含まれず、結局トランスクリプトを読む必要がある。
全ツール呼び出しにフックを挟んでもレイテンシが増えるだけで、得られる情報は増えない。

**イベント単位 / セッション単位の記録。**
イベント単位は 1 セッション数百〜数千行に膨らむ割に、中核要件(skill 単位の分離)は
ターン × skill で足りる。セッション単位は skill 別の内訳が消えるため要件を満たさない。

## 4. データ源

| 欲しい値 | 取得元 |
|---|---|
| session_id / transcript_path / cwd | フックの stdin JSON |
| トークン各種 | transcript の assistant 行 `message.usage` |
| タイムスタンプ | transcript の各行 `timestamp` |
| ブランチ名 | transcript の `gitBranch` |
| Claude Code バージョン | transcript の `version` |
| モデル / effort | transcript の `message.model` / `effort` |
| 使用 skill | assistant 行の `tool_use` (`name == "Skill"`) の `input.skill` |
| skill の版 | `SKILL.md` の内容ハッシュ(実行時に算出) |
| プラグイン版 | `.claude-plugin/plugin.json` の `version` |
| mode / permission_mode | transcript の `type:"mode"` / `type:"permission-mode"` 行 |

**git コマンドを一切呼ばない。** ブランチ名も Claude Code のバージョンも
transcript に実値があり、しかも「その時点の値」として正確である。

`project` はリポジトリのルート名だが、これも git を起動せずに求める。
cwd から親方向へ `.git` の存在をファイルシステム上で探し、見つかった
ディレクトリの basename を使う。見つからなければ cwd の basename を使う。

## 5. セグメント分割アルゴリズム

transcript の行を時刻順に走査し、次の境界でセグメントを切る。

| 境界 | 判定 |
|---|---|
| ターン開始 | `type:"user"` かつ content が文字列または `text` ブロック かつ `isMeta` が偽 |
| skill 切替 | assistant 行の `tool_use` で `name == "Skill"` → 以後 active skill を差し替え |
| セグメント終端 | 次の skill 切替、またはターン終端 |

- skill が有効でない区間も `skill: null` として記録する。取りこぼしを作らない
- `type:"user"` のうち `tool_result` を含む行はターン境界ではない(同一ターン内の継続)
- `isMeta` が真の user 行はシステム注入であり、ターン境界ではない

### 空セグメントは出力しない

セグメントに assistant 行が 1 つも含まれず、経過時間も 0 の場合は行を出力しない。

これはターンの最後の行動として skill を呼び、実際の作業が次のターンで始まる場合に起きる。
その skill は状態ファイルの `active_skill` として持ち越され、次のターンの
`seq: 0` セグメントで正しく計上される。空行を出すとノイズにしかならない。

### 既知の限界: ネストは表現しない

`brainstorming` が `writing-plans` を呼ぶようなネストは、
**「最後に呼ばれた skill が有効」** として扱う。skill の *終了* を示す信号が
transcript に存在しないため、親 skill への復帰は観測できない。

この限界はデータの読み手が知っている必要があるため、
`docs/fork/telemetry.md` にも明記する。

### skill のターンまたぎ

active skill は状態ファイルで次ターンへ持ち越す。
1 つの skill が複数ターンにわたって有効な場合、ターンごとに別々の行が出る。
skill 単位で集計するときは `skill` で group by すればよい。

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

## 7. スキーマ(確定版)

1 行 = 1 セグメント = (session, turn, seq)。

```jsonc
{
  "schema_version": 1,
  "kind": "seg",
  "ts": "2026-08-21T04:12:33.412Z",
  "ts_end": "2026-08-21T04:13:04.417Z",

  "session": "5f655673-4088-465d-ade7-b48bbe42e428",
  "turn": 7,
  "seq": 1,
  "agent": "main",
  "subagent_type": null,
  "parent_turn": null,
  "first_uuid": "9c1f0e2a-...",

  "skill": "superpowers:requesting-code-review",
  "skill_rev": "7c20be11",
  "invoked_by": "model",
  "phase": "reviewing",

  "project": "superpowers",
  "branch": "feat/telemetry-hook",
  "cc_version": "2.1.4",
  "plugin_version": "1.0.0",
  "model": "claude-opus-5",
  "effort": "high",
  "mode": "normal",
  "permission_mode": "auto",

  "exec_ms": 31005,
  "wait_ms": 0,
  "api_calls": 12,

  "tokens": {
    "in": 2,
    "out": 8100,
    "thinking": 2210,
    "cache_read": 220625,
    "cache_create_5m": 0,
    "cache_create_1h": 10860
  },

  "tools": { "Bash": 6, "Edit": 2 },
  "tool_errors": 1,
  "stop_reason": "end_turn",
  "compacted": false
}
```

### フィールド定義

| フィールド | 型 | 意味 |
|---|---|---|
| `schema_version` | int | このスキーマの版。変更時に必ず上げる |
| `kind` | string | 現在は `"seg"` のみ。将来別種のレコードを足せる余地 |
| `ts` / `ts_end` | string | セグメントの開始 / 終了時刻(ISO 8601, UTC) |
| `session` | string | Claude Code のセッション ID |
| `turn` | int | セッション内のターン番号(1 起点) |
| `seq` | int | ターン内のセグメント番号(0 起点) |
| `agent` | string | `"main"` または `"subagent"` |
| `subagent_type` | string \| null | サブエージェントの種別(`"Explore"` 等)。本体では `null` |
| `parent_turn` | int \| null | サブエージェントを起動した親ターン。判定不能なら `null` |
| `first_uuid` | string \| null | セグメント先頭 assistant 行の `uuid`。transcript への逆引きアンカー |
| `skill` | string \| null | 有効だった skill。無ければ `null` |
| `skill_rev` | string \| null | `SKILL.md` の sha256 先頭 8 桁。skill 未特定なら `null` |
| `invoked_by` | string | `"model"` / `"user"` / `"session-start"` |
| `phase` | string | §8 の写像による作業フェーズ |
| `project` | string | cwd から上へ `.git` を探して見つかったディレクトリの basename。見つからなければ cwd の basename |
| `branch` | string \| null | transcript の `gitBranch` |
| `cc_version` | string | transcript の `version` |
| `plugin_version` | string | `.claude-plugin/plugin.json` の `version` |
| `model` | string | transcript の `message.model` の実値 |
| `effort` | string \| null | transcript の `effort` |
| `mode` | string \| null | 直近の `type:"mode"` 行の値 |
| `permission_mode` | string \| null | 直近の `type:"permission-mode"` 行の値 |
| `exec_ms` | int | §6 の定義による実行時間(ミリ秒) |
| `wait_ms` | int | §6 の定義による待機時間。ターン境界の待ちに加え、`AskUserQuestion` / `ExitPlanMode` の回答待ちを含む |
| `api_calls` | int | セグメント内の assistant メッセージ数 |
| `tokens.in` | int | `usage.input_tokens` の合計 |
| `tokens.out` | int | `usage.output_tokens` の合計 |
| `tokens.thinking` | int | `usage.output_tokens_details.thinking_tokens` の合計 |
| `tokens.cache_read` | int | `usage.cache_read_input_tokens` の合計 |
| `tokens.cache_create_5m` | int | `usage.cache_creation.ephemeral_5m_input_tokens` の合計 |
| `tokens.cache_create_1h` | int | `usage.cache_creation.ephemeral_1h_input_tokens` の合計 |
| `tools` | object | ツール名 → 呼び出し回数 |
| `tool_errors` | int | `is_error` が真の `tool_result` の数 |
| `stop_reason` | string \| null | セグメント最後の assistant 行の `message.stop_reason` |
| `compacted` | bool | このセグメント中にコンパクション境界の行が現れたか(判定方法は §15-5 で確定) |

### 各フィールドを入れる理由(後から復元できないもの)

- **`cache_create_5m` / `cache_create_1h` の分離** — 5 分キャッシュと 1 時間キャッシュは
  単価が異なる。合算すると正確なコストが算出できない
- **`invoked_by`** — その skill が自発的に発火したのか、人間が
  `/brainstorming` と打って初めて動いたのか。「呼ばれない skill」は改修対象そのものであり、
  この列が無いと発火失敗が記録に残らない
- **`tool_errors`** — skill の手順に従った結果どれだけ失敗したかは skill 品質の直接指標
- **`first_uuid`** — 数値だけ残しても原因調査ができない。transcript に戻る手段が要る
- **`stop_reason`** — `max_tokens` や中断が混ざると「重い skill」の判定が変わる
- **`schema_version`** — 将来の変更で旧データが解釈不能になるのを防ぐ

### ベストエフォートな判定

`invoked_by` と `parent_turn` は確実な判定手段が未確定である。

- `invoked_by` — ターンのユーザープロンプトがその skill のスラッシュコマンドだった場合
  `"user"`、SessionStart による注入なら `"session-start"`、いずれでもなければ `"model"`。
  判定不能な場合は `"model"` に倒す
- `parent_turn` — サブエージェントを起動した親ターンが特定できない場合は `null`

いずれも §11 の実測で確定させ、テストで判定を明示的に検証する。

## 8. phase 写像

| skill | phase |
|---|---|
| `brainstorming` | `brainstorming` |
| `writing-plans` | `planning` |
| `test-driven-development` / `executing-plans` / `subagent-driven-development` | `implementing` |
| `systematic-debugging` | `debugging` |
| `requesting-code-review` / `receiving-code-review` / `verification-before-completion` | `reviewing` |
| `finishing-a-development-branch` | `finishing` |
| 上記以外、および skill 無し | `unknown` |

写像はコード内の 1 つの辞書に集約し、未知の skill 名は `unknown` に落とす。
skill が増えたときに辞書へ 1 行足すだけで済む形にする。

## 9. 状態管理と増分読み

```
~/.claude/superpowers/telemetry/.state/<session_id>.json

{
  "line": 412,
  "turn": 7,
  "active_skill": "superpowers:test-driven-development",
  "active_skill_rev": "a3f19c04",
  "invoked_by": "model",
  "last_assistant_ts": "2026-08-21T04:12:33.412Z"
}
```

transcript は追記専用なので、処理済み行数を保持すれば増分で読める。
毎ターン全文を読むとセッション長に対して O(n^2) になるため、これは必須である。

`active_skill` を持ち越すことで、skill がターンをまたいで継続していても正しく引き継がれる。

**状態ファイルの掃除** — 実行時に、更新から 30 日以上経過した `.state/*.json` を削除する。

**セッション ID が変わる場合**(`/clear` など)は新しい状態ファイルになり、
ターン番号は 1 から数え直す。

## 10. 保存先とローテーション

```
~/.claude/superpowers/telemetry/
  2026-08.jsonl
  2026-09.jsonl
  errors.log
  .state/<session_id>.json
```

全プロジェクトが 1 ファイルに混在し、`project` フィールドで区別する。
skill の改修判断には複数プロジェクトを横断した比較が要るため、この配置が要件に合う。

月次ローテーションは追記時のファイル名決定のみで行う(別プロセスは不要)。
保持期間の自動削除は行わない。不要になったら手で消す。

## 11. 失敗時の挙動

**このフックはセッションを止めてはならない。**

- ラッパは **stdout に一切出力せず、常に `exit 0`** する。
  `Stop` フックの stdout は harness に解釈されうるため、空にする
- `python3` が無い / `transcript_path` が読めない / 行が壊れている → 静かにスキップ
- 例外は全て捕捉し、`errors.log` に 1 行だけ記録する
  (`ts`, `session`, 例外の型とメッセージ)。そこも失敗したら握り潰す
- `hooks.json` で `timeout: 10` を設定する

### 書き込み競合

月次 1 ファイルに複数セッション・サブエージェントが同時追記する。

- `open(path, 'a')` + `fcntl.flock(LOCK_EX)` で排他し、1 行を 1 回の `write` で出す
- ロックが取れなければ 200ms 間隔で 3 回リトライ、それでも駄目なら `errors.log` に
  落として諦める。**データ 1 行より、セッションを止めないことを優先する**

## 12. プライバシー

**プロンプト本文・ファイル内容・ツール引数は一切記録しない。**

記録するのは skill 名、ツール名と回数、数値、プロジェクト名、ブランチ名のみ。
保存先はローカルのみで、送信先は存在しない。

## 13. ファイル構成

```
hooks/custom/telemetry           新規  bash 薄ラッパ (chmod +x)
hooks/custom/telemetry.py        新規  python3 標準ライブラリのみ
hooks/hooks.json                 +2 ブロック  ← 唯一の共有コンフリクト面
tests/hooks/test-telemetry.sh    新規
tests/hooks/fixtures/            新規  合成トランスクリプト
docs/fork/telemetry.md           新規  スキーマと jq レシピ
docs/fork/DIVERGENCE.md          Custom hooks 表に 1 行追加
```

`hooks/hooks.json` への追記は次の 2 ブロックのみ。
このファイルは upstream との唯一の共有コンフリクト面であり、変更を最小に保つ。

```json
"Stop": [
  { "hooks": [ { "type": "command",
      "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/custom/telemetry\"",
      "shell": "bash", "async": true, "timeout": 10 } ] }
],
"SubagentStop": [
  { "hooks": [ { "type": "command",
      "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/custom/telemetry\"",
      "shell": "bash", "async": true, "timeout": 10 } ] }
]
```

`hooks/hooks-cursor.json` は変更しない。このフックは Claude Code の
transcript 形式に依存しており、Cursor では動かない。

## 14. テスト計画

`tests/hooks/test-telemetry.sh` に、合成トランスクリプトの fixture を食わせて
出力 JSONL を検証するテストを置く。既存の `tests/hooks/test-session-start.sh` の
構成(mktemp した隔離 HOME、pass/fail カウンタ、`trap cleanup EXIT`)に倣う。

検証項目:

1. 1 ターン 1 skill の基本形が 1 行として出る
2. **1 ターン内で `test-driven-development` から `requesting-code-review` に
   切り替わると 2 行に分かれ、時間とトークンが分離される**(中核要件)
3. skill 無しの区間が `skill: null` として残る
4. `wait_ms` が `seq: 0` にのみ載り、他は 0
5. 同じ transcript を 2 回処理しても重複行が出ない(増分読み)
6. active skill がターンをまたいで引き継がれる
7. 壊れた JSON 行が混ざってもクラッシュせず、他の行は処理される
8. `python3` が無い環境で `exit 0` かつ stdout が空
9. `transcript_path` が存在しない場合も `exit 0` かつ stdout が空
10. `invoked_by` が `"user"` / `"model"` / `"session-start"` を正しく判定する
11. `tool_errors` が `is_error` の `tool_result` を数える
12. `tokens.cache_create_5m` と `cache_create_1h` が分離して集計される

## 15. 未検証リスクと実装順

実装の最初のステップで次を実測し、結果に応じて設計を確定させる。

1. **サブエージェントの transcript の所在** — `isSidechain: true` の行が親ファイルに
   混ざるのか、別ファイルになるのか。現時点でこのマシンにサブエージェント実行の
   実績が無く未確認。実際にサブエージェントを 1 回走らせて確認する
2. **`Stop` 発火時点で最終 assistant 行が書き込み済みか** — 未書き込みなら記録が
   1 ターン遅れる。増分読み設計のため次ターンで自動的に拾えるが、実測して挙動を記録する
3. **`async: true` が `Stop` / `SubagentStop` で尊重されるか** — 尊重されない場合は
   同期実行になる。処理は数十ミリ秒で終わる想定だが、実測する
4. **`invoked_by` の判定手段** — スラッシュコマンド起動が transcript にどう残るかを
   実測し、判定ロジックを確定させる
5. **コンパクション境界の表現** — `/compact` および自動コンパクションが transcript に
   どの行として残るかを実測する(候補: `type:"summary"` 行、`isCompactSummary` フラグ、
   SessionStart の `source == "compact"`)。判定できない場合、`compacted` は
   常に `false` を入れる。**フィールド自体は残す** — 後から足すとスキーマ変更になるため

実装順:

1. 上記 4 点の実測(コードは書かず、実データの観察のみ)
2. `telemetry.py` の中核(セグメント分割と集計)を TDD で実装
3. bash ラッパと失敗時の握り潰し
4. `hooks.json` 登録と実セッションでの動作確認
5. `docs/fork/telemetry.md` と `DIVERGENCE.md` の行追加

### 実測結果 (2026-08-21)

1. **サブエージェントの transcript** — 本タスク自身がサブエージェントとして実行された
   状態を観察して確定した。`isSidechain: true` の行は親トップレベルの
   `<session-id>.jsonl` には一切混ざらない(`~/.claude/projects/*/*.jsonl` を全走査
   しても isSidechain 行はゼロ件)。実際には親セッションのディレクトリ配下に
   `<parent-session-id>/subagents/agent-<agentId>.jsonl` という**専用ファイル**が
   作られ、そのファイルの全行に `isSidechain: true` が付く。同じディレクトリに
   `agent-<agentId>.meta.json` も生成され、`agentType`(例:
   `"general-purpose"`)・`description`・`toolUseId`・`spawnDepth`・`model` を持つ。
   `toolUseId` は親トランスクリプト中の `tool_use`(`name:"Agent"`)の `id` と一致し、
   その `tool_use` の `input.subagent_type` に `subagent_type` の実値が直接入っている
   (本タスクでは `"general-purpose"`)。親ターンは、この `tool_use` を含む
   assistant 行を親トランスクリプト上で特定し、そこから遡ってターン開始 `user` 行を
   探すことで求まる(実測: `toolUseId` から該当する `tool_use`/`tool_result`
   ペアを親トランスクリプト中に特定できた)。サブエージェント側トランスクリプトの
   先頭行は `parentUuid: null` で始まり、親トランスクリプトの uuid 連鎖には
   繋がらない — 親ターンの特定は uuid チェーンではなく `toolUseId` の突合せで行う
   必要がある。また、このサブエージェント用ファイルは `SubagentStop` を待たず
   作業中も逐次追記されることを確認した(観測中に 17 行 → 24 行 → 56 行と増加、
   同時に親トップレベルファイルの行数は不変)。
2. **`Stop` 発火時点の最終 assistant 行** — 完了済みセッション 2 件
   (`cbc6a9f5-...`, `b47b5a3d-...`)と、本セッションの直前ターンの計 3 件で、
   最後の assistant 行の `stop_reason` はいずれも `"end_turn"` だった。もう 1 件
   (`09a7f426-...`)は assistant 行が 1 つも無いセッション(`/clear` 直後に
   終了したものと見られる)で対象外。結論: 完了したターンの最終 assistant 行は
   `Stop` 発火時点で書き込み済みであり、`stop_reason != "tool_use"` を
   セグメント終端の判定に使ってよい。
3. **スラッシュコマンドの痕跡** — `type:"user"` 行の content に
   `<command-name>/xxx</command-name>` `<command-message>...</command-message>`
   `<command-args>...</command-args>` という XML ライクなブロックがそのまま
   書き込まれることを実測で確認した(`/clear`, `/plugin`, `/login`,
   `/reload-plugins` の実例で確認。`isMeta` は立たず通常の user 行として記録される)。
   `/brainstorming` など skill 起動コマンドの実例は今回のデータには存在しなかったが、
   機構自体は確認済みであり、`invoked_by` の判定はターン先頭 user 行の text が
   `<command-name>` で始まるかどうかで `"user"` / それ以外は `"model"` と
   判定できる。
4. **コンパクション境界** — 確定できず。親トランスクリプト 4 件とサブエージェント
   トランスクリプト 1 件の全行を走査したが、`isCompactSummary`、
   `type:"summary"`、`type:"compact-boundary"` はいずれもゼロ件だった。
   `SessionStart` の attachment 行は `hookName` に `"SessionStart:startup"` と
   `"SessionStart:clear"` のみが出現し、`"SessionStart:compact"` は一度も
   観測されなかった — このマシン上のどのセッションでもコンパクションが
   発生していないためで、コンパクションが起きた際の表現が無いことの証明では
   ない。フォールバック: `compacted` は常に `false` を入れる(フィールドは残す)。
5. **`async` の扱い** — 確定できず。インストール済みプラグインは
   `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7` と
   自分自身の `~/.claude/plugins/cache/superpowers-tackyto/superpowers/1.0.0`
   の 2 つのみで、両方とも `hooks.json` は `SessionStart` しか登録しておらず、
   `Stop` / `SubagentStop` を使っている実例は存在しない。両方とも
   `"async": false` のみが使われており(`"async": true` の実例はゼロ)、
   このリポジトリの `hooks/custom/README.md` のテンプレートも
   `"async": false` をデフォルトにしている。Claude Code の changelog
   (`~/.claude/cache/changelog.md`)は非同期フックが一般機能として存在すること
   (例: "async PostToolUse hooks", "async hook output", "pending async
   hooks" 等の記述)を示すが、`Stop` / `SubagentStop` に限定した記述は無い。
   フォールバック: Task 7 は `async` に頼らず登録する(`async: true` は落とし、
   `async: false` にするか省略する)。

## 16. 集計レシピ

`docs/fork/telemetry.md` に置く jq ワンライナー(抜粋)。

```bash
cd ~/.claude/superpowers/telemetry

# skill 別の合計実行時間と出力トークン
cat 2026-*.jsonl | jq -s '
  group_by(.skill)[] |
  { skill: .[0].skill,
    segments: length,
    exec_min: (map(.exec_ms) | add / 60000 | floor),
    out: (map(.tokens.out) | add),
    errors: (map(.tool_errors) | add) }'

# skill が自発的に発火した割合(呼ばれない skill を探す)
cat 2026-*.jsonl | jq -s '
  map(select(.skill != null)) | group_by(.skill)[] |
  { skill: .[0].skill,
    by_model: (map(select(.invoked_by == "model")) | length),
    by_user:  (map(select(.invoked_by == "user"))  | length) }'

# skill の版ごとの比較(改修の前後)
cat 2026-*.jsonl | jq -s '
  map(select(.skill == "superpowers:brainstorming")) |
  group_by(.skill_rev)[] |
  { rev: .[0].skill_rev,
    n: length,
    avg_exec_s: (map(.exec_ms) | add / length / 1000 | floor),
    avg_out: (map(.tokens.out) | add / length | floor) }'

# プロジェクト別のトークン
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
