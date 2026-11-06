# -*- coding: utf-8 -*-
"""PartDeform: パネル・起点クリックツール・コマンド・メニュー。"""
import math

import c4d
from c4d import gui, plugins

from . import __version__
from . import core
from . import icons
from . import winowner
from .i18n import tr

TITLE = "PartDeform"
# パネルの題名（窓・ドッキングしたタブに出る）にはバージョンを入れる。
# winowner は題名で窓を探すので、パネルの窓に関わるところでは必ずこちらを使う
PANEL_TITLE = "%s %s" % (TITLE, __version__)
LOG_PREFIX = "[%s] " % TITLE

# パネルのガジェットID
G_TYPE_BASE = 1200  # + DEFORMER_TYPES の添字
G_CYCLE = 1300
G_FLIP = 1301
G_ROT90 = 1302
G_PICK = 1303
G_AUTO = 1304
G_REFIT = 1305
G_FREEZE = 1306
G_SHIFT_LABEL = 1400  # 1段目（量）の名前
G_SHIFT = 1401  # 1段目（量）: シアー・テーパー・膨張・ベベルは長さ、屈曲・ツイストは角度
G_DIR_LABEL = 1402  # 2段目（方向）の名前
G_DIR = 1403  # 2段目（方向）: 屈曲・シアーの角度（曲げ・ずらす向き）
G_FEATHER_LABEL = 1404  # 3段目（ぼかし）の名前
G_FEATHER = 1405  # 3段目（ぼかし）: 境目から内側へ効きを弱める幅（長さ）
G_DEFORMEDIT = 1500
G_LIMIT = 1501  # 「選択範囲に限定」のチェック
G_RECAPTURE = 1307
LABEL_OFFSET = 5000  # アイコンの下の名前のガジェットID＝ボタンのID＋これ

# パネルのボタンに流用する C4D 標準のアイコン（コマンドのアイコン）
ICON_CYCLE = 100004839  # ピボット（3本の軸）
ICON_FLIP = 14041  # 法線を反転（上下の矢印）
ICON_ROT90 = 450000002  # 法線に沿って回転（軸まわりの回転）
ICON_PICK = 1027636  # インタラクティブ作業平面（グリッド＋カーソル）
ICON_AUTO = 1019940  # トランスフォームをリセット
ICON_REFIT = 1011169  # UV をキャンバスに合わせる（枠に合わせる）
ICON_RECAPTURE = 12552  # 選択範囲を記録
ICON_FREEZE = 12233  # 現在の状態をオブジェクト化（雪の結晶）

# 「起点と方向」のボタン（横1列）。いちばん使う「起点（クリックで指定）」を左端に置き、
# 左3つ＝起点（起点・反転・自動）、右3つ＝方向と箱（主軸・90°回転・フィット）。
# 名前は種類ボタン（屈曲〜ベベル）より幅が広がらないよう短くし、詳しい説明はツールチップに書く
ORIENT_BUTTONS = (
    (G_PICK, ICON_PICK, tr("起点", "Anchor"),
     tr("ビューでクリックした端を起点（効果0）にする。続けて切り替えられる。"
        "終了は対象の外をクリック・もう一度このボタン・ほかのボタン・Esc",
        "Click a side of the mesh in the viewport to make it the anchor (no effect there). You can keep clicking "
        "to switch. To finish: click outside the object, press this button again, press another button, or Esc")),
    (G_FLIP, ICON_FLIP, tr("反転", "Flip"),
     tr("起点と先端を入れ替える", "Swap the anchor and the tip")),
    (G_AUTO, ICON_AUTO, tr("自動", "Auto"),
     tr("向きと起点を自動判定に戻す", "Reset the direction and the anchor to automatic")),
    (G_CYCLE, ICON_CYCLE, tr("主軸", "Axis"),
     tr("曲げる・ひねる軸（主軸）を、箱の別の軸に切り替える（起点は自動判定）",
        "Switch the main (bend / twist) axis to another axis of the box (the anchor is chosen automatically)")),
    (G_ROT90, ICON_ROT90, tr("90°回転", "Rot 90°"),
     tr("主軸まわりに 90° 回す（曲げ・せん断の方向が変わる）",
        "Rotate 90° around the main axis (changes the bend / shear direction)")),
    (G_REFIT, ICON_REFIT, tr("フィット", "Fit"),
     tr("今の向きのまま、選択範囲タグ（全体用はオブジェクトの今の形）に箱を合わせ直す（再フィット）",
        "Refit the box to the selection tag (for a whole-object deformer, to the object's current shape), keeping the current direction")),
)

# 起点クリックツールを抜けたあとに戻すツール
_previous_tool = None

# パネルの設定（C4D を終了しても残る。キーは本体のID）
PREF_LIMIT = 1  # 新しく作るデフォーマーを選択範囲に限定するか（既定はオン）


def limit_default():
    """これから作るデフォーマーを選択範囲に限定するか（パネルの「選択範囲に限定」の既定値）。"""
    bc = plugins.GetWorldPluginData(core.ID_PANEL)
    return bc.GetBool(PREF_LIMIT, True) if bc is not None else True


def set_limit_default(on):
    bc = plugins.GetWorldPluginData(core.ID_PANEL) or c4d.BaseContainer()
    bc.SetBool(PREF_LIMIT, bool(on))
    plugins.SetWorldPluginData(core.ID_PANEL, bc)


def _icon(resource_id):
    try:
        return c4d.bitmaps.InitResourceBitmap(resource_id)
    except Exception:
        return None


def report(message, error=False):
    """C4D のステータスバーとコンソールにメッセージを出す（パネルには出さない）。"""
    gui.StatusSetText(("⚠ " if error else "") + message)
    print(LOG_PREFIX + message)


def open_panel():
    if not _panel.IsOpen():
        _panel.Open(c4d.DLG_TYPE_ASYNC, pluginid=core.ID_PANEL, defaultw=300, defaulth=0)


def _run(doc, label, func):
    """コアの処理を呼び、結果をパネルに出す。"""
    if doc is None:
        return None
    try:
        result = func()
    except core.SDError as e:
        report(str(e), error=True)
        return None
    if label:
        report(label)
    return result


# ---------------------------------------------------------------------------
# 操作（パネルとコマンドから呼ぶ）
# ---------------------------------------------------------------------------
def shift_down():
    """Shift キーが押されているか。"""
    bc = c4d.BaseContainer()
    if gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.BFM_INPUT_CHANNEL, bc):
        return bool(bc.GetInt32(c4d.BFM_INPUT_QUALIFIER) & c4d.QSHIFT)
    return False


def do_type(doc, dtype, add=False):
    """種類ボタン。add=True（Shift＋クリック）で、選択中のデフォーマーに重ねて追加する。"""
    leave_pick_mode(doc)
    name = c4d.GetObjectName(dtype)

    def work():
        previous = core.active_sd_deformer(doc)
        previous_name = previous.GetName() if previous is not None else ""
        limit = limit_default()
        reason = _whole_reason_on_active(doc) if previous is None else None
        d, how = core.create_or_switch(doc, dtype, add=add, limit=limit)
        if how == "create" and core.is_whole(d):
            report(_whole_created_message(d, reason))
        elif how == "add":
            report(tr("%s を追加しました（%s と同じ選択範囲・向きで重ねました）。", "Added %s (stacked on %s with the same selection and direction).") % (d.GetName(), previous_name))
        elif how == "create" and core.is_bevel(d):
            # ベベルは選択範囲タグの名前で限定するので、タグを持たない子オブジェクトには効かない
            report(tr("%s を作成しました。オフセットはパネルの量の欄か属性マネージャーで調整できます。", "Created %s. Adjust the offset in the panel or in the Attribute Manager.") % d.GetName())
        elif how == "create" and not limit:
            report(tr("%s を作成しました（選択範囲に限定: オフ。選択していない部分も、標準のデフォーマーと同じように変形します）。",
                      "Created %s (Limit to Selection: off. Unselected parts deform too, as with a standard deformer).") % d.GetName())
        elif how == "create":
            message = tr("%s を作成しました。向きが違うときは「起点と方向」のボタン（「起点」でクリック指定）で直せます。", "Created %s. If the direction is wrong, fix it with the Anchor & Direction buttons (Anchor lets you click the side).") % d.GetName()
            children = core.affected_children(d.GetUp())
            if children:
                names = tr("、", ", ").join(tr("「%s」", '"%s"') % c.GetName() for c in children[:3])
                if len(children) > 3:
                    names += tr("ほか", " and others")
                report(tr("%s を作成しました。子オブジェクト %s も一緒に変形します（フィールドの変数タグは、タグを持たない子を除外できません）。",
                          "Created %s. The child object(s) %s are deformed too (a Variable Tag field cannot exclude "
                          "children that do not have the tag).")
                       % (d.GetName(), names), error=True)
            else:
                report(message)
        else:
            report(tr("%s に切り替えました。", "Switched to %s.") % name)
        return d

    return _run(doc, None, work)


def _whole_reason_on_active(doc):
    """選択中のオブジェクト1つに作るとき、全体用になる理由（core.whole_reason）。決まらなければ None。"""
    act = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE)
    if len(act) != 1 or act[0].GetInfo() & c4d.OBJECT_MODIFIER:
        return None
    return core.whole_reason(doc, act[0])


def _whole_note(reason, obj_name):
    """全体用になった理由（作成・選択の取り直しのメッセージに付ける）。"""
    if reason == "not_mesh":
        return tr("「%s」はメッシュになっていないので、オブジェクト全体にかけました。選択を取り直す・選択範囲に限定・フリーズは、"
                  "C キーで編集可能にすると使えます。",
                  "\"%s\" is not a mesh, so it works on the whole object. Update Selection, Limit to Selection and Freeze "
                  "become available once you make it editable with C.") % obj_name
    if reason == "mode":
        return tr("ポイント・エッジ・ポリゴンのモードではないので、オブジェクト全体にかけました。一部だけにかけるときは、そのモードで選択してください。",
                  "Not in Points, Edges or Polygons mode, so it works on the whole object. To work on a part, select it in one of those modes.")
    return tr("何も選択していなかったので、オブジェクト全体にかけました。",
              "Nothing was selected, so it works on the whole object.")


def _whole_created_message(d, reason):
    parent = d.GetUp()
    message = tr("%s を作成しました。", "Created %s. ") % d.GetName() + _whole_note(reason, parent.GetName() if parent else "")
    if parent is not None and core.shape_children(parent):
        message += tr("子オブジェクトも一緒に変形するので、箱は子も含めた大きさに合わせました。",
                      " Child objects are deformed too, so the box covers them as well.")
    if core.is_bevel(d):
        message += tr("角度が 40°以上の角だけ丸めます（属性マネージャーの「角度しきい値」で変えられます）。",
                      " Only corners of 40° or more are rounded (change it with Angle Threshold in the Attribute Manager).")
    return message


def do_reorient(doc, func, label):
    leave_pick_mode(doc)
    return _run(doc, label, lambda: func(doc, core.edit_target(doc)))


def do_recapture(doc):
    """選択中の PartDeform のデフォーマー（またはメッシュの下にただ1つあるもの）の選択範囲を、メッシュの今の選択で取り直す。"""
    leave_pick_mode(doc)

    def work():
        try:
            target = core.edit_target(doc)
        except core.SDError:
            raise core.SDError(tr("選択を取り直すデフォーマーを選んでください（メッシュで選択し直したあと、オブジェクトマネージャーでデフォーマーをクリック）。", "Select the deformer to update (reselect on the mesh, then click the deformer in the Object Manager)."))
        mesh = target.GetUp()
        reason = core.whole_reason(doc, mesh) if mesh is not None else None
        d, tag = core.recapture_selection(doc, target, limit_default())
        if tag is None:
            report(tr("%s をオブジェクト全体用にしました。", "Made %s work on the whole object. ") % d.GetName()
                   + _whole_note(reason, mesh.GetName())
                   + tr("向きと起点は自動判定し直したので、違うときは「起点と方向」のボタンで直せます。",
                        " The direction and the anchor were detected again; fix them with the Anchor & Direction buttons if needed."))
            return d
        shared = [x for x in core.sd_deformers_under(d.GetUp()) if x != d and core.get_selection_tag(x) == tag]
        note = tr("（同じタグを使う %d 個も合わせ直しました）", " (also refitted %d deformer(s) sharing the tag)") % len(shared) if shared else ""
        report(tr("%s の選択範囲を取り直しました（タグ「%s」）%s。向きと起点は自動判定し直したので、違うときは「起点と方向」のボタンで直せます。", "Updated the selection of %s (tag \"%s\")%s. The direction and the anchor were detected again; fix them with the Anchor & Direction buttons if needed.")
               % (d.GetName(), tag.GetName(), note))
        return d

    return _run(doc, None, work)


def do_freeze(doc):
    leave_pick_mode(doc)

    def work():
        targets = core.freeze_targets(doc)
        meshes = core.freeze(doc, targets)
        message = tr("%d 個のデフォーマーをフリーズしました（%s）。", "Froze %d deformer(s) (%s).") % (len(targets), tr("、", ", ").join(m.GetName() for m in meshes))
        children = [c for m in meshes for c in core.affected_children(m)]
        if children:
            # フリーズで焼き込むのはメッシュの点だけ。デフォーマーを消すので、一緒に変形していた子は元の形に戻る
            names = tr("、", ", ").join(tr("「%s」", '"%s"') % c.GetName() for c in children[:3])
            if len(children) > 3:
                names += tr("ほか", " and others")
            message += tr("子オブジェクト %s の変形は焼き込まれず、元の形に戻りました。", " The child object(s) %s were not baked and are back to their original shape.") % names
            report(message, error=True)
        else:
            report(message)
        return meshes

    return _run(doc, None, work)


def do_limit(doc, on):
    """「選択範囲に限定」のチェック。選択中の PartDeform のデフォーマーを切り替え（アンドゥ1回）、
    これから作るデフォーマーの既定値にもする（デフォーマーを選んでいなければ既定値だけ）。"""
    leave_pick_mode(doc)
    set_limit_default(on)

    def work():
        target = _target_or_none(doc)
        if target is None or core.is_bevel(target):
            if on:
                report(tr("これから作るデフォーマーは、選択範囲に限定します。", "New deformers will be limited to the selection."))
            else:
                report(tr("これから作るデフォーマーは、選択範囲に限定しません（フィールドのレイヤーは「有効」オフで入ります）。",
                          "New deformers will not be limited to the selection (the Fields layer is added but disabled)."))
            return None
        core.set_selection_limit(doc, target, on)
        if on:
            report(tr("%s を選択範囲に限定しました（選択した部分だけが変形します）。",
                      "Limited %s to the selection (only the selected part deforms).") % target.GetName())
        else:
            report(tr("%s の「選択範囲に限定」をオフにしました。選択していない部分も、標準のデフォーマーと同じように変形します"
                      "（パイプの一部を曲げて、先の部分も付いてこさせるときなど）。",
                      "Turned off Limit to Selection for %s. Unselected parts deform too, as with a standard deformer "
                      "(for example, to bend part of a pipe and let the rest follow).") % target.GetName())
        return target

    return _run(doc, None, work)


# パネルの数値欄（3段）。選んでいるデフォーマーの種類で、名前と単位（長さ／角度）が切り替わる
AMOUNT_LABEL_NONE = tr("量（PartDeform のデフォーマーを選ぶと使えます）", "Amount (select a PartDeform deformer)")
DIRECTION_LABEL_NONE = tr("角度（屈曲・シアーで使えます）", "Angle (Bend / Shear)")
FEATHER_LABEL_NONE = tr("ぼかし（選択範囲にかけた箱の種類で使えます）", "Feather (box types on a selection)")
ROW_IDS = (G_SHIFT, G_DIR, G_FEATHER)
ROW_LABEL_ID = {G_SHIFT: G_SHIFT_LABEL, G_DIR: G_DIR_LABEL, G_FEATHER: G_FEATHER_LABEL}
ROW_LABEL_NONE = {G_SHIFT: AMOUNT_LABEL_NONE, G_DIR: DIRECTION_LABEL_NONE, G_FEATHER: FEATHER_LABEL_NONE}
ROW_CONTENT = {G_SHIFT: core.amount_row, G_DIR: core.direction_row, G_FEATHER: core.feather_row}
# ドラッグ前の値に戻すパラメーター（ぼかしはパラメーターではなく頂点マップなので、幅で戻す＝_finish_drag）
ROW_PARAMS = {G_SHIFT: core.amount_params, G_DIR: core.direction_params, G_FEATHER: lambda d: ()}
ROW_NONE_RANGE = {G_SHIFT: (-1.0, 1.0), G_DIR: core.DIRECTION_SLIDER, G_FEATHER: (0.0, 1.0)}


def _row_target(doc, gid):
    """数値欄 gid の対象と中身: (デフォーマー, (名前, 単位, 値, スライダー範囲))。使えなければ (None, None)。

    対象は選択中、または選択オブジェクト直下にただ1つある PartDeform のデフォーマー。
    ベベルのオフセットモードが「比例」のときは長さではないので量の欄は使えない。
    """
    d = _target_or_none(doc) if doc is not None else None
    row = ROW_CONTENT[gid](d) if d is not None else None
    return (d, row) if row is not None else (None, None)


def set_deformed_edit(doc, on):
    """アクティブなビューの「デフォーマ後に編集」を切り替える（ビューの表示メニューと同じ設定を書き換えるだけ）。"""
    bd = doc.GetActiveBaseDraw() if doc is not None else None
    if bd is None:
        report(tr("アクティブなビューがありません。", "There is no active view."), error=True)
        return
    bd[c4d.BASEDRAW_DATA_DEFORMEDEDIT] = bool(on)
    c4d.EventAdd()
    report(tr("デフォーマ後に編集を%sにしました（アクティブなビュー）。", "Turned Deformed Editing %s (active view).") % (tr("オン", "on") if on else tr("オフ", "off")))


def redraw_now():
    """すべてのビューを、その場で（スレッドを使わず）評価・再描画する。"""
    c4d.DrawViews(c4d.DRAWFLAGS_NO_THREAD | c4d.DRAWFLAGS_STATICBREAK | c4d.DRAWFLAGS_INDRAG)


def _mouse_left_down():
    bc = c4d.BaseContainer()
    if gui.GetInputState(c4d.BFM_INPUT_MOUSE, c4d.BFM_INPUT_MOUSELEFT, bc):
        return bc.GetInt32(c4d.BFM_INPUT_VALUE) == 1
    return False


def format_length(value):
    try:
        return c4d.utils.FormatNumber(value, c4d.FORMAT_METER, 0)
    except Exception:
        return "%.2f" % value


def format_angle(value):
    """ラジアンを「45°」のような表示にする（小数は2桁まで、末尾の0は省く）。"""
    return ("%.2f" % math.degrees(value)).rstrip("0").rstrip(".") + "°"


def do_amount(doc, value):
    """1段目（量）の確定。長さの種類は強度を逆算、屈曲・ツイストは角度をそのまま入れる。アンドゥ1回。"""
    def work():
        d, row = _row_target(doc, G_SHIFT)
        if d is None:
            raise core.SDError(tr("PartDeform のデフォーマーを選択してください（ベベルはオフセットモードが「比例」以外のとき）。", "Select a PartDeform deformer (Bevel: offset mode other than Proportional)."))
        core.set_amount(doc, d, value)
        label, unit = row[0], row[1]
        if core.is_bevel(d):
            report(tr("%s を %s にしました。", "Set %s to %s.") % (label, format_length(d[c4d.O_BEVEL_RADIUS])))
        elif unit == core.UNIT_ANGLE:
            report(tr("%s を %s にしました。", "Set %s to %s.") % (label, format_angle(value)))
        else:
            report(tr("%s を %s にしました（強度 %.1f%%）。", "Set %s to %s (strength %.1f%%).") % (label, format_length(value), d[c4d.DEFORMOBJECT_STRENGTH] * 100.0))
        return d

    return _run(doc, None, work)


def do_direction(doc, value):
    """2段目（方向）の確定。屈曲・シアーの角度。シアーは先端のずれが変わらないよう強度も換算する。アンドゥ1回。"""
    def work():
        d, row = _row_target(doc, G_DIR)
        if d is None:
            raise core.SDError(tr("屈曲かシアーのPartDeform のデフォーマーを選択してください。", "Select a PartDeform Bend or Shear deformer."))
        core.set_direction(doc, d, value)
        if d.GetType() == c4d.Oshear:
            report(tr("%s を %s にしました（先端のずれ %s、強度 %.1f%%）。", "Set %s to %s (tip offset %s, strength %.1f%%).") % (
                row[0], format_angle(value), format_length(core.shear_shift(d)), d[c4d.DEFORMOBJECT_STRENGTH] * 100.0))
        else:
            report(tr("%s を %s にしました。", "Set %s to %s.") % (row[0], format_angle(value)))
        return d

    return _run(doc, None, work)


def do_feather(doc, value):
    """3段目（ぼかし）の確定。境目から内側へ効きを弱める幅。0 でぼかしを外す。アンドゥ1回。"""
    def work():
        d, row = _row_target(doc, G_FEATHER)
        if d is None:
            raise core.SDError(tr("選択範囲にかけた PartDeform の箱の種類（屈曲・シアー・テーパー・ツイスト・膨張）を選択してください。",
                                  "Select a PartDeform Bend, Shear, Taper, Twist or Bulge that works on a selection."))
        core.set_feather(doc, d, value)
        width = core.feather_width(d)
        if width <= 0.0:
            report(tr("%s のぼかしを外しました（境目はくっきり）。", "Removed the feather from %s (sharp border).") % d.GetName())
            return d
        message = tr("%s のぼかしを %s にしました（境目から内側へ弱めます）。", "Set the feather of %s to %s (fades inward from the border).") % (d.GetName(), format_length(width))
        if core.selection_limit(d) is False:
            report(message + tr("「選択範囲に限定」がオフなので、オンにすると効きます。", " Limit to Selection is off; turn it on for the feather to take effect."), error=True)
        else:
            report(message)
        return d

    return _run(doc, None, work)


ROW_APPLY = {G_SHIFT: do_amount, G_DIR: do_direction, G_FEATHER: do_feather}


def show_in_attribute_manager(obj):
    """属性マネージャーをオブジェクトモードにして obj を表示する（ツールの設定画面にしない）。"""
    if obj is None:
        return
    try:
        gui.ActiveObjectManager_SetObject(
            c4d.ACTIVEOBJECTMODE_OBJECT, obj, c4d.ACTIVEOBJECTMANAGER_SETOBJECTS_OPEN, c4d.DescID())
    except Exception as e:  # 表示の切り替えに失敗しても操作は続ける
        print(LOG_PREFIX + tr("属性マネージャーを切り替えられませんでした: %r", "Could not switch the Attribute Manager: %r") % e)


def _target_or_none(doc):
    try:
        return core.edit_target(doc)
    except core.SDError:
        return None


def start_pick_tool(doc):
    global _previous_tool
    try:
        target = core.edit_target(doc)
        if core.is_bevel(target):
            raise core.SDError(tr("ベベルには箱や向きがないので、起点の指定はありません。", "Bevel has no box or direction, so it has no anchor."))
    except core.SDError as e:
        report(str(e), error=True)
        return
    current = doc.GetAction()
    if current != core.ID_TOOL_PICK:
        _previous_tool = current
    doc.SetAction(core.ID_TOOL_PICK)
    show_in_attribute_manager(target)
    report(tr("起点（効果0）にしたい端をクリックしてください。続けて切り替えられます。終了は、対象の外をクリック・もう一度「起点」・ほかのボタン・Esc。", "Click the side to use as the anchor (no effect there). You can keep clicking to switch. To finish: click outside the object, press Anchor again, press another button, or Esc."))
    c4d.EventAdd()


def pick_mode_on(doc):
    """起点クリックのモード中か。"""
    return doc is not None and doc.GetAction() == core.ID_TOOL_PICK


def end_pick_tool(doc):
    global _previous_tool
    tool = _previous_tool if _previous_tool and _previous_tool != core.ID_TOOL_PICK else c4d.ID_MODELING_MOVE
    _previous_tool = None
    doc.SetAction(tool)
    # ツールを戻すと属性マネージャーがツールの設定に切り替わるので、デフォーマーの属性に戻す
    show_in_attribute_manager(_target_or_none(doc))
    c4d.EventAdd()


def leave_pick_mode(doc):
    """ほかの機能を使うときは、起点クリックのモードを抜けてから行う。"""
    if pick_mode_on(doc):
        end_pick_tool(doc)


# ---------------------------------------------------------------------------
# パネル
# ---------------------------------------------------------------------------
class PartDeformPanel(gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle(PANEL_TITLE)
        self.GroupBegin(1000, c4d.BFH_SCALEFIT | c4d.BFV_TOP, cols=1)
        self.GroupBorderSpace(6, 6, 6, 6)
        self.GroupSpace(4, 4)

        self.AddStaticText(0, c4d.BFH_LEFT, name=tr("種類（作成／切り替え）", "Type (create / switch)"))
        self.GroupBegin(1001, c4d.BFH_SCALEFIT, cols=len(core.DEFORMER_TYPES))
        self.GroupSpace(2, 2)
        for i, dtype in enumerate(core.DEFORMER_TYPES):
            self._add_type_button(G_TYPE_BASE + i, dtype)
        self.GroupEnd()
        # 選択範囲に限定（フィールドの変数タグレイヤーの「有効」）。選択中のデフォーマーの状態を表示・切り替えし、
        # これから作るデフォーマーの既定値にもなる。オフはパイプの一部を曲げて先も付いてこさせるときなど
        self.AddCheckbox(G_LIMIT, c4d.BFH_LEFT, 0, 0, name=tr("選択範囲に限定", "Limit to Selection"))

        # 1段目＝量: シアー・テーパー・膨張の強度（%）は実際に動く量（長さ）、ベベルはオフセット、
        # 屈曲は強度（曲げる角度）、ツイストは角度（ひねる角度）。属性マネージャーと同じ「数値欄＋スライダー」
        self.AddStaticText(G_SHIFT_LABEL, c4d.BFH_SCALEFIT, name=AMOUNT_LABEL_NONE)
        self.AddEditSlider(G_SHIFT, c4d.BFH_SCALEFIT)
        # 2段目＝方向: 屈曲・シアーの角度（曲げる向き・ずらす向き）
        self.AddStaticText(G_DIR_LABEL, c4d.BFH_SCALEFIT, name=DIRECTION_LABEL_NONE)
        self.AddEditSlider(G_DIR, c4d.BFH_SCALEFIT)
        # 3段目＝ぼかし: 選んだ範囲の内側で、境目に向かって効きを 0 まで弱める幅（0 でくっきり）
        self.AddStaticText(G_FEATHER_LABEL, c4d.BFH_SCALEFIT, name=FEATHER_LABEL_NONE)
        self.AddEditSlider(G_FEATHER, c4d.BFH_SCALEFIT)

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name=tr("起点と方向", "Anchor & Direction"))
        self.GroupBegin(1002, c4d.BFH_SCALEFIT, cols=len(ORIENT_BUTTONS))  # 横1列
        self.GroupSpace(2, 2)  # 種類ボタンと同じ間隔
        for gid, icon, label, tip in ORIENT_BUTTONS:
            # 「起点」はモードのオン／オフが見えるようトグル表示（押すたびにモードに入る／抜ける）
            self._add_icon_button(gid, icon, label, tip, toggle=(gid == G_PICK))
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.GroupBegin(1003, c4d.BFH_SCALEFIT, cols=2)
        self.GroupSpace(2, 4)
        self._add_icon_button(G_RECAPTURE, ICON_RECAPTURE, tr("選択を取り直す", "Update Selection"),
                              tr("メッシュの今の選択（今のモード）で選択範囲タグを取り直し、向きと起点も自動判定し直す", "Replace the selection tag with the mesh's current selection (current mode) and detect the direction and the anchor again"))
        self._add_icon_button(G_FREEZE, ICON_FREEZE, tr("フリーズ", "Freeze"),
                              tr("変形をポリゴンに書き込み、デフォーマーと PartDeform が作った選択範囲タグ（とぼかしの頂点マップ）を消す（アンドゥ1回で戻る）", "Bake the deformation into the polygons and remove the deformer and the selection tag (and feather vertex map) created by PartDeform (one undo step)"))
        self.GroupEnd()

        # ビューの「表示 ＞ デフォーマ後に編集」と同じ設定（アクティブなビュー）。パネルは値を読み書きするだけ
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddCheckbox(G_DEFORMEDIT, c4d.BFH_LEFT, 0, 0, name=tr("デフォーマ後に編集（アクティブなビュー）", "Deformed Editing (active view)"))
        self.GroupEnd()
        return True

    def _add_icon_button(self, gid, icon_id, label, tooltip, size=32, toggle=False):
        """アイコン（上）と名前（下）のボタン。アイコンを押すと gid の Command が来る。

        BITMAPBUTTON_STRING で文字を入れると「文字→アイコン」の順に描かれ、
        アイコンが隣の名前に付いて見えるので、名前はアイコンの下に別に置く。
        名前のガジェットIDは gid + LABEL_OFFSET（ボタンと一緒に使える／使えないを切り替えるため）。
        """
        self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=1)
        self.GroupSpace(0, 0)
        bc = c4d.BaseContainer()
        bc.SetBool(c4d.BITMAPBUTTON_BUTTON, True)
        if toggle:
            bc.SetBool(c4d.BITMAPBUTTON_TOGGLE, True)
        bc.SetInt32(c4d.BITMAPBUTTON_ICONID1, icon_id)
        bc.SetInt32(c4d.BITMAPBUTTON_FORCE_SIZE, size)
        bc.SetInt32(c4d.BITMAPBUTTON_FORCE_SIZE_Y, size)
        bc.SetInt32(c4d.BITMAPBUTTON_BORDER, c4d.BORDER_ROUND)
        bc.SetString(c4d.BITMAPBUTTON_TOOLTIP, "%s: %s" % (label, tooltip))
        gadget = self.AddCustomGui(gid, c4d.CUSTOMGUI_BITMAPBUTTON, label, c4d.BFH_CENTER, 0, 0, bc)
        if gadget is None:
            self.AddButton(gid, c4d.BFH_SCALEFIT, name=label)
        else:
            self.AddStaticText(gid + LABEL_OFFSET, c4d.BFH_CENTER, name=label)
        self.GroupEnd()

    def _enable_icon_button(self, gid, on):
        self.Enable(gid, on)
        self.Enable(gid + LABEL_OFFSET, on)

    def _add_type_button(self, gid, dtype):
        """標準デフォーマーのアイコンと名前。アイコンを押すと作成／切り替え（Shift＋クリックで追加）。"""
        self._add_icon_button(
            gid, dtype, c4d.GetObjectName(dtype),
            tr("メッシュ選択中は作成、PartDeform のデフォーマー選択中は切り替え。Shift＋クリックで同じ選択範囲に重ねて追加", "Creates on a selected mesh, switches the type on a selected PartDeform deformer. Shift+click to stack another deformer on the same selection"))

    def InitValues(self):
        # スライダーのドラッグ中: (欄のID, デフォーマー, {パラメーター: ドラッグ前の値}, ドラッグ前のシアーのずれ,
        #                        ドラッグ前のぼかしの幅)
        self._drag = None
        self._shown = {}  # 欄のID → 今出している (対象, 範囲, 単位, 値)
        self._pick_on = None  # 「起点」ボタンに今出しているオン／オフ
        self._set_row_gadget(G_SHIFT, 0.0, (-1.0, 1.0), core.UNIT_LENGTH)
        self._set_row_gadget(G_DIR, 0.0, core.DIRECTION_SLIDER, core.UNIT_ANGLE)
        self._set_row_gadget(G_FEATHER, 0.0, (0.0, 1.0), core.UNIT_LENGTH)
        self.update_target()
        # フローティング時にメインウィンドウの裏へ隠れないよう、窓の所有者を見張る（ドッキング・切り離しにも追従）
        winowner.keep_above_main(PANEL_TITLE)
        self._tick = 0
        self._badges_on = False
        self.SetTimer(100)  # Shift の目印を素早く出すため 0.1 秒ごと
        return True

    def Timer(self, msg):
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 5 == 0:
            winowner.keep_above_main(PANEL_TITLE)
        want = shift_down() and self._is_active()
        if want != getattr(self, "_badges_on", False):
            self._set_badges(want)
        # C4D のツールを直接切り替えたとき（移動ツールなど）も「起点」ボタンの表示を合わせる
        self._sync_pick_toggle()

    def _sync_pick_toggle(self, force=False):
        """「起点」ボタンの押し込み表示を、起点クリックのモード中かどうかに合わせる。"""
        on = pick_mode_on(c4d.documents.GetActiveDocument())
        if not force and on == getattr(self, "_pick_on", None):
            return
        self._pick_on = on
        gadget = self.FindCustomGui(G_PICK, c4d.CUSTOMGUI_BITMAPBUTTON)
        if gadget is not None:
            gadget.SetToggleState(on)
            gadget.Redraw()

    def _mouse_inside(self):
        """マウスがパネルの上にあるか（ドッキング中も使える判定）。"""
        bc = c4d.BaseContainer()
        if not self.GetInputState(c4d.BFM_INPUT_MOUSE, c4d.BFM_INPUT_MOUSELEFT, bc):
            return False
        x, y = bc.GetInt32(c4d.BFM_INPUT_X), bc.GetInt32(c4d.BFM_INPUT_Y)  # パネルの左上が原点
        dim = self.GetItemDim(1000)
        if not dim:
            return False
        return 0 <= x <= dim["x"] + dim["w"] and 0 <= y <= dim["y"] + dim["h"]

    def _is_active(self):
        """パネルがアクティブか: 浮いたパネルが前面の窓、またはマウスがパネルの上。"""
        return winowner.is_foreground(PANEL_TITLE) or self._mouse_inside()

    def _set_badges(self, on):
        """種類ボタンのアイコンを、通常／右下に緑の＋（Shift＋クリックで追加）に切り替える。"""
        self._badges_on = on
        for i, dtype in enumerate(core.DEFORMER_TYPES):
            gadget = self.FindCustomGui(G_TYPE_BASE + i, c4d.CUSTOMGUI_BITMAPBUTTON)
            bmp = icons.add_icon(dtype) if on else icons.normal_icon(dtype)
            if gadget is not None and bmp is not None:
                gadget.SetImage(bmp, True, False)
                gadget.Redraw()

    def _set_row_gadget(self, gid, value, slider_range, unit):
        lo, hi = slider_range
        # min/max はスライダーの範囲、min2/max2 は数値欄に入力できる範囲（属性マネージャーと同じく広め）。
        # 角度は値・範囲ともラジアンで渡し、表示は度（属性マネージャーと同じ 1° 刻み）
        if unit == core.UNIT_ANGLE:
            self.SetFloat(gid, value, min=lo, max=hi, step=math.radians(1.0), format=c4d.FORMAT_DEGREE,
                          min2=-1e9, max2=1e9)
        else:
            self.SetFloat(gid, value, min=lo, max=hi, step=0.1, format=c4d.FORMAT_METER, min2=-1e9, max2=1e9)

    def update_deformed_edit(self, doc):
        """アクティブなビューの「デフォーマ後に編集」の今の値を表示する（値は変えない）。"""
        bd = doc.GetActiveBaseDraw() if doc is not None else None
        self.Enable(G_DEFORMEDIT, bd is not None)
        if bd is not None:
            value = bool(bd[c4d.BASEDRAW_DATA_DEFORMEDEDIT])
            if self.GetBool(G_DEFORMEDIT) != value:
                self.SetBool(G_DEFORMEDIT, value)

    def update_target(self):
        doc = c4d.documents.GetActiveDocument()
        self.update_deformed_edit(doc)
        # ベベルには箱や向きがないので、起点と方向のボタンは使えなくする
        no_box = core.is_bevel(_target_or_none(doc)) if doc is not None else False
        for gid in (G_CYCLE, G_FLIP, G_ROT90, G_PICK, G_AUTO, G_REFIT):
            self._enable_icon_button(gid, not no_box)
        self.update_limit(doc)
        self._sync_pick_toggle()
        self.update_rows(doc)

    def update_limit(self, doc):
        """「選択範囲に限定」: PartDeform のデフォーマーを選んでいればその状態、いなければ作成時の既定値を表示する。
        ベベルは名前で限定するので常にオン（切り替えられない）。"""
        target = _target_or_none(doc) if doc is not None else None
        state = core.selection_limit(target) if target is not None else None
        if core.is_bevel(target) and not core.is_whole(target):
            value, enabled = True, False
        elif target is not None and core.is_whole(target):
            value, enabled = False, False  # 全体用は限定する選択範囲が無い
        elif state is None:
            value, enabled = limit_default(), True
        else:
            value, enabled = state, True
        self.Enable(G_LIMIT, enabled)
        if self.GetBool(G_LIMIT) != value:
            self.SetBool(G_LIMIT, value)

    def update_rows(self, doc):
        """数値欄（量・方向）を、選んでいるデフォーマーの種類に合わせて名前と単位を切り替えて表示する。"""
        if getattr(self, "_drag", None) is not None:
            return  # ドラッグ中はスライダーを書き換えない（つまみが飛ぶため）
        for gid in ROW_IDS:
            target, row = _row_target(doc, gid)
            if row is not None:
                label, unit, value, slider_range = row
            else:
                label, value = ROW_LABEL_NONE[gid], 0.0
                unit = core.UNIT_ANGLE if gid == G_DIR else core.UNIT_LENGTH
                slider_range = ROW_NONE_RANGE[gid]
            self.SetString(ROW_LABEL_ID[gid], label)
            self.Enable(gid, row is not None)
            self.Enable(ROW_LABEL_ID[gid], row is not None)
            # 入力中の値を上書きしないよう、対象・範囲・単位・値のどれかが変わったときだけ書き込む
            shown = self._shown.get(gid)
            if (shown is None or shown[0] != target or shown[1] != slider_range or shown[2] != unit
                    or abs(shown[3] - value) > 1e-6 or abs(self.GetFloat(gid) - value) > 1e-6):
                self._set_row_gadget(gid, value, slider_range, unit)
                self._shown[gid] = (target, slider_range, unit, value)

    def _on_row(self, doc, gid, msg):
        """数値欄のスライダー・数値欄。ドラッグ中はアンドゥを積まずに更新し、離したときにアンドゥ1回で確定する。"""
        value = self.GetFloat(gid)
        dragging = msg.GetBool(c4d.BFM_ACTION_INDRAG) if msg is not None else False
        if not dragging:
            self._finish_drag(doc, gid, value)
            return
        target, row = _row_target(doc, gid)
        if target is None:
            return
        if self._drag is None or self._drag[0] != gid or self._drag[1] != target:
            if self._drag is not None:
                self._finish_drag(doc)  # 別の欄のドラッグが確定されずに残っていたら先に確定する
            originals = {p: target[p] for p in ROW_PARAMS[gid](target)}
            keep_shift = core.shear_shift(target) if target.GetType() == c4d.Oshear else None
            self._drag = (gid, target, originals, keep_shift, core.feather_width(target))
        try:
            if gid == G_SHIFT:
                core.set_amount(doc, target, value, undo=False)
            elif gid == G_FEATHER:
                # 境目からの距離は最初に一度だけ測って使い回すので、ドラッグ中は重みを掛け直すだけ
                core.set_feather(doc, target, value, undo=False)
            else:
                # シアーはドラッグ前のずれを保つ（毎回いまのずれから換算すると誤差がたまる）
                core.set_direction(doc, target, value, undo=False, keep_shift=self._drag[3])
        except core.SDError as e:
            report(str(e), error=True)
            return
        # ドラッグ中は C4D のイベント処理が止まっていて EventAdd の再描画が離すまで遅れるので、
        # 属性マネージャーのスライダーと同じように、その場でシーンを評価して描き直す
        redraw_now()

    def _finish_drag(self, doc, gid=None, value=None):
        """ドラッグ中なら、ドラッグ前の値に戻してから最終値をアンドゥ1回分として入れる。
        gid を渡せばその欄の value を確定する（ドラッグでない入力もここを通る）。"""
        if self._drag is not None:
            drag_gid, target, originals, _, feather0 = self._drag
            self._drag = None
            if target.IsAlive():
                for param, original in originals.items():
                    target[param] = original
                if drag_gid == G_FEATHER:
                    try:
                        core.set_feather(doc, target, feather0, undo=False)  # ドラッグ前の頂点マップに戻す
                    except core.SDError:
                        pass
            if drag_gid != gid:
                ROW_APPLY[drag_gid](doc, self.GetFloat(drag_gid))
        if gid is not None:
            ROW_APPLY[gid](doc, value)

    def CoreMessage(self, mid, msg):
        if mid == c4d.EVMSG_CHANGE:
            if getattr(self, "_drag", None) is not None and not _mouse_left_down():
                # 離した通知が来なかったときの安全策: ボタンが離れていればここで確定する
                self._finish_drag(c4d.documents.GetActiveDocument())
            self.update_target()
        return gui.GeDialog.CoreMessage(self, mid, msg)

    def Command(self, cid, msg):
        doc = c4d.documents.GetActiveDocument()
        if G_TYPE_BASE <= cid < G_TYPE_BASE + len(core.DEFORMER_TYPES):
            qual = msg.GetInt32(c4d.BFM_ACTION_QUAL) if msg is not None else 0
            add = bool(qual & c4d.QSHIFT) or shift_down()
            do_type(doc, core.DEFORMER_TYPES[cid - G_TYPE_BASE], add=add)
        elif cid == G_CYCLE:
            do_reorient(doc, core.cycle_axis, tr("主軸を切り替えました。", "Switched the main axis."))
        elif cid == G_FLIP:
            do_reorient(doc, core.flip, tr("起点と先端を入れ替えました。", "Swapped the anchor and the tip."))
        elif cid == G_ROT90:
            do_reorient(doc, core.rotate90, tr("主軸まわりに90°回しました。", "Rotated 90° around the main axis."))
        elif cid == G_PICK:
            # もう一度押すと抜ける（押すたびにモードのオン／オフ）
            if pick_mode_on(doc):
                report(tr("起点の指定を終了しました。", "Finished setting the anchor."))
                end_pick_tool(doc)
            else:
                start_pick_tool(doc)
            # ボタンはクリックで見た目が自動で切り替わるので、実際のモードに合わせ直す（入れなかったときなど）
            self._sync_pick_toggle(force=True)
        elif cid == G_AUTO:
            do_reorient(doc, core.reset_auto, tr("向きを自動判定に戻しました。", "Reset the direction to automatic."))
        elif cid == G_REFIT:
            target = _target_or_none(doc)
            if target is not None and core.is_whole(target):
                do_reorient(doc, core.refit, tr("オブジェクト全体の今の形に合わせ直しました。", "Refitted to the current shape of the whole object."))
            else:
                do_reorient(doc, core.refit, tr("選択範囲に合わせ直しました。", "Refitted to the selection."))
        elif cid == G_FREEZE:
            do_freeze(doc)
        elif cid == G_RECAPTURE:
            do_recapture(doc)
        elif cid == G_LIMIT:
            do_limit(doc, self.GetBool(G_LIMIT))
        elif cid == G_DEFORMEDIT:
            set_deformed_edit(doc, self.GetBool(G_DEFORMEDIT))
        elif cid in ROW_IDS:
            self._on_row(doc, cid, msg)
            if self._drag is not None:
                return True  # ドラッグ中は表示の更新を省く
        self.update_target()
        return True


_panel = PartDeformPanel()


# ---------------------------------------------------------------------------
# 起点クリックツール
# ---------------------------------------------------------------------------
COLOR_ROOT = c4d.Vector(0.2, 0.9, 0.3)
COLOR_HOVER = c4d.Vector(1.0, 0.55, 0.0)


class PickRootTool(plugins.ToolData):
    def __init__(self):
        self.hover = None  # (axis, sign)

    def _target(self, doc):
        d = _target_or_none(doc)
        return None if core.is_bevel(d) else d  # ベベルには箱が無いので枠を描かない

    def GetState(self, doc):
        return c4d.CMD_ENABLED

    def KeyboardInput(self, doc, data, bd, win, msg):
        if msg[c4d.BFM_INPUT_CHANNEL] == c4d.KEY_ESC:
            self.hover = None
            report(tr("起点の指定を終了しました。", "Finished setting the anchor."))
            end_pick_tool(doc)
            return True
        return False

    def _face_at(self, doc, bd, x, y):
        """(対象のデフォーマー, マウスの下の端 (axis, sign))。対象のメッシュの外なら端は None。"""
        d = self._target(doc)
        if d is None:
            return None, None
        try:
            return d, core.face_from_view(d, bd, x, y, mesh_only=True)
        except Exception:
            return d, None

    def MouseInput(self, doc, data, bd, win, msg):
        """クリックした端を起点にし、モードはそのまま続ける（続けて別の端をクリックできる）。
        対象のメッシュの外（何もない所・ほかのオブジェクト）をクリックしたら、起点モードを抜ける。"""
        if msg[c4d.BFM_INPUT_CHANNEL] != c4d.BFM_INPUT_MOUSELEFT:
            return False
        d, face = self._face_at(doc, bd, msg[c4d.BFM_INPUT_X], msg[c4d.BFM_INPUT_Y])
        self.hover = None
        if face is None:
            report(tr("起点の指定を終了しました。", "Finished setting the anchor."))
            end_pick_tool(doc)
            return True
        if face == (1, -1):
            report(tr("そこは今の起点です。ほかの端をクリックしてください（対象の外をクリックか、もう一度「起点」で終了）。", "That is already the anchor. Click another side (click outside the object or press Anchor again to finish)."))
            return True
        try:
            core.set_root_face(doc, d, face[0], face[1])
            report(tr("起点を変更しました。続けてほかの端もクリックできます（対象の外をクリックか、もう一度「起点」で終了）。", "Anchor changed. You can keep clicking other sides (click outside the object or press Anchor again to finish)."))
        except core.SDError as e:
            report(str(e), error=True)
        show_in_attribute_manager(d)
        c4d.EventAdd()
        return True

    def GetCursorInfo(self, doc, data, bd, x, y, bc):
        if bc.GetId() == c4d.BFM_CURSORINFO_REMOVE:
            if self.hover is not None:
                self.hover = None
                c4d.DrawViews(c4d.DRAWFLAGS_ONLY_ACTIVE_VIEW | c4d.DRAWFLAGS_NO_THREAD | c4d.DRAWFLAGS_NO_ANIMATION)
            return True
        d, face = self._face_at(doc, bd, x, y)
        if face is None:
            # 対象の外: クリックすると抜けることを示す（オレンジの帯も出さない）
            bc.SetString(c4d.RESULT_BUBBLEHELP, tr("対象の外をクリックすると、起点の指定を終了します", "Click outside the object to finish setting the anchor"))
            bc.SetInt32(c4d.RESULT_CURSOR, c4d.MOUSE_NORMAL)
        else:
            bc.SetString(c4d.RESULT_BUBBLEHELP, tr("クリックでこの端を起点（効果0）に。続けて切り替えられます", "Click to make this side the anchor (no effect there). You can keep switching"))
            bc.SetInt32(c4d.RESULT_CURSOR, c4d.MOUSE_POINT_HAND)
        if face != self.hover:
            self.hover = face
            c4d.DrawViews(c4d.DRAWFLAGS_ONLY_ACTIVE_VIEW | c4d.DRAWFLAGS_NO_THREAD | c4d.DRAWFLAGS_NO_ANIMATION)
        return True

    def _band(self, d, axis, sign):
        """起点になる帯のポリゴン（変形前の点番号）。デフォーマーやメッシュが変わるまで使い回す。"""
        mesh = d.GetUp()
        key = (id(d), axis, sign, d.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX),
               mesh.GetDirty(c4d.DIRTYFLAGS_DATA) if mesh is not None else 0)
        cache = getattr(self, "_band_cache", None)
        if cache is None or cache[0] != key:
            try:
                polys, points = core.face_band(d, axis, sign)
            except core.SDError:
                polys, points = [], []
            self._band_cache = (key, polys, points)
            cache = self._band_cache
        return cache[1], cache[2]

    def _draw_band(self, bd, d, axis, sign, color, transparency, label):
        """起点になる帯を、変形後のメッシュの上に半透明の塗り＋太い外周線で描く（奥行き判定なしで手前に）。

        箱の面は変形前の位置にあるので、曲げた先などでは見当違いの場所に描かれる。
        実際の形の上で「どこが起点になるか」が分かるよう、メッシュそのものを塗る。
        """
        mesh = d.GetUp()
        if mesh is None:
            return
        polys, points = self._band(d, axis, sign)
        if not polys and not points:
            return
        cache = mesh.GetDeformCache()
        pts = cache.GetAllPoints() if cache is not None and cache.GetPointCount() == mesh.GetPointCount() else mesh.GetAllPoints()
        mg = mesh.GetMg()
        world = {}

        def wp(i):
            if i not in world:
                world[i] = mg * pts[i]
            return world[i]

        bd.SetMatrix_Matrix(None, c4d.Matrix())
        bd.SetDepth(False)
        try:
            bd.SetTransparency(-transparency)
            for ids in polys:
                bd.DrawPolygon([wp(i) for i in ids], [color] * len(ids))  # 2027 は引数2つ（点の数で三角／四角）
            bd.SetTransparency(0)
            # 帯の外周（1枚のポリゴンにしか属さないエッジ）を太い線で
            count = {}
            for ids in polys:
                for k in range(len(ids)):
                    e = tuple(sorted((ids[k], ids[(k + 1) % len(ids)])))
                    count[e] = count.get(e, 0) + 1
            bd.SetDrawParam(c4d.DRAW_PARAMETER_LINEWIDTH, 3.0)
            bd.SetPen(color)
            for (a, b), n in count.items():
                if n == 1:
                    bd.DrawLine(wp(a), wp(b), c4d.NOCLIP_Z)
            if not polys:
                try:  # 点だけの選択: 大きめの点で示す
                    bd.SetPointSize(8.0)
                    bd.SetPen(color)
                    bd.DrawPoints([wp(i) for i in points])
                except Exception:
                    pass
        finally:
            bd.SetTransparency(0)
            bd.SetDrawParam(c4d.DRAW_PARAMETER_LINEWIDTH, 1.0)
            bd.SetDepth(True)
        if label:
            ids = points or [i for p in polys for i in p]
            centre = sum((wp(i) for i in ids), c4d.Vector()) / max(len(ids), 1)
            sp = bd.WS(centre)
            try:
                bd.DrawHUDText(int(sp.x) + 10, int(sp.y) - 10, label)
            except Exception:
                pass

    def Draw(self, doc, data, bd, bh, bt, flags):
        d = self._target(doc)
        if d is None:
            return c4d.TOOLDRAW_NONE
        hovering_other = self.hover is not None and self.hover != (1, -1)
        # 今の起点（箱の底面側）は緑。マウスを重ねた面の側はオレンジで濃く塗って目立たせる
        self._draw_band(bd, d, 1, -1, COLOR_ROOT, 170 if hovering_other else 120, tr("今の起点", "Current anchor"))
        if hovering_other:
            self._draw_band(bd, d, self.hover[0], self.hover[1], COLOR_HOVER, 90, tr("ここを起点に", "Set anchor here"))
        return c4d.TOOLDRAW_NONE


# ---------------------------------------------------------------------------
# コマンド
# ---------------------------------------------------------------------------
class PanelCommand(plugins.CommandData):
    def Execute(self, doc):
        if _panel.IsOpen():
            _panel.update_target()
        open_panel()
        return True

    def RestoreLayout(self, sec_ref):
        return _panel.Restore(core.ID_PANEL, secret=sec_ref)


class TypeCommand(plugins.CommandData):
    def __init__(self, dtype):
        self.dtype = dtype

    def Execute(self, doc):
        open_panel()
        do_type(doc, self.dtype, add=shift_down())  # パレット等から Shift＋クリックでも追加
        return True


# ---------------------------------------------------------------------------
# 登録
# ---------------------------------------------------------------------------
# メニューは C4D 標準の「拡張」メニュー（プラグインフォルダごとのサブメニュー）に任せる。
# C4D 2027 の Python では SearchPluginMenuResource() が BaseContainer ではなく PyCapsule を返し、
# メニューを書き換えられないため、自前のサブメニューは作らない。
# メニューに出すのはパネルと種類の6個だけ（再フィット・フリーズ・起点はパネルから使う）。
def register():
    hide = 0
    ok = plugins.RegisterCommandPlugin(
        core.ID_PANEL, TITLE, hide, _icon(c4d.Obend),
        tr("PartDeform のパネルを開く", "Open the PartDeform panel"), PanelCommand())
    for dtype in core.DEFORMER_TYPES:
        name = c4d.GetObjectName(dtype)
        ok &= plugins.RegisterCommandPlugin(
            core.CMD_FOR_TYPE[dtype], tr("選択範囲に%s", "%s to Selection") % name, hide, _icon(dtype),
            tr("選択範囲に合わせて%sデフォーマーを置く（デフォーマー選択中は種類を切り替え）", "Place a %s deformer fitted to the selection (switches the type when a PartDeform deformer is selected)") % name,
            TypeCommand(dtype))
    ok &= _register_tool()
    if not ok:
        print(LOG_PREFIX + tr("一部のプラグインを登録できませんでした。", "Some plugins could not be registered."))
    return ok


def _register_tool():
    name = tr("PartDeform の起点", "PartDeform Anchor")
    help_text = tr("クリックした側を起点（効果0）にする", "Click a side to make it the anchor (no effect there)")
    errors = []
    # パネルの「起点」ボタンから使うので、拡張メニューには出さない
    for info in (getattr(c4d, "PLUGINFLAG_HIDEPLUGINMENU", 0), 0):
        try:
            if plugins.RegisterToolPlugin(core.ID_TOOL_PICK, name, info, _icon(12139), help_text, PickRootTool()):
                if errors:
                    print(LOG_PREFIX + tr("起点クリックツール: ", "Anchor tool: ") + " / ".join(errors))
                return True
            errors.append("info=%d: False" % info)
        except Exception as e:  # 登録の失敗理由をコンソールに残す
            errors.append("info=%d: %r" % (info, e))
    message = tr("起点クリックツールを登録できませんでした: ", "Could not register the anchor tool: ") + " / ".join(errors)
    print(LOG_PREFIX + message)
    try:  # 起動時のコンソールは後から読めないので、一時フォルダにも残す
        import os
        import tempfile

        with open(os.path.join(tempfile.gettempdir(), "partdeform_register.log"), "w", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass
    return False
