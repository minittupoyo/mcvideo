# mcvideo

任意の動画を、Minecraft: Java Edition の中で **ブロック** または **パーティクル** で再生するためのデータパックを生成するツールです。
動画ごとにデータパック（と音声のリソースパック）を作り、ゲーム内で `/function <名前>:start` を打つと、いまいる場所の正面に画面が現れて再生が始まります。

*Generate a datapack that plays any video inside Minecraft: Java Edition, drawn with blocks or particles.*

- ブロック版: 壁に並べたブロックを、変わった部分だけ書き換えます。色は 2色〜121色のパレットから選べます。
- パーティクル版: 光る粒で絵を描きます（カラー / 白一色）。
- 音声: 動画の音声を、リソースパックとして一緒に作ります。
- 位置: 実行したプレイヤーの足元の高さと向きを基準に置きます（座標を決める必要はありません）。
- 地形を壊しません（ブロック版は、パレットのブロックだけを置き換えます）。
- 標準ライブラリだけで動きます（外部ツールは ffmpeg のみ）。

## 必要なもの

- Python 3.9 以上
- ffmpeg / ffprobe（`PATH` にあること。`FFMPEG` / `FFPROBE` 環境変数でも指定できます）
- Minecraft: Java Edition 26.3（他のバージョンは「[バージョンについて](#バージョンについて)」を参照）

## 使い方

```
git clone <このリポジトリ>
cd mcvideo
pip install -e .          # 任意。入れない場合は PYTHONPATH=src python -m mcvideo ... でも動きます
```

```
# ブロック版（コンクリート＋羊毛＋テラコッタの49色）
mcvideo clip.mp4 --name myclip --mode block --palette plus

# パーティクル版（カラー）
mcvideo clip.mp4 --name myclip --mode particle --width 64

# 白黒動画を、白いパーティクルで
mcvideo clip.mp4 --name bw --mode particle --mono --width 64
```

`build/<名前>/` に、次の2つができます。

| ファイル | 置き場所 |
|---|---|
| `<名前>_data.zip`（データパック） | ワールドの `datapacks/`（入れたら `/reload`） |
| `<名前>_audio.zip`（音声のリソースパック） | `resourcepacks/`（有効にして F3+T） |

`--world-datapacks <フォルダ>` と `--resourcepacks <フォルダ>` を付けると、生成と同時にコピーします。

### ゲーム内

画面を置きたい **方向を向き、下端にしたい高さ（足元）に立って**、次を実行します。

```
/function <名前>:start     再生を始める（前の画面は自動で消えて、置き直されます）
/function <名前>:stop      止める
/function <名前>:clear     止めて、画面を撤去する
```

- ブロック版: 向きは東西南北の4方向に丸められます。壁の下端が足元の高さに合い、正面 `--dist`（標準100）ブロック先に立ちます。
- パーティクル版: 向きはそのまま使い、正面 `--dist`（標準30）ブロック先に出ます。粒を明るく保つため `light` ブロックを置きます（`clear` で撤去）。
- 壁が大きいので、少し離れて見上げる位置で眺めるのがおすすめです。

## 主なオプション

| オプション | 内容 |
|---|---|
| `--mode block\|particle` | 描き方（標準: block） |
| `--width` / `--height` | 絵の大きさ（ピクセル）。高さは動画の縦横比から自動 |
| `--fps` | 1秒あたりのフレーム数（1, 2, 4, 5, 10, 20）。標準 10 |
| `--ss` / `--seconds` | 変換する範囲（開始位置と長さ） |
| `--palette` | ブロックの色数: `bw`（2）/ `gray`（4）/ `color`（16）/ `plus`（49）/ `full`（121） |
| `--dither` | `none` / `bayer` / `floyd_steinberg`（減色の誤差拡散） |
| `--preview 秒` | 指定した秒のフレームを、そのパレットで見るとどうなるか、PNG にして出して終了 |
| `--anchor bottom\|gaze` | `bottom`: 下端を足元の高さに合わせる（標準）。`gaze`: 目線の先を画面の中心にする |
| `--dist` / `--lift` | 正面までの距離 / 画面を持ち上げる高さ |
| `--cell` / `--scale` / `--thr` / `--mono` / `--invert` / `--particle` | パーティクル版の粒の間隔、大きさ、明るさの閾値、白一色、暗部を描く、粒の種類 |
| `--min-y` / `--max-y` | ワールドの高さ制限（標準: -64 / 319） |
| `--data-format` / `--resource-format` | パックの形式番号（標準: 26.3 用の 121 / 97） |

全オプションは `mcvideo --help` で見られます。

### パレットの選び方

ブロックの色数を増やすほど絵は自然になりますが、コマンド数とサイズが増え、`/reload` も遅くなります。
Connect the World（3分19秒、128×72）での目安:

| パレット | 色数 | コマンド数 | データパック |
|---|---|---|---|
| `color` | 16 | 約156万 | 約13MB |
| `plus` | 49 | 約302万 | 約25MB |
| `full` | 121 | 約454万 | 約39MB |

迷ったら `plus` がおすすめです。`--preview` で、ゲームに入れる前に見え方を比べられます。

```
mcvideo clip.mp4 --palette full --preview 60 --out build/preview
```

## バージョンについて

パックの形式番号は Minecraft **26.3** 用（データパック 121 / リソースパック 97）です。別のバージョンでは `--data-format` / `--resource-format` を合わせてください。
`@n` セレクター、`y_rotation`、ローカル座標（`^ ^ ^`）、`execute store`、`function` フォルダ名（単数形）、`min_format` / `max_format` を使うため、比較的新しいバージョン向けです。

動作確認の状況:
- Horizon（Rust による再実装クライアント、26.3）: ブロック版（`color` / `plus` / `full`）の再生を確認しています。パーティクル版は、以前の生成方式で確認したもので、現在の生成方式のゲーム内再生は未確認です。
- 通常の Java 版（Prism Launcher、Fabric、26.3）: 動いたという報告を利用者から受けています（詳細な検証は未実施）。

ブロックの色は、ゲーム本体のテクスチャの平均から求めています。別のバージョンで色を測り直すには:

```
python -m mcvideo.make_palette --jar <minecraft-クライアント.jar>
```

## 仕組み・困ったとき

- [仕組み](docs/how-it-works.md): マーカーによる相対配置、差分書き換え、パレット、パーティクルの扱い。
- [トラブルシューティング](docs/troubleshooting.md): 壁が出ない、`reload` が遅い、音が鳴らない、など。

## 開発

```
python -B -m unittest discover -s tests -v
```

テストは ffmpeg があれば、短い合成動画から実際にパックを生成して構造を検証します（なければ、その部分は飛ばされます）。

## 注意

- 変換した動画の権利は、元の動画の権利者にあります。個人のワールドで楽しむ範囲に留め、変換したパックや元の動画を、許可なく配布・公開しないでください。動画の取得方法や利用規約の遵守は、利用者の責任です。
- これは非公式のツールで、Mojang Studios / Microsoft とは関係がありません。「Minecraft」は、その権利者の商標です。
- リポジトリには、ゲームのテクスチャは含まれていません。含まれているのは、テクスチャを平均して得た色の数値（`src/mcvideo/data/blockpalette.json`）だけです。
