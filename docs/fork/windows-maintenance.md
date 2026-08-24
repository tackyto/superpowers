# Windows Git Bash からフォークを保守する

このフォークを Windows で**保守**する — バージョンを上げる、リリースを切る — 場合に
必要な前提条件をまとめる。プラグインを**使う**だけなら何も要らない。インストール手順は
[README.md](../../README.md) を見ること。

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

入っているものが mikefarah 版かどうかは、バージョン表示に出る URL で判別する。

```console
$ yq --version
yq (https://github.com/mikefarah/yq/) version v4.49.2
```

`https://github.com/mikefarah/yq/` が出なければ別物である。

## 入れずに実行した場合

安全側に倒れる。中途半端な状態にはならない。

`--check` は読めたところまで表示し、足りないツールを名指しして止まる。

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

## 回避路 — WSL / Linux から実行する

Windows 側に `yq` を入れたくないなら、バージョン更新とリリース作業だけを WSL または
Linux 側で行えばよい。`scripts/bump-version.sh` はリポジトリのファイルを書き換える
だけで、Windows 固有の要素を一切持たない。

## なぜ `yq` 依存を外さないのか

`scripts/bump-version.sh`、`.version-bump.json`、`tests/version-bump/` はいずれも
upstream 由来で、フォーク時点(`fork-base/v6.3.0`)と同一である。しかも upstream は
このスクリプトをリリースのたびに更新している。

```console
$ git log --oneline -- scripts/bump-version.sh
b36e082 Release v6.3.0 ...
1f20bef Release v5.0.7 ...
```

`yq` を `sed` の行置換に替えれば依存は消える。だが上流が保守しているファイルを
書き換えることになり、同期のたびに同じコンフリクトを解き続けることになる。加えて
`select(tag == "!!str")` の型チェック — upstream 自身のテストが `version: 123` という
フィクスチャで検証している挙動 — を自前で書き直す必要がある。保守のときにしか効かない
利便性のために払う代償としては大きい。
