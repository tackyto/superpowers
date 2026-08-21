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

## 対応環境

**Linux と macOS のみ。WSL はこれに含まれる。Windows のネイティブ環境では動作しない。**

Windows で動かない理由は 2 つあり、どちらも未対応である。

1. **`store.py` が `fcntl` を import している。** これは UNIX 専用モジュールで、
   Windows の Python には存在しない。実測(Windows 11 / pyenv-win の Python 3.10.5):
   `json` `os` `hashlib` `datetime` `time` `re` はすべて import できるが、
   `fcntl` だけが `ModuleNotFoundError` になる。
2. **フックが `hooks/run-hook.cmd` を経由していない。** upstream がこの polyglot
   ラッパを用意しているのは、拡張子なしのフックスクリプトを Windows で動かすため
   である。このフックは `hooks/custom/README.md` の「Windows 対応が実際に必要に
   なるまでは直接呼ぶ」という方針に従い、直接呼ぶ形で登録されている。

**この失敗は無言である。** `telemetry.py` はモジュール読み込みの時点で `store` を
import するため、`fcntl` の不在は `main()` の例外捕捉に到達する *前* に起きる。
つまり `errors.log` にすら 1 行も残らない。Windows でテレメトリが空のままなのを
見つけたときは、設定を疑う前にここを思い出すこと。

対応するなら、`fcntl` が使えない環境ではロックを諦めて追記のみにフォールバックし
(`O_APPEND` での単一 `write` は実用上アトミックである)、フック登録を
`run-hook.cmd` 経由に変えることになる。

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
  "agent": "main", "agent_id": "3f9a21bc", "subagent_type": null, "parent_turn": null,
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
4. **`invoked_by` はベストエフォート。** 判定できない場合は `"model"` に倒れる。
   **`parent_turn` は常に `null` である。** ベストエフォートですらなく、判定
   ロジック自体が実装されていない。したがって現状、サブエージェントの行を
   それを起動した親ターンに結びつけることはできない
5. **`cache_read` は請求上の実数。** リクエストごとに課金されるため、
   合算すると「同じコンテキストを何度も読んだ」分が積み上がる。これは
   誤りではなく、実際にそう課金される
6. **ロック取得に失敗しても、失われるのはメインセッションでは一時的、
   サブエージェントでは恒久的。** 読み込み位置の保存は `append_records` の
   *後* に行われるため、書き込みが失敗すると位置は進まない。メインセッションは
   ターン終了ごとに `Stop` が発火するため、失敗した分は次のターン終了時に
   同じ行から読み直され、重複無く回収される(実測済み: 出力先を書き込み不可に
   して失敗させ、書き込み可能に戻して再実行すると失敗分がすべて回収され、
   3 回目の実行では何も増えない)。一方 `SubagentStop` は 1 回しか発火しない
   ため、そこで失敗したサブエージェントの行はやり直す機会が無く恒久的に失われる
   (月をまたぐ場合はロックも月ごとなので、失われるとしてもその月の分だけである)。
   それでも素早く諦めるのは、失う代償がセッションを止める代償より小さいと
   判断しているため。なお、月をまたぐバッチで一方の月のロックだけ失敗した場合、
   成功した月の行はやり直しで再び書き込まれ重複しうるが、その重複行は元の行と
   バイト単位で同一なので `sort -u` や `jq -s unique` で完全に除去できる
7. **`compacted` は常に `false`。** このフックを作ったマシン上ではコンパクション
   が一度も観測できず、判定ロジックを実装できなかった。フィールド自体は
   残してある — 後から判定を足すときにスキーマ変更にならないようにするため
8. **`project` は `.git` を含むディレクトリの basename である。** git worktree
   で作業すると、worktree のディレクトリ名が本体のリポジトリ名と異なる限り、
   `group_by(.project)` では別プロジェクトとして現れる

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
セッション内で一意ではなく、`(session, agent_id, turn, seq)` で初めて一意になる。
並行するサブエージェントは親と同じ `session` を持ち、`agent` もどちらも
`"subagent"` なので、両者を区別できるのは `agent_id`(transcript パスの
ハッシュ)だけである。

## 止めかた・消しかた

`hooks/hooks.json` から `Stop` と `SubagentStop` のブロックを消せば止まる。
記録済みのデータは `rm -rf ~/.claude/superpowers/telemetry/` で消える。

出力先は `SUPERPOWERS_TELEMETRY_DIR` で変更できる。

## 動かないときは

`~/.claude/superpowers/telemetry/errors.log` に理由が 1 行ずつ入る。
ファイルが無く、JSONL も増えていない場合は、まず[対応環境](#対応環境)を確認する
— Windows のネイティブ環境では何も記録されず、`errors.log` すら作られない。
次に[有効にする](#有効にする)のとおりプラグインが再インストールされ新しい
セッションが始まっているかを確認し、最後に `python3` が PATH にあるか確認する
(無い場合、フックは何もせずに終了する)。
