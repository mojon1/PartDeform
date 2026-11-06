# Changelog / 変更履歴

## Unreleased

- **Limit to Selection** option in the panel. Turn it off to make the deformer act like a standard one
  (for example, bend the middle of a pipe and let the rest follow). The Fields layer stays but is disabled, so you can switch back at any time.
  パネルに「選択範囲に限定」を追加。オフにすると標準のデフォーマーと同じ動きになる（パイプの途中を曲げて、先の部分も付いてこさせるなど）。
  フィールドのレイヤーは「有効」オフで残るので、いつでも戻せる。

## 1.0.0 (2026-11-06)

First public release. / 最初の公開版。

- Place Bend, Shear, Taper, Twist, Bulge or Bevel fitted to a polygon, point or edge selection in one click.
  ポリゴン・ポイント・エッジの選択範囲に合わせて、屈曲・シアー・テーパー・ツイスト・膨張・ベベルを1クリックで置く。
- Automatic direction and anchor (unselected side), following the edge flow.
  向きと起点（未選択側）の自動判定。エッジの流れに合わせる。
- Anchor mode (click to switch the anchor repeatedly), Flip, Auto, Axis, Rotate 90°, Fit.
  起点モード（クリックで続けて切り替え）、反転・自動・主軸・90°回転・フィット。
- Value fields with real lengths (Shear / Taper / Bulge / Bevel) and angles (Bend / Twist / direction), live while dragging.
  実際の長さ・角度で調整できる数値欄（ドラッグ中もリアルタイム）。
- Switch type, Shift+click to stack, Update Selection, Freeze (one undo step).
  種類の切り替え、Shift＋クリックで重ねる、選択を取り直す、フリーズ（アンドゥ1回）。
- English / Japanese UI.
  英語・日本語表示。
- The version is shown in the panel title and in VERSION.txt.
  パネルのタイトルと VERSION.txt でバージョンが分かる。
