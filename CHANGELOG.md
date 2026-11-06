# Changelog / 変更履歴

## Unreleased

- **Limit to Selection** option in the panel. Turn it off to make the deformer act like a standard one
  (for example, bend the middle of a pipe and let the rest follow). The Fields layer stays but is disabled, so you can switch back at any time.
  パネルに「選択範囲に限定」を追加。オフにすると標準のデフォーマーと同じ動きになる（パイプの途中を曲げて、先の部分も付いてこさせるなど）。
  フィールドのレイヤーは「有効」オフで残るので、いつでも戻せる。
- **Nothing selected = whole object.** With no polygons, points or edges selected, the deformer is applied to the whole object,
  the same as Select All (also for Update Selection). The anchor is then at the minus end of the object's axis (the bottom for a tall object).
  何も選択していなければ、全選択と同じくオブジェクト全体にかかるようにした（「選択を取り直す」も同じ）。
  起点はオブジェクトの軸のマイナス側の端（縦長なら下）。
- **Fix: the box could come out tilted by a few degrees.** On a surface where details are placed unevenly
  (for example, raised blocks scattered over a plane), the automatic direction drifted a few degrees away from the edges.
  The tip then did not move by the set amount along its whole width (in one scene, only 78–100% of it depending on the spot),
  and the anchor edge moved slightly. The box now lines up exactly with the edge flow.
  **修正: 箱が数度傾くことがあった。** 凸などが偏って並ぶ面（平面に押し出しが不規則に散らばっている等）では、
  自動の向きがエッジから数度ずれていた。そのため先端の辺が場所によって指定した量だけずれず（ある例では指定値の 78〜100%）、
  起点の辺もわずかに動いていた。箱がエッジの流れにきちんと揃うようにした。

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
