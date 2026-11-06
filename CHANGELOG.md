# Changelog / 変更履歴

## Unreleased

- **Limit to Selection** option in the panel. Turn it off to make the deformer act like a standard one
  (for example, bend the middle of a pipe and let the rest follow). The Fields layer stays but is disabled, so you can switch back at any time.
  パネルに「選択範囲に限定」を追加。オフにすると標準のデフォーマーと同じ動きになる（パイプの途中を曲げて、先の部分も付いてこさせるなど）。
  フィールドのレイヤーは「有効」オフで残るので、いつでも戻せる。
- **Whole object.** With nothing selected, in Model mode, or on an object that is not an editable mesh
  (a primitive, a generator such as Subdivision Surface or Cloner, or a Null group), the deformer is applied to the whole object.
  No selection tag is made. The deformer is sized to the current shape including child objects and aligned to the object's axes
  (the longest side becomes the main axis, with the anchor at its minus end). Update Selection switches between a part and the whole.
  Bevel on the whole object rounds only corners of 40° or more.
  On an object that is not a mesh, Update Selection, Limit to Selection and Freeze become available once you make it editable with C.
  **オブジェクト全体にかけられるようにした。** 何も選択していないとき・モデルモードのとき・編集可能なメッシュになっていないオブジェクト
  （プリミティブ、サブディビジョンサーフェイスやクローナーなどのジェネレーター、ヌルでまとめたグループ）では、オブジェクト全体にかける。
  選択範囲タグは作らない。デフォーマーの大きさは子オブジェクトも含めた今の形に合わせ、向きはオブジェクトの軸にそろえる（いちばん長い軸が主軸、起点はそのマイナス側の端）。
  「選択を取り直す」で、一部と全体を切り替えられる。全体のベベルは、40°以上の角だけ丸める。
  メッシュになっていないオブジェクトでは、「選択を取り直す」「選択範囲に限定」「フリーズ」は C キーで編集可能にすると使える。
- **Feather.** A new Feather field in the panel fades the effect inward from the border of the selection,
  so no crease appears where the deformed part meets the rest. Enter the width as a length (0 = sharp border, the default).
  It puts a Vertex Map tag into the deformer's Fields (standard Cinema 4D), one per deformer, and follows Update Selection,
  type switches and Fit. Freeze bakes the feathered shape and removes the vertex map. Not available for Bevel or the whole object.
  **境目のぼかし。** パネルに「ぼかし」を追加。選んだ範囲の内側で、境目に向かって効きを弱めるので、変形した部分とほかの部分の
  つなぎ目に折れ目が出ない。幅は長さで入れる（0＝くっきり、既定）。デフォーマーのフィールドに頂点マップタグ（標準機能）を入れる形で、
  デフォーマーごとに持ち、選択の取り直し・種類の切り替え・フィットにも付いてくる。フリーズはぼかしの効いた形で焼き込み、頂点マップも消す。
  ベベルとオブジェクト全体には無い。
- **Freeze tells you about child objects.** Freeze bakes only the mesh itself, so child objects that were deformed together
  go back to their original shape. The message now says so.
  フリーズで焼き込むのはメッシュそのものだけなので、一緒に変形していた子オブジェクトは元の形に戻る。そのことをメッセージで知らせるようにした。
- **Fix: the deformer could be placed a few degrees off.** On a surface where details are placed unevenly
  (for example, raised blocks scattered over a plane), the automatic direction drifted a few degrees away from the edges.
  The tip then did not move by the set amount along its whole width (in one scene, only 78–100% of it depending on the spot),
  and the anchor edge moved slightly. The deformer now lines up exactly with the edge flow.
  **修正: デフォーマーが数度傾いて置かれることがあった。** 凸などが偏って並ぶ面（平面に押し出しが不規則に散らばっている等）では、
  自動の向きがエッジから数度ずれていた。そのため先端の辺が場所によって指定した量だけずれず（ある例では指定値の 78〜100%）、
  起点の辺もわずかに動いていた。デフォーマーがエッジの流れにきちんと揃うようにした。

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
