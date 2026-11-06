# -*- coding: utf-8 -*-
"""選択範囲デフォーマー: パネル・起点クリックツール・コマンド・メニュー。"""
import math

import c4d
from c4d import gui, plugins

from . import core
from . import icons
from . import winowner

TITLE = "選択範囲デフォーマー"
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
G_DEFORMEDIT = 1500
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
    (G_PICK, ICON_PICK, "起点", "ビューでクリックした端を起点（効果0）にする。続けて切り替えられる。"
                                "終了は対象の外をクリック・もう一度このボタン・ほかのボタン・Esc"),
    (G_FLIP, ICON_FLIP, "反転", "起点と先端を入れ替える"),
    (G_AUTO, ICON_AUTO, "自動", "向きと起点を自動判定に戻す"),
    (G_CYCLE, ICON_CYCLE, "主軸", "曲げる・ひねる軸（主軸）を、箱の別の軸に切り替える（起点は自動判定）"),
    (G_ROT90, ICON_ROT90, "90°回転", "主軸まわりに 90° 回す（曲げ・せん断の方向が変わる）"),
    (G_REFIT, ICON_REFIT, "フィット", "今の向きのまま、選択範囲タグに箱を合わせ直す（再フィット）"),
)

# 起点クリックツールを抜けたあとに戻すツール
_previous_tool = None


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
        d, how = core.create_or_switch(doc, dtype, add=add)
        if how == "add":
            report("%s を追加しました（%s と同じ選択範囲・向きで重ねました）。" % (d.GetName(), previous_name))
        elif how == "create" and core.is_bevel(d):
            # ベベルは選択範囲タグの名前で限定するので、タグを持たない子オブジェクトには効かない
            report("%s を作成しました。オフセットはパネルの量の欄か属性マネージャーで調整できます。" % d.GetName())
        elif how == "create":
            message = "%s を作成しました。向きが違うときは「起点と方向」のボタン（「起点」でクリック指定）で直せます。" % d.GetName()
            children = core.affected_children(d.GetUp())
            if children:
                names = "」「".join(c.GetName() for c in children[:3]) + ("」ほか" if len(children) > 3 else "」")
                report("%s を作成しました。子オブジェクト「%sも一緒に変形します（フィールドの変数タグは、タグを持たない子を除外できません）。"
                       % (d.GetName(), names), error=True)
            else:
                report(message)
        else:
            report("%s に切り替えました。" % name)
        return d

    return _run(doc, None, work)


def do_reorient(doc, func, label):
    leave_pick_mode(doc)
    return _run(doc, label, lambda: func(doc, core.edit_target(doc)))


def do_recapture(doc):
    """選択中の選択範囲デフォーマー（またはメッシュの下にただ1つあるもの）の選択範囲を、メッシュの今の選択で取り直す。"""
    leave_pick_mode(doc)

    def work():
        try:
            target = core.edit_target(doc)
        except core.SDError:
            raise core.SDError("選択を取り直すデフォーマーを選んでください（メッシュで選択し直したあと、オブジェクトマネージャーでデフォーマーをクリック）。")
        d, tag = core.recapture_selection(doc, target)
        shared = [x for x in core.sd_deformers_under(d.GetUp()) if x != d and core.get_selection_tag(x) == tag]
        note = "（同じタグを使う %d 個も合わせ直しました）" % len(shared) if shared else ""
        report("%s の選択範囲を取り直しました（タグ「%s」）%s。向きと起点は自動判定し直したので、違うときは「起点と方向」のボタンで直せます。"
               % (d.GetName(), tag.GetName(), note))
        return d

    return _run(doc, None, work)


def do_freeze(doc):
    leave_pick_mode(doc)

    def work():
        targets = core.freeze_targets(doc)
        meshes = core.freeze(doc, targets)
        report("%d 個のデフォーマーをフリーズしました（%s）。" % (len(targets), "、".join(m.GetName() for m in meshes)))
        return meshes

    return _run(doc, None, work)


# パネルの数値欄（2段）。選んでいるデフォーマーの種類で、名前と単位（長さ／角度）が切り替わる
AMOUNT_LABEL_NONE = "量（選択範囲デフォーマーを選ぶと使えます）"
DIRECTION_LABEL_NONE = "角度（屈曲・シアーで使えます）"
ROW_LABEL_ID = {G_SHIFT: G_SHIFT_LABEL, G_DIR: G_DIR_LABEL}
ROW_LABEL_NONE = {G_SHIFT: AMOUNT_LABEL_NONE, G_DIR: DIRECTION_LABEL_NONE}
ROW_CONTENT = {G_SHIFT: core.amount_row, G_DIR: core.direction_row}
ROW_PARAMS = {G_SHIFT: core.amount_params, G_DIR: core.direction_params}


def _row_target(doc, gid):
    """数値欄 gid の対象と中身: (デフォーマー, (名前, 単位, 値, スライダー範囲))。使えなければ (None, None)。

    対象は選択中、または選択オブジェクト直下にただ1つある選択範囲デフォーマー。
    ベベルのオフセットモードが「比例」のときは長さではないので量の欄は使えない。
    """
    d = _target_or_none(doc) if doc is not None else None
    row = ROW_CONTENT[gid](d) if d is not None else None
    return (d, row) if row is not None else (None, None)


def set_deformed_edit(doc, on):
    """アクティブなビューの「デフォーマ後に編集」を切り替える（ビューの表示メニューと同じ設定を書き換えるだけ）。"""
    bd = doc.GetActiveBaseDraw() if doc is not None else None
    if bd is None:
        report("アクティブなビューがありません。", error=True)
        return
    bd[c4d.BASEDRAW_DATA_DEFORMEDEDIT] = bool(on)
    c4d.EventAdd()
    report("デフォーマ後に編集を%sにしました（アクティブなビュー）。" % ("オン" if on else "オフ"))


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
            raise core.SDError("選択範囲デフォーマーを選択してください（ベベルはオフセットモードが「比例」以外のとき）。")
        core.set_amount(doc, d, value)
        label, unit = row[0], row[1]
        if core.is_bevel(d):
            report("%s を %s にしました。" % (label, format_length(d[c4d.O_BEVEL_RADIUS])))
        elif unit == core.UNIT_ANGLE:
            report("%s を %s にしました。" % (label, format_angle(value)))
        else:
            report("%s を %s にしました（強度 %.1f%%）。" % (label, format_length(value), d[c4d.DEFORMOBJECT_STRENGTH] * 100.0))
        return d

    return _run(doc, None, work)


def do_direction(doc, value):
    """2段目（方向）の確定。屈曲・シアーの角度。シアーは先端のずれが変わらないよう強度も換算する。アンドゥ1回。"""
    def work():
        d, row = _row_target(doc, G_DIR)
        if d is None:
            raise core.SDError("屈曲かシアーの選択範囲デフォーマーを選択してください。")
        core.set_direction(doc, d, value)
        if d.GetType() == c4d.Oshear:
            report("%s を %s にしました（先端のずれ %s、強度 %.1f%%）。" % (
                row[0], format_angle(value), format_length(core.shear_shift(d)), d[c4d.DEFORMOBJECT_STRENGTH] * 100.0))
        else:
            report("%s を %s にしました。" % (row[0], format_angle(value)))
        return d

    return _run(doc, None, work)


ROW_APPLY = {G_SHIFT: do_amount, G_DIR: do_direction}


def show_in_attribute_manager(obj):
    """属性マネージャーをオブジェクトモードにして obj を表示する（ツールの設定画面にしない）。"""
    if obj is None:
        return
    try:
        gui.ActiveObjectManager_SetObject(
            c4d.ACTIVEOBJECTMODE_OBJECT, obj, c4d.ACTIVEOBJECTMANAGER_SETOBJECTS_OPEN, c4d.DescID())
    except Exception as e:  # 表示の切り替えに失敗しても操作は続ける
        print(LOG_PREFIX + "属性マネージャーを切り替えられませんでした: %r" % e)


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
            raise core.SDError("ベベルには箱や向きがないので、起点の指定はありません。")
    except core.SDError as e:
        report(str(e), error=True)
        return
    current = doc.GetAction()
    if current != core.ID_TOOL_PICK:
        _previous_tool = current
    doc.SetAction(core.ID_TOOL_PICK)
    show_in_attribute_manager(target)
    report("起点（効果0）にしたい端をクリックしてください。続けて切り替えられます。"
           "終了は、対象の外をクリック・もう一度「起点」・ほかのボタン・Esc。")
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
class SelectionDeformerPanel(gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle(TITLE)
        self.GroupBegin(1000, c4d.BFH_SCALEFIT | c4d.BFV_TOP, cols=1)
        self.GroupBorderSpace(6, 6, 6, 6)
        self.GroupSpace(4, 4)

        self.AddStaticText(0, c4d.BFH_LEFT, name="種類（作成／切り替え）")
        self.GroupBegin(1001, c4d.BFH_SCALEFIT, cols=len(core.DEFORMER_TYPES))
        self.GroupSpace(2, 2)
        for i, dtype in enumerate(core.DEFORMER_TYPES):
            self._add_type_button(G_TYPE_BASE + i, dtype)
        self.GroupEnd()

        # 1段目＝量: シアー・テーパー・膨張の強度（%）は実際に動く量（長さ）、ベベルはオフセット、
        # 屈曲は強度（曲げる角度）、ツイストは角度（ひねる角度）。属性マネージャーと同じ「数値欄＋スライダー」
        self.AddStaticText(G_SHIFT_LABEL, c4d.BFH_SCALEFIT, name=AMOUNT_LABEL_NONE)
        self.AddEditSlider(G_SHIFT, c4d.BFH_SCALEFIT)
        # 2段目＝方向: 屈曲・シアーの角度（曲げる向き・ずらす向き）
        self.AddStaticText(G_DIR_LABEL, c4d.BFH_SCALEFIT, name=DIRECTION_LABEL_NONE)
        self.AddEditSlider(G_DIR, c4d.BFH_SCALEFIT)

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="起点と方向")
        self.GroupBegin(1002, c4d.BFH_SCALEFIT, cols=len(ORIENT_BUTTONS))  # 横1列
        self.GroupSpace(2, 2)  # 種類ボタンと同じ間隔
        for gid, icon, label, tip in ORIENT_BUTTONS:
            # 「起点」はモードのオン／オフが見えるようトグル表示（押すたびにモードに入る／抜ける）
            self._add_icon_button(gid, icon, label, tip, toggle=(gid == G_PICK))
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.GroupBegin(1003, c4d.BFH_SCALEFIT, cols=2)
        self.GroupSpace(2, 4)
        self._add_icon_button(G_RECAPTURE, ICON_RECAPTURE, "選択を取り直す",
                              "メッシュの今の選択（今のモード）で選択範囲タグを取り直し、向きと起点も自動判定し直す")
        self._add_icon_button(G_FREEZE, ICON_FREEZE, "フリーズ",
                              "変形をポリゴンに書き込み、デフォーマーとプラグイン製の選択範囲タグを消す（アンドゥ1回で戻る）")
        self.GroupEnd()

        # ビューの「表示 ＞ デフォーマ後に編集」と同じ設定（アクティブなビュー）。パネルは値を読み書きするだけ
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddCheckbox(G_DEFORMEDIT, c4d.BFH_LEFT, 0, 0, name="デフォーマ後に編集（アクティブなビュー）")
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
            "メッシュ選択中は作成、選択範囲デフォーマー選択中は切り替え。Shift＋クリックで同じ選択範囲に重ねて追加")

    def InitValues(self):
        # スライダーのドラッグ中: (欄のID, デフォーマー, {パラメーター: ドラッグ前の値}, ドラッグ前のシアーのずれ)
        self._drag = None
        self._shown = {}  # 欄のID → 今出している (対象, 範囲, 単位, 値)
        self._pick_on = None  # 「起点」ボタンに今出しているオン／オフ
        self._set_row_gadget(G_SHIFT, 0.0, (-1.0, 1.0), core.UNIT_LENGTH)
        self._set_row_gadget(G_DIR, 0.0, core.DIRECTION_SLIDER, core.UNIT_ANGLE)
        self.update_target()
        # フローティング時にメインウィンドウの裏へ隠れないよう、窓の所有者を見張る（ドッキング・切り離しにも追従）
        winowner.keep_above_main(TITLE)
        self._tick = 0
        self._badges_on = False
        self.SetTimer(100)  # Shift の目印を素早く出すため 0.1 秒ごと
        return True

    def Timer(self, msg):
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 5 == 0:
            winowner.keep_above_main(TITLE)
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
        return winowner.is_foreground(TITLE) or self._mouse_inside()

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
        self._sync_pick_toggle()
        self.update_rows(doc)

    def update_rows(self, doc):
        """数値欄（量・方向）を、選んでいるデフォーマーの種類に合わせて名前と単位を切り替えて表示する。"""
        if getattr(self, "_drag", None) is not None:
            return  # ドラッグ中はスライダーを書き換えない（つまみが飛ぶため）
        for gid in (G_SHIFT, G_DIR):
            target, row = _row_target(doc, gid)
            if row is not None:
                label, unit, value, slider_range = row
            else:
                label, value = ROW_LABEL_NONE[gid], 0.0
                unit = core.UNIT_ANGLE if gid == G_DIR else core.UNIT_LENGTH
                slider_range = core.DIRECTION_SLIDER if gid == G_DIR else (-1.0, 1.0)
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
            self._drag = (gid, target, originals, keep_shift)
        try:
            if gid == G_SHIFT:
                core.set_amount(doc, target, value, undo=False)
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
            drag_gid, target, originals, _ = self._drag
            self._drag = None
            if target.IsAlive():
                for param, original in originals.items():
                    target[param] = original
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
            do_reorient(doc, core.cycle_axis, "主軸を切り替えました。")
        elif cid == G_FLIP:
            do_reorient(doc, core.flip, "起点と先端を入れ替えました。")
        elif cid == G_ROT90:
            do_reorient(doc, core.rotate90, "主軸まわりに90°回しました。")
        elif cid == G_PICK:
            # もう一度押すと抜ける（押すたびにモードのオン／オフ）
            if pick_mode_on(doc):
                report("起点の指定を終了しました。")
                end_pick_tool(doc)
            else:
                start_pick_tool(doc)
            # ボタンはクリックで見た目が自動で切り替わるので、実際のモードに合わせ直す（入れなかったときなど）
            self._sync_pick_toggle(force=True)
        elif cid == G_AUTO:
            do_reorient(doc, core.reset_auto, "向きを自動判定に戻しました。")
        elif cid == G_REFIT:
            do_reorient(doc, core.refit, "選択範囲に合わせ直しました。")
        elif cid == G_FREEZE:
            do_freeze(doc)
        elif cid == G_RECAPTURE:
            do_recapture(doc)
        elif cid == G_DEFORMEDIT:
            set_deformed_edit(doc, self.GetBool(G_DEFORMEDIT))
        elif cid in (G_SHIFT, G_DIR):
            self._on_row(doc, cid, msg)
            if self._drag is not None:
                return True  # ドラッグ中は表示の更新を省く
        self.update_target()
        return True


_panel = SelectionDeformerPanel()


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
            report("起点の指定を終了しました。")
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
            report("起点の指定を終了しました。")
            end_pick_tool(doc)
            return True
        if face == (1, -1):
            report("そこは今の起点です。ほかの端をクリックしてください（対象の外をクリックか、もう一度「起点」で終了）。")
            return True
        try:
            core.set_root_face(doc, d, face[0], face[1])
            report("起点を変更しました。続けてほかの端もクリックできます（対象の外をクリックか、もう一度「起点」で終了）。")
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
            bc.SetString(c4d.RESULT_BUBBLEHELP, "対象の外をクリックすると、起点の指定を終了します")
            bc.SetInt32(c4d.RESULT_CURSOR, c4d.MOUSE_NORMAL)
        else:
            bc.SetString(c4d.RESULT_BUBBLEHELP, "クリックでこの端を起点（効果0）に。続けて切り替えられます")
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
        self._draw_band(bd, d, 1, -1, COLOR_ROOT, 170 if hovering_other else 120, "今の起点")
        if hovering_other:
            self._draw_band(bd, d, self.hover[0], self.hover[1], COLOR_HOVER, 90, "ここを起点に")
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


class RefitCommand(plugins.CommandData):
    def Execute(self, doc):
        open_panel()
        do_reorient(doc, core.refit, "選択範囲に合わせ直しました。")
        return True


class FreezeCommand(plugins.CommandData):
    def Execute(self, doc):
        open_panel()
        do_freeze(doc)
        return True


# ---------------------------------------------------------------------------
# 登録
# ---------------------------------------------------------------------------
# メニューは C4D 標準の「拡張」メニュー（プラグインフォルダごとのサブメニュー）に任せる。
# C4D 2027 の Python では SearchPluginMenuResource() が BaseContainer ではなく PyCapsule を返し、
# メニューを書き換えられないため、自前のサブメニューは作らない。
def register():
    hide = 0
    ok = plugins.RegisterCommandPlugin(
        core.ID_PANEL, TITLE + "パネル", hide, _icon(c4d.Obend),
        "選択範囲デフォーマーのパネルを開く", PanelCommand())
    for dtype in core.DEFORMER_TYPES:
        name = c4d.GetObjectName(dtype)
        ok &= plugins.RegisterCommandPlugin(
            core.CMD_FOR_TYPE[dtype], "選択範囲に%s" % name, hide, _icon(dtype),
            "選択範囲に合わせて%sデフォーマーを置く（デフォーマー選択中は種類を切り替え）" % name,
            TypeCommand(dtype))
    ok &= plugins.RegisterCommandPlugin(
        core.ID_CMD_REFIT, "選択範囲デフォーマーを再フィット", hide, _icon(13038),
        "今の向きのまま、選択範囲タグに箱を合わせ直す", RefitCommand())
    ok &= plugins.RegisterCommandPlugin(
        core.ID_CMD_FREEZE, "選択範囲デフォーマーをフリーズ", hide, _icon(12233),
        "変形をポリゴンに書き込み、デフォーマーとプラグイン製の選択範囲タグを消す", FreezeCommand())
    ok &= _register_tool()
    if not ok:
        print(LOG_PREFIX + "一部のプラグインを登録できませんでした。")
    return ok


def _register_tool():
    name = "選択範囲デフォーマーの起点をクリック"
    help_text = "クリックした側を起点（効果0）にする"
    errors = []
    for info in (0,):
        try:
            if plugins.RegisterToolPlugin(core.ID_TOOL_PICK, name, info, _icon(12139), help_text, PickRootTool()):
                if errors:
                    print(LOG_PREFIX + "起点クリックツール: " + " / ".join(errors))
                return True
            errors.append("info=%d: False" % info)
        except Exception as e:  # 登録の失敗理由をコンソールに残す
            errors.append("info=%d: %r" % (info, e))
    message = "起点クリックツールを登録できませんでした: " + " / ".join(errors)
    print(LOG_PREFIX + message)
    try:  # 起動時のコンソールは後から読めないので、一時フォルダにも残す
        import os
        import tempfile

        with open(os.path.join(tempfile.gettempdir(), "seldeform_register.log"), "w", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass
    return False
