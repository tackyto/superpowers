# Windows Git Bash からフォークを保守する

このフォークを Windows で**保守**する — バージョンを上げる、リリースを切る — 場合の
前提条件と、そのために入れた修正をまとめる。プラグインを**使う**だけなら何も要らない。
インストール手順は [README.md](../../README.md) を見ること。

いまこのドキュメントが扱うのはバージョン更新のツールチェーンだけである。他の保守
スクリプトは、Windows で実際に動かして確かめられた時点で追記する。

## 必要なもの

| ツール | 使う場面 | 備考 |
|---|---|---|
| Git Bash | すべてのスクリプト | Git for Windows 同梱 |
| `jq` | `.version-bump.json` と 8 つの JSON manifest | |
| `yq` | `.hermes-plugin/plugin.yaml` | **mikefarah/yq (Go 実装)**。python の `yq` では動かない |

`scripts/bump-version.sh` が揃える 9 つの manifest のうち、`yq` を使うのは
`.hermes-plugin/plugin.yaml` の 1 つだけである。残り 8 つは JSON で、`jq` が扱う。

## `yq` は mikefarah 版でなければならない

`yq` という名前のツールは 2 つある。PyPI の `yq`(kislyuk/yq)は YAML を JSON に変換して
`jq` に渡すラッパで、`scripts/bump-version.sh` が使うフィルタを解釈できない。

```console
$ jq -n 'strenv("FIELD")'
jq: error: strenv/1 is not defined at <top-level>, line 1:

$ jq -n '1 | tag'
jq: error: tag/0 is not defined at <top-level>, line 1:
```

`strenv()` も `tag` も mikefarah/yq 固有で、`jq` には無い。前者はフィールド名と値を
環境変数経由で安全に渡すため、後者は `version:` が引用符付きの文字列であることを
確かめるために使われている(`select(tag == "!!str")`)。python 版ではどちらも通らない。

## 入れる、確かめる

```console
> winget install MikeFarah.yq
```

winget は PATH を書き換えるので、**新しいシェルを開かないと `yq` は見つからない**。
入っているものが mikefarah 版かどうかは、バージョン表示に出る URL で判別する。

```console
$ yq --version
yq (https://github.com/mikefarah/yq/) version v4.53.6
```

`https://github.com/mikefarah/yq/` が出なければ別物である。

## `yq` を入れずに実行した場合

安全側に倒れる。中途半端な状態にはならない。`--check` は読めたところまで表示し、
足りないツールを名指しして止まる。

```console
$ scripts/bump-version.sh --check
Version check:

  package.json (version)                         1.0.0
error: required tool 'yq' is not on PATH
$ echo $?
1
```

バージョン更新の方は、`cmd_bump` が `preflight_manifests` で全 manifest を読めることを
先に確かめる。したがって **1 ファイルも書き換えないまま止まる**。

```console
$ scripts/bump-version.sh 1.0.1
error: required tool 'yq' is not on PATH
error: cannot read declared manifest: .hermes-plugin/plugin.yaml (version)
$ echo $?
1
```

「9 つの manifest が同じバージョンに揃っている」という不変条件は、`yq` が無いという
理由では壊れない。

## Windows の `jq` は CRLF を出す — このフォークが直した点

`yq` を正しく入れても、素の `scripts/bump-version.sh` は Windows では動かなかった。
原因は `yq` ではなく `jq` の側にある。ネイティブの `jq.exe` は標準出力をテキスト
モードで開くため、印字する行がすべて `\r\n` で終わる。

```console
$ jq -rn '"hello"' | od -c
0000000   h   e   l   l   o  \r  \n        <- jq 1.8.2 (Windows)

$ yq -rn '"hello"' | od -c
0000000   h   e   l   l   o  \n            <- yq は Go 製なので LF
```

`declared_files()` はこの出力を `while IFS=$'\t' read -r path field` で読む。結果、
フィールド名が `version\r` になる。`bash -x` の実測:

```console
++ read_yaml_field .../plugin.yaml $'version\r'
Error: no matches found
```

`strenv(FIELD)` が `version\r` を返し、`.["version\r"]` はどのキーにも当たらない。
これが `--check` と `bump` の両方を止めていた。被害はそれだけではなく、

- `write_json_field` は `jq` の出力をそのままファイルに落とすので、**JSON manifest
  8 つが CRLF に書き換わる**(実測: `{\n` → `{\r\n`)。
- `read_json_field` が返すバージョン文字列にも `\r` が付く。`--audit` はその文字列で
  リポジトリを `grep` するため何にも当たらず、**未宣言ファイルがあっても
  「All clear」と報告する**。
- `audit_excludes()` の除外パターンにも `\r` が付き、`--exclude` が効かない。

`jq` の出力を消費する 4 箇所すべてに `tr -d '\r'` を挟んで直した。パス名・フィールド名・
バージョン文字列に CR が正当に含まれることはなく、文字列内部の CR は `jq` が `\r` と
エスケープして出すので、バイトを消して問題ない。スクリプト冒頭の `set -o pipefail`
により `jq` の終了ステータスも保たれる。

`jq -b`(バイナリ出力)でも直るが、`-b` は `jq` 1.7 で追加されたフラグで 1.6 には無い。
`tr` を選んだのはそのためである。

回帰テストは `tests/version-bump/test-bump-version.sh` にある。PATH に「`jq` の出力へ
CR を足す」シムを置くことで、Linux 上でも Windows と同じ壊れ方を再現している。

## 動作確認

Windows 11 / Git Bash (`uname -o` = `Msys`) / `jq` 1.8.2 / `yq` 4.53.6 で、
作業ツリーを Windows の一時ディレクトリに展開して実測した。

| 確認項目 | 結果 |
|---|---|
| `scripts/bump-version.sh --check` | 9 manifest すべて表示、exit 0 |
| `tests/version-bump/test-bump-version.sh` | PASS |
| `scripts/bump-version.sh 1.0.1`(実際に更新) | 9 ファイルすべて 1.0.1、exit 0 |
| 更新後の JSON manifest 8 つの改行 | すべて LF(CR なし) |

## WSL / Linux から実行してもよい

Windows 側に何も入れたくないなら、バージョン更新とリリース作業だけを WSL または
Linux 側で行えばよい。`scripts/bump-version.sh` はリポジトリのファイルを書き換える
だけで、Windows 固有の要素を持たない。

## なぜ `yq` 依存そのものは外さないのか

`scripts/bump-version.sh` と `tests/version-bump/` は upstream 由来である。CRLF の修正は
Windows で動かすために避けられなかったが、`yq` を `sed` の行置換に替える変更は別で、
上流が保守しているファイルの書き換え量を増やすだけの見返りしかない。加えて
`select(tag == "!!str")` の型チェック — upstream 自身のテストが `version: 123` という
フィクスチャで検証している挙動 — を自前で書き直す必要がある。
