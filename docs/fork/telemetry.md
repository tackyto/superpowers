# セッションテレメトリ

このフォークは、セッションとサブエージェントの活動を
`~/.claude/superpowers/telemetry/YYYY-MM.jsonl` に記録する。

設計の経緯は
[docs/superpowers/specs/2026-08-21-session-telemetry-hook-design.md](../superpowers/specs/2026-08-21-session-telemetry-hook-design.md)
にある。

## 有効にする

フック自体はこのリポジトリの `hooks/hooks.json` に登録済みだが、実際に動くのは
`~/.claude/plugins/cache/` 配下にインストールされているプラグインのコピーの方であり、
これはこのリポジトリとは別物である。したがって、**プラグインを再インストールまたは
更新し、新しいセッションを開始するまでは何も記録されない。** インストール手順は
[README.md](../../README.md) の Claude Code 向けの節(`/plugin marketplace add` /
`/plugin install`)を使う。更新の具体的な手順はハーネス依存で、README.md の
「Updating」節が言うとおり自動のこともある — ここではコマンドを新しく決め打ちしない。

動いているかどうかは次で確認する。

- `~/.claude/superpowers/telemetry/YYYY-MM.jsonl` がターンの終わりごとに増えていく
- 増えない場合は `~/.claude/superpowers/telemetry/errors.log` を見る。理由が
  1 行ずつ入っている(詳しくは末尾の「動かないときは」)

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

### ターンの境界

`type: "user"` のレコードは、それだけでは「実際に人間が打ったプロンプト」とは
限らない。次の判定で、実プロンプトだけをターン開始として数える。

- `tool_result` ブロックを含むレコード(同一ターン内の継続) → 数えない
- `isMeta` が真のレコード(システムによる注入) → 数えない
- `<local-command-stdout>` で始まるレコード → 数えない。これはスラッシュ
  コマンドの**出力**がそのまま会話に戻されたものであり、人間の入力ではない。
  これを数えるとターンを水増ししてしまう
- `<command-name>` を含むレコード → **数える**。これは人間がスラッシュ
  コマンドを打った記録そのものであり、`invoked_by` の判定([限界](#読むときに知っておくべき限界)参照)もこの行に依っている

### サブエージェント

サブエージェントのトランスクリプトは、親とは別ファイル
`<session-id>/subagents/agent-<id>.jsonl` に書かれるが、中身のレコードは
**親と同じ `sessionId`** を持つ。この違いを `agent` フィールドで区別し、
サブエージェント由来の行は `agent: "subagent"` になる。

`subagent_type` はこのトランスクリプト自身には入っていない。同じディレクトリの
`agent-<id>.meta.json` の `agentType` フィールドから読み、`general-purpose` の
ような実際の値が入るのはそのため。

## 記録されないもの

**プロンプト本文、ファイルの内容、ツールの引数は記録しない。** 残るのは
skill 名、ツール名と回数、数値、プロジェクト名、ブランチ名だけ。送信先は無い。

## 読むときに知っておくべき限界

この数値は skill を改修すべきかどうかの判断材料であり、**何が数字から
抜け落ちているかを知らずに読むと、自信満々な誤った結論に至る。** 以下を
先に読むこと。

1. **`turn` はエージェントのターンを数えるもので、会話としての往復を
   数えるものではない。** `<local-command-stdout>`(コマンド出力の
   エコー)を除外したことで実態にかなり近づいたが、人間が打った
   スラッシュコマンドはアシスタントの作業を何も生まなくても 1 ターンとして
   数えられる
2. **skill のネストは表現されない。** `brainstorming` が `writing-plans` を
   呼ぶと、以後は `writing-plans` が有効なままになる。skill の *終了* を示す
   信号がトランスクリプトに無いため、親への復帰は観測できない
3. **権限プロンプトの待ち時間は `exec_ms` に含まれる。** `AskUserQuestion` と
   `ExitPlanMode` の回答待ちは `wait_ms` に分離されるが、権限確認の待ちは
   トランスクリプトに行として残らないため分離できない
4. **`invoked_by` と `parent_turn` はベストエフォート。** 判定できない場合は
   それぞれ `"model"` と `null` に倒れる
5. **`cache_read` は請求上の実数。** リクエストごとに課金されるため、
   合算すると「同じコンテキストを何度も読んだ」分が積み上がる。これは
   誤りではなく、実際にそう課金される
6. **ロック取得に失敗すると、失われるのは 1 行ではなくバッチ全体。** 同じ
   月次ファイルに複数のセッション・サブエージェントが同時に追記するため、
   書き込みは排他ロックを取ってからまとめて 1 回で行う。ロックが取れなければ
   プロセスごとに間隔を変えながら 12 回までリトライし(最大で約 1 秒)、
   それでも取れなければ `errors.log` に記録して諦める。このとき失われるのは
   そのフック呼び出しが溜め込んでいたセグメント全部であり、1 行だけではない。
   これは意図的な設計であり、バッチを失う代償はセッションを止める代償より
   小さいと判断している
7. **`compacted` は常に `false`。** このフックを作ったマシン上ではコンパクション
   が一度も観測できず、判定ロジックを実装できなかった。フィールド自体は
   残してある — 後から判定を足すときにスキーマ変更にならないようにするため

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

上記 5 本はすべて、このフックで実際に生成した JSONL に対して実行して確認済み。

## 状態ファイル

増分読みの読み込み位置は、次のパスに 1 ファイルずつ保持する。

```
~/.claude/superpowers/telemetry/.state/<session-id>-<transcript_path のハッシュ>.json
```

キーは **セッション ID 単体ではなく、トランスクリプトファイル単位**。
サブエージェントのトランスクリプトは親と同じ `sessionId` を持つため
([サブエージェント](#サブエージェント)参照)、もしセッション ID だけを
キーにすると親とサブエージェントが読み込み位置を共有してしまい、互いの
レコードを読み飛ばす。ファイル単位でキーを分けているのはこれを避けるため。

この設計の副作用として、1 つのセッション内で並行して動いた複数のサブエージェントは、
それぞれ自分の `turn` 番号を 1 から数え始める。したがって `turn` の値は
セッション内で一意ではなく、`(session, agent, turn)` で初めて一意になる。

## 止めかた・消しかた

`hooks/hooks.json` から `Stop` と `SubagentStop` のブロックを消せば止まる。
記録済みのデータは `rm -rf ~/.claude/superpowers/telemetry/` で消える。

出力先は `SUPERPOWERS_TELEMETRY_DIR` で変更できる。

## 動かないときは

`~/.claude/superpowers/telemetry/errors.log` に理由が 1 行ずつ入る。
ファイルが無く、JSONL も増えていない場合は、まず[有効にする](#有効にする)の
とおりプラグインが再インストールされ新しいセッションが始まっているかを確認し、
次に `python3` が PATH にあるか確認する(無い場合、フックは何もせずに終了する)。
