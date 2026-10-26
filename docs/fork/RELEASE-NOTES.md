# フォークのリリースノート

このフォーク([tackyto/superpowers](https://github.com/tackyto/superpowers))自身の変更履歴。
upstream のリリースノートは [../../RELEASE-NOTES.md](../../RELEASE-NOTES.md) にそのまま残してある
— 別ファイルにしているのは、upstream が毎リリースそちらの先頭に追記するためで、同じファイルを
使うと同期のたびにコンフリクトする。

バージョンは upstream とは独立した SemVer で、upstream `v6.3.0` を起点に `1.0.0` から始まる。
詳しくは [FORK-POLICY.md](FORK-POLICY.md) を見ること。

## v1.4.0 (2026-10-27)

upstream `v7.0.1` の取り込み。フォーク独自の変更は、そのマージを成立させるためのものだけ。

### upstream から入ったもの

- **`brainstorming` の再調整。** v7.0.0 の作り直しで定型的になっていた質問を改善した。
  既存プロジェクトや指定された spec・計画・ファイルを最初に読み、そこで答えが出ていることは
  尋ねない。依頼内容がはっきりしていれば、調べた内容と合わせて言い返し、残る一点だけを尋ねる。
  「質問を飛ばすか」の提案は、ユーザーが名指しで呼んだときには出さない。2〜3 案を示して
  推奨を付け、選んでもらってから設計ドキュメントを書き、承認まで実装しない。
- **長いスキルがコンパクション後も欠けにくくなった。** Claude Code はコンパクション後に
  各スキルを 20,000 文字で切って再添付するため、それ以降の指示が失われていた。
  `subagent-driven-development` は fix loop・final review・報告の扱い・再開・preflight・
  batching・cannot-verify を、`writing-skills` は補助ドキュメントを `references/` に分け、
  必要な段階でディスクから読む。`executing-plans` は重複していた Example Workflow を削除。
- **`tests/skill-size/test-skill-size.sh`(新規)** — `SKILL.md` が 20,000 バイトに達すると失敗する。
- `diagnosing-superpowers` が下書きする issue に「誰が提出するか」と人間が書く要約の欄が増え、
  要約がプレースホルダのままでは提出しない。

### フォーク側の対応

- **`AGENTS.md`・`README.md`(Contributing)・PR テンプレートは ours を維持した。** upstream の
  変更(#2569)は obra/superpowers への貢献規約の強化で、このフォークには適用されない。
- issue テンプレートは upstream 版のまま更新を受け入れた(フォークでは未改変)。
- upstream が `docs/superpowers/plans/` の過去の計画を削除した。フォーク独自の計画
  (`2026-08-21-session-telemetry-hook.md`)は残っている。

## v1.3.0 (2026-10-13)

upstream `v7.0.0` の取り込み。

### upstream から入ったもの

- **`brainstorming` が作り直された。** 何を作りたいか・なぜかを、具体的な場面を尋ねる質問で
  引き出し、理解した内容を数百語で言い返して訂正を受ける。推測は推測と明示する。理解が固まって
  から作業の大きさを判断し、すぐ済む作業はそのまま実施、小さな変更はチャットで合意、
  プロジェクト規模なら設計ドキュメントを書く。spec-document reviewer は廃止され、新しい
  サブエージェントが「実装する人」として設計を読み、残る疑問を挙げる builder check に
  置き換わった。プラットフォームや言語などの選択をユーザー自身が決めたいかも確認する。
- **新ハーネス: Antigravity のネイティブ plugin manifest(`.antigravity-plugin/plugin.json`)。**
  Antigravity には session-start フックが無く、`using-superpowers` の description によって
  起動される。
- **SessionStart フックが、壊れた・空の `PATH` でも動く**(anthropics/claude-code#43127)。
- `sdd-workspace` がリポジトリ自身の `.superpowers/sdd/.gitignore` を上書きしなくなった。
  `task-done` が出力なしで成功したテストも記録する。`requesting-code-review` の例が
  スキル引数で壊れなくなった。`systematic-debugging` の例が秘密の値を出力しなくなった。

### フォーク側の対応

- **`hooks/run-hook.cmd` は upstream 版をほぼそのまま採用した。** upstream は v1.1.0 で
  フォークが直したのと同じ 2 つのバグ(WSL ランチャーの誤選択、終了コードの消失)を独立に
  修正した。upstream 版は WSL ランチャーをディレクトリで除外して**起動すらしない**。
  フォーク版の `uname -o` による判定は、判定のためにランチャーを一度起動していた。
  さらに upstream 版はカレントディレクトリに置かれた `where.bat` や `bash.cmd` を実行しない
  (フォーク版は実行し得た)。フォーク独自の「`git` の場所から bash を導出する」段だけを、
  upstream と同じ安全な書き方で足した。Git for Windows は `<root>\cmd` しか `PATH` に
  入れないので、標準以外の場所にインストールされた Git の bash は、この段が無いと見つからない。
- Windows 実機で検証済み。`verify-windows-dispatch.py` は全項目合格。upstream の
  `test-run-hook-cmd-windows.sh` は `café-bin` の 1 件だけ失敗するが、これは upstream の
  未改変ファイルでも同様に失敗する(コードページ 932 が原因と推測、未確認)。WindowsApps の
  ケースは、`%TEMP%` が 8.3 短縮名だと誤って失敗するので、`TMPDIR` を長い形式にして実行する。
- `.antigravity-plugin/plugin.json` が upstream 所有のまま新規追加されたので、フォーク所有に
  変更した。移植ガイドに増えた `agy plugin install` の URL も、フォークに向け直した。
- **バージョンを持つ manifest が 11 から 12 に増えた**(`.antigravity-plugin/plugin.json`)。

## v1.2.0 (2026-09-29)

upstream `v6.4.1` / `v6.4.2` の取り込み。フォーク独自の変更は、そのマージを成立させるための
ものだけ。

### upstream から入ったもの

- **`diagnosing-superpowers`(新スキル)** — セッションが失敗したとき
  「このセッションで superpowers の何が悪かったか調べて」と頼むと、ディスク上のトランスクリプトを
  読み、全所見に `path:line` の根拠を付けて報告する。スクラブ済みバンドルや issue 下書きの生成も
  できる。過去のセッションも id 指定で調べられる。
- **`executing-plans` が Native(インライン)実行として作り直された。** 従来の 64 行の
  スタブは実測でプラグイン無しと同等だった。現在は SDD と同じワークスペース・台帳・停止ルールの
  下でセッション自身が全タスクを実装し、最後に最上位モデルで全ブランチレビューを 1 回だけ回す。
  **注意: 数タスクごとのチェックインは無くなった。** プラン全体を走り切ってから最後に 1 回。
- **`writing-plans` が軽量化された。** プランは「コードの書き写し」ではなく「決定の記録」に
  再定義。テストステップはテスト名とアサーション、コードステップは正確なシグネチャと仕様上の値。
  upstream の再現実験で所要時間 1/4・トークン約 1/3、欠陥検出は従来と同等(9/9)。
- `brainstorming` は機能提案の前に動機を確認する。`test-driven-development` は green の定義を
  プロジェクトのテストスイート全体に。コードレビューは仕様に無い挙動を「妥当なユーザーの期待」で
  判定する。
- **新ハーネス: OpenCode 2.0.4+、Muse、Qwen Code。**

### フォーク側の対応

- **`CLAUDE.md` は upstream が削除したが、こちらは維持する。** upstream の理由は
  「Claude Code は `CLAUDE.md` が無いときだけ `AGENTS.md` を読むので、1 行のポインタを残すと
  本体のガイドラインが隠れる」。このフォークは構成が逆で、`CLAUDE.md` がフォークポリシー本体、
  `AGENTS.md` がポインタなので、同じ理由が維持する側に働く。以後の同期では content ではなく
  modify/delete コンフリクトとして出る。
- **`AGENTS.md` は upstream と収束した。** v1.1.0 でシンボリックリンクをやめたのと同じ修正を
  upstream も #2317 で入れた(Muse のインストーラがシンボリックリンクを拒否するため)。ただし
  upstream はそのファイルを contributor guidelines 本体にしたので、中身は引き続きこちらが勝つ。
- **新しいインストール経路を 4 箇所フォークに向け直した** — OpenCode V2 の `plugins` キー、
  `qwen extensions install`、Muse の `git clone`。いずれも**コンフリクトせず無言で auto-merge
  され**、upstream の URL を持ち込んでいた。同期後の grep 手順を
  [DIVERGENCE.md](DIVERGENCE.md) に追加した。
- `.muse-plugin/marketplace.json` が upstream 所有のまま新規追加されたので、
  `.claude-plugin/marketplace.json` と同じくフォーク所有に変更した。
- **バージョンを持つ manifest が 9 つから 11 に増えた**(`.muse-plugin/` の 2 つ)。
  対象は `.version-bump.json` の宣言が正で、`scripts/bump-version.sh` がそれを読む。

## v1.1.0 (2026-08-27)

### Windows で使えるようになった

1.0.0 の時点では、このフォークは Windows で**無言で何もしなかった**。原因は一つではなく、
それぞれ別の層にあった。

- **セッションテレメトリが Windows で動く。** `store.py` が読み込み時に `fcntl` を
  import していたため、Windows では `telemetry.py` の catch-all より前に失敗し、
  `errors.log` にすら理由が残らなかった。`fcntl` が無い環境では `msvcrt` でロックする
  ようにした。依存は増えていない。なお `O_APPEND` の単一 write は Windows では
  **アトミックではない**(8KB 付近から再現性をもって裂ける)ので、ロックを外す選択肢は無い。
- **フックが実行されるようになった。** `run-hook.cmd` は `where bash` が最初に見つけた
  ものを使っていた。WSL が入っているマシンではそれが `C:\Windows\System32\bash.exe`、
  つまり WSL のランチャで、Windows のパスを開けない。`git` の場所から bash を導出する
  経路を先に置き、PATH 上の bash は `uname -o` が `Msys` / `Cygwin` を返したときだけ
  使うようにした。
- **フックの終了コードが届くようになった。** 括弧付きの `if` ブロック内の
  `exit /b %ERRORLEVEL%` はパース時に展開されるため、Windows ではどのフックの終了コードも
  harness に届いていなかった(実測: 3 で終了したフックが 0 と報告される)。
- **ペイロードが UTF-8 として読まれる。** `sys.stdin.read()` が Python の既定
  エンコーディングを使うため、日本語 Windows(cp932)では非 ASCII を含むペイロードが
  壊れることがあった。cp932 の lead byte 60 種のうち 52 種が直後の `\` を飲み込むので、
  `\"` が `"` になって JSON がそこで終わる。実セッションの `errors.log` で見つかった。

### 保守も Windows からできるようになった

- **`scripts/bump-version.sh` が Windows で動く。** ネイティブの `jq.exe` は標準出力を
  テキストモードで開くため全行が CRLF で終わる。フィールド名が `version\r` になって
  yq のキー参照が外れるだけでなく、JSON manifest 8 つが CRLF に書き換わり、`--audit` は
  何にも当たらないまま「All clear」と報告していた。jq の出力を消費する 4 箇所で CR を
  落とすようにした。
- **`AGENTS.md` がネイティブ clone で壊れない。** シンボリックリンクをやめて実ファイルに
  した。Windows の git は Developer Mode 無しではシンボリックリンクを再現できず、既定の
  clone では 9 バイトのプレースホルダになり、`core.symlinks=true` を強制するとファイル自体が
  作られない。どちらも警告は出ない。
- 前提条件は [windows-maintenance.md](windows-maintenance.md) に記録した。

### セッションテレメトリ(新規)

`Stop` / `SubagentStop` で、セッションを (ターン × スキル) のセグメントに分けて
`~/.claude/superpowers/telemetry/YYYY-MM.jsonl` に記録する。Python 3 標準ライブラリのみで、
依存は増えていない。スキーマと限界は [telemetry.md](telemetry.md)。

### フォークの運用

- `scripts/sync-upstream.sh` — upstream の取り込み用
- インストール手順をすべてこのフォークに向けた。Contributing はフォーク自身の手順に置き換え、
  「upstream に PR を出さない」を明示した
- [DIVERGENCE.md](DIVERGENCE.md) — upstream と意図的に異なる箇所の台帳

## v1.0.0 (2026-08-21)

upstream `v6.3.0`(`b36e082`)からのフォーク起点。バージョンを独立させ、9 つの manifest の
所有者情報をこのフォークに変更しただけで、機能の変更は無い。
