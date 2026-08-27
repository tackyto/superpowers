# フォークのリリースノート

このフォーク([tackyto/superpowers](https://github.com/tackyto/superpowers))自身の変更履歴。
upstream のリリースノートは [../../RELEASE-NOTES.md](../../RELEASE-NOTES.md) にそのまま残してある
— 別ファイルにしているのは、upstream が毎リリースそちらの先頭に追記するためで、同じファイルを
使うと同期のたびにコンフリクトする。

バージョンは upstream とは独立した SemVer で、upstream `v6.3.0` を起点に `1.0.0` から始まる。
詳しくは [FORK-POLICY.md](FORK-POLICY.md) を見ること。

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
