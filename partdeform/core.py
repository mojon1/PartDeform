# -*- coding: utf-8 -*-
"""PartDeform: コア処理（Cinema 4D 2027）

標準デフォーマー（屈曲・シアー・テーパー・ツイスト・膨張・ベベル）を、
選択範囲に合わせた大きさと向きで、編集可能なポリゴンオブジェクトの子に置く。

- 影響範囲は、デフォーマーのフィールドに入れた「変数タグ」レイヤー（FLweight）で、
  プラグインが作った選択範囲タグに絞る（選択範囲タグを手でフィールドに入れたのと同じ形）。
  注意: FLweight は、そのタグを持たないオブジェクト（メッシュの子など）には重み1を返すので、
  メッシュに子オブジェクトがあると子まで変形する（C4D 標準の挙動）。affected_children() で検出して知らせる。
  昔の「制限」タグはレガシー扱いなので使わない（旧版で作ったデフォーマーの読み取りだけ対応）。
  「選択範囲に限定」をオフにすると、このレイヤーの「有効」をオフにする（レイヤーとタグは残す）。
  フィールドが効かないので標準のデフォーマーと同じ動きになり、パイプの一部を曲げると先の部分も付いてくる。
- 何も選んでいない・モデルモードなど・メッシュになっていないオブジェクト（プリミティブ、ジェネレーター、
  ヌルのグループ）では「全体用」にする。選択範囲タグもフィールドのレイヤーも入れず（全選択のタグは
  変形の結果を変えないうえ、あとで足したポリゴンが漏れる）、箱を子も含めた今の形に合わせるだけ。
  印に MK_WHOLE を立てて、一部用と見分ける。
- 標準デフォーマーは箱の底面（ローカル -Y）で効果0、上面で最大（膨張は両端0）。
  そこで箱の底面を選択範囲の「起点」に合わせる。
- プラグインが作ったデフォーマー／タグには、BaseContainer の ID_MARKER に印を残す。
  プラグインが無い環境でも、標準のデフォーマーとタグとしてそのまま動く。
"""
import heapq
import math

import c4d

from .i18n import tr

# ---------------------------------------------------------------------------
# プラグインID（すべて Maxon で登録した正式なID。右のコメントは登録時のラベル）
# ---------------------------------------------------------------------------
ID_PANEL = 1073413  # PartDeform（本体。パネルを開くコマンド）
ID_CMD_BEND = 1073415  # PartDeformBend
ID_CMD_SHEAR = 1073416  # PartDeformShear
ID_CMD_TAPER = 1073417  # PartDeformTaper
ID_CMD_TWIST = 1073418  # PartDeformTwist
ID_CMD_BULGE = 1073419  # PartDeformBulge
ID_CMD_BEVEL = 1073420  # PartDeformBevel
ID_TOOL_PICK = 1073421  # PartDeformAnchor（起点クリックのツール。メニューには出さない）
# 印を入れる BaseContainer のキー。登録済みのIDなら他のプラグインと重ならないので、本体のIDを使う
ID_MARKER = ID_PANEL
# 試作版（テスト用ID）で作ったシーンの印のキー。読むときだけ見る（自分の印の形のときだけ印とみなす）
ID_MARKER_LEGACY = 1000010

# 印（サブコンテナ）の中身
MK_KIND = 1
MK_TAG = 2
MK_VERSION = 3
MK_WHOLE = 4  # True: オブジェクト全体にかける「全体用」（選択範囲タグもフィールドのレイヤーも持たない）
MK_FEATHER = 5  # 境目のぼかしの幅（長さ）。0 または無しならぼかさない
MK_FEATHER_TAG = 6  # ぼかしの頂点マップタグ（リンク）
KIND_DEFORMER = 1
KIND_TAG = 2
KIND_FEATHER = 3  # ぼかしの頂点マップタグ
MARKER_VERSION = 1

# 扱うデフォーマーの種類（パネルとメニューの並び順）
# BOX_TYPES: 箱で効く範囲を決め、フィールドで選択範囲に限定する種類
# ベベル: 箱もフィールドも無く、自分の「選択範囲」欄にタグの名前を入れて限定する（トポロジーが変わる）
BOX_TYPES = (c4d.Obend, c4d.Oshear, c4d.Otaper, c4d.Otwist, c4d.Obulge)
DEFORMER_TYPES = BOX_TYPES + (c4d.Obevel,)
CMD_FOR_TYPE = {
    c4d.Obend: ID_CMD_BEND,
    c4d.Oshear: ID_CMD_SHEAR,
    c4d.Otaper: ID_CMD_TAPER,
    c4d.Otwist: ID_CMD_TWIST,
    c4d.Obulge: ID_CMD_BULGE,
    c4d.Obevel: ID_CMD_BEVEL,
}

# ベベル
BEVEL_SELECTION = 2007  # O_BEVEL_RESTRICTION_START。中身はタグの「名前」の文字列（リンクを入れても効かない）
BEVEL_MODE_FOR_TAG = {  # 選択範囲タグの種類 → ベベルのコンポーネントモード
    c4d.Tpointselection: 0,
    c4d.Tedgeselection: 1,
    c4d.Tpolygonselection: 2,
}
BEVEL_TOOL_MODE = {  # コンポーネントモード → ベベルツールのモデリングモード
    0: c4d.MODELINGCOMMANDMODE_POINTSELECTION,
    1: c4d.MODELINGCOMMANDMODE_EDGESELECTION,
    2: c4d.MODELINGCOMMANDMODE_POLYGONSELECTION,
}
# ベベルデフォーマーとベベルツール（ID_XBEVELTOOL）で番号が同じパラメーター（フリーズでツールに渡す）
BEVEL_TOOL_PARAMS = (1001, 1002, 1003, 1004, 1005, 1100, 1101, 1102, 1103, 1201, 1202, 1203, 1204,
                     1205, 1206, 1207, 1208, 1301, 1302, 1303, 1304, 1305, 1306, 1307)
BEVEL_DEFAULT_RATIO = 0.03  # 作成時のオフセット（選択範囲の最大辺に対する割合）
BEVEL_OFFSET_PROPORTIONAL = 2  # オフセットモード「比例」（オフセットが長さではなくなる）
BEVEL_MODE_EDGES = 1  # ベベルのコンポーネントモード「エッジ」
# 全体用のベベル: 標準のベベルデフォーマーの既定と同じく、隣の面との角度がこれ以上の角だけ丸める
# （分割された平らな面の中のエッジまで丸めないため）
BEVEL_WHOLE_ANGLE = math.radians(40.0)
# 全体用のベベルをフリーズするとき、隣の面が無い外周のエッジも丸めるか。デフォーマーは「角度を使う」のとき
# 外周を丸めない（C4D 2027 で、分割した平面が変わらないことを確認）ので、それに合わせる
BEVEL_WHOLE_BOUNDARY = False

# モード。ポイント・エッジ・ポリゴンのモードで何か選んでいれば、その部分にかける。それ以外は全体用
COMPONENT_MODES = (c4d.Mpoints, c4d.Medges, c4d.Mpolygons)

# 作成時の強さ（向きがすぐ分かるように少しだけ効かせる）。シアーは default_amount() で箱から計算する
DEFAULT_AMOUNT = {
    c4d.Obend: math.radians(45.0),
    c4d.Otwist: math.radians(45.0),
    c4d.Oshear: 0.3,
    c4d.Otaper: 0.3,
    c4d.Obulge: 0.3,
}
# シアーの作成時のずれ量（主軸方向の長さに対する割合）
SHEAR_DEFAULT_SHIFT = 0.2
# 「強さ」に当たるパラメーター（ツイストだけ「角度」が強さ）
AMOUNT_PARAM = {
    c4d.Obend: c4d.DEFORMOBJECT_STRENGTH,
    c4d.Otwist: c4d.DEFORMOBJECT_ANGLE,
    c4d.Oshear: c4d.DEFORMOBJECT_STRENGTH,
    c4d.Otaper: c4d.DEFORMOBJECT_STRENGTH,
    c4d.Obulge: c4d.DEFORMOBJECT_STRENGTH,
    c4d.Obevel: c4d.O_BEVEL_RADIUS,
}
# 種類を切り替えるとき、単位が同じもの同士だけ強さを引き継ぐ
# （シアーの % は箱の X 幅に対する割合で、テーパー・膨張の % とは意味が違うので引き継がない）
AMOUNT_UNIT = {
    c4d.Obend: "angle",
    c4d.Otwist: "angle",
    c4d.Oshear: "shear",
    c4d.Otaper: "ratio",
    c4d.Obulge: "ratio",
    c4d.Obevel: "bevel",
}
# DEFORMOBJECT_ANGLE が「曲げ・せん断の方向」を表す種類
DIRECTION_ANGLE_TYPES = (c4d.Obend, c4d.Oshear)

SELTAG_BASENAME = "PD_Sel"
FEATHER_BASENAME = "PD_Feather"  # ぼかしの頂点マップタグの名前

# 自動判定のしきい値
COHERENCE_SURFACE = 0.5  # 平均法線の揃い具合。これ以上なら「面」として扱う
THICKNESS_RATIO = 0.3  # 法線方向の厚み / 面内の長さ。これ以上なら法線を主軸にする
END_BAND = 0.1  # 起点判定で「端」とみなす範囲（主軸方向の長さに対する割合）
ROOT_TIE_RATIO = 0.01  # 両端とオブジェクトの中心との距離の差がこの割合（主軸方向の長さに対する）以下なら同じとみなす
BOUNDARY_OFFSET_RATIO = 0.1  # 境目→遠い部分のずれが、選択範囲の対角のこの割合未満なら方向なしとみなす
SNAP_ANGLE = 15.0  # 自動の主軸を、オブジェクトの軸や形の主軸に揃える角度
EDGE_ALIGN_MIN = 0.3  # エッジの向きがこの割合以上そろっていれば、面の中の向き・H 角度をエッジの流れに合わせる
MIN_SIZE_RATIO = 0.05  # 薄い軸の箱サイズの下限（最大辺に対する割合）
EPS = 1e-9


class SDError(Exception):
    """ユーザーに見せるエラー（日本語メッセージ）。"""


def _stop_threads():
    """シーンを書き換える前に、ビューの描画など裏のスレッドを止める。

    止めずにトポロジーを変えたりオブジェクトを消したりすると、描画スレッドが消えかけのデータを
    読んで C4D ごと落ちることがある（2026-11-06、ベベルのフリーズを含むテストで実際に落ちた）。
    """
    c4d.StopAllThreads()


# ---------------------------------------------------------------------------
# 印
# ---------------------------------------------------------------------------
def _marker(node):
    if node is None:
        return None
    bc = node.GetDataInstance()
    if bc is None:
        return None
    sub = bc.GetContainerInstance(ID_MARKER)
    if sub is None:
        # 試作版で作ったデフォーマー／タグ。テスト用IDはほかの開発中のプラグインも使いうるので、
        # 中身が自分の印の形（種類と版）のときだけ印とみなす
        old = bc.GetContainerInstance(ID_MARKER_LEGACY)
        if (old is not None and old.GetInt32(MK_VERSION) == MARKER_VERSION
                and old.GetInt32(MK_KIND) in (KIND_DEFORMER, KIND_TAG)):
            sub = old
    return sub


def is_marked(node, kind=None):
    sub = _marker(node)
    if sub is None:
        return False
    k = sub.GetInt32(MK_KIND)
    if kind is None:
        return k in (KIND_DEFORMER, KIND_TAG, KIND_FEATHER)
    return k == kind


def is_sd_deformer(obj):
    return (
        obj is not None
        and isinstance(obj, c4d.BaseObject)
        and obj.GetType() in DEFORMER_TYPES
        and is_marked(obj, KIND_DEFORMER)
    )


def _set_marker(node, kind, tag=None, whole=False, feather=None):
    """印を書く。feather=(幅, 頂点マップ) でぼかしを入れる。None なら、node に今あるぼかしの情報を残す
    （選択の取り直しなどで印を書き直しても、ぼかしが消えないように）。消すときは (0.0, None)。"""
    if feather is None and kind == KIND_DEFORMER:
        feather = (feather_width(node), feather_tag(node))
    bc = node.GetDataInstance()
    sub = c4d.BaseContainer()
    sub.SetInt32(MK_KIND, kind)
    sub.SetInt32(MK_VERSION, MARKER_VERSION)
    if tag is not None:
        sub.SetLink(MK_TAG, tag)
    if whole:
        sub.SetBool(MK_WHOLE, True)
    if feather is not None and feather[0] > 0.0 and feather[1] is not None:
        sub.SetFloat(MK_FEATHER, feather[0])
        sub.SetLink(MK_FEATHER_TAG, feather[1])
    bc.SetContainer(ID_MARKER, sub)


def feather_width(deformer):
    """境目のぼかしの幅（長さ）。ぼかしていなければ 0。"""
    sub = _marker(deformer)
    if sub is None or feather_tag(deformer) is None:
        return 0.0
    return max(sub.GetFloat(MK_FEATHER), 0.0)


def feather_tag(deformer):
    """ぼかしの頂点マップタグ（親メッシュのもの）。無ければ None。"""
    sub = _marker(deformer)
    if sub is None or deformer is None:
        return None
    vmap = sub.GetLink(MK_FEATHER_TAG, deformer.GetDocument())
    parent = deformer.GetUp()
    if vmap is None or parent is None or vmap.GetType() != c4d.Tvertexmap or vmap.GetObject() != parent:
        return None
    return vmap


def is_whole(deformer):
    """オブジェクト全体にかける「全体用」のデフォーマーか（選択範囲タグを持たない）。"""
    sub = _marker(deformer)
    return sub is not None and sub.GetBool(MK_WHOLE)


WHOLE_LABEL = tr("全体", "Whole")  # 全体用のデフォーマーの名前の [ ] の中


SELECTION_TAG_TYPES = (c4d.Tpolygonselection, c4d.Tpointselection)  # フィールド（箱の種類）で使えるタグ


def _iter_layers(layer):
    while layer:
        yield layer
        for sub in _iter_layers(layer.GetDown()):
            yield sub
        layer = layer.GetNext()


def weight_layer_targets(deformer, doc=None):
    """フィールドの変数タグレイヤーが指しているもの（タグ等）のリスト。

    deformer[c4d.FIELDS] は一時的なコピーで、関数を抜けると中のレイヤーも消えるので、
    リンク先はここで解決して返す。
    """
    fl = deformer[c4d.FIELDS]
    if fl is None:
        return []
    root = fl.GetLayersRoot()
    if root is None:
        return []
    doc = doc or deformer.GetDocument()
    return [l.GetLinkedObject(doc) for l in _iter_layers(root.GetDown()) if l.GetType() == c4d.FLweight]


def _new_weight_layer(tag, enabled=True):
    layer = c4d.modules.mograph.FieldLayer(c4d.FLweight)
    if layer is None or not layer.SetLinkedObject(tag):
        raise SDError(tr("選択範囲タグをフィールドに入れられませんでした。", "Could not add the selection tag to the deformer's Fields."))
    layer.SetChannelFlag(c4d.FIELDLAYER_CHANNELFLAG_ENABLE, bool(enabled))
    return layer


def make_field_list(tag, limit=True):
    """選択範囲タグを入れた「変数タグ」レイヤーだけのフィールドリスト。

    limit=False（選択範囲に限定しない）でもレイヤーは入れ、「有効」をオフにしておく。
    タグとのつながりが残るので、あとから属性マネージャーやパネルでオンにでき、
    種類の切り替え・選択の取り直し・フリーズもいつもどおりタグを見つけられる。
    """
    fl = c4d.FieldList()
    fl.InsertLayer(_new_weight_layer(tag, limit))
    return fl


def _weight_layers(fl, tag, doc):
    """フィールドリスト fl の中で tag を指している変数タグレイヤー（fl が生きている間だけ使える）。"""
    root = fl.GetLayersRoot() if fl is not None else None
    if root is None:
        return []
    return [l for l in _iter_layers(root.GetDown()) if l.GetType() == c4d.FLweight and l.GetLinkedObject(doc) == tag]


def selection_limit(deformer):
    """箱の種類のデフォーマーが選択範囲に限定しているか（True / False）。

    選択範囲タグを指す変数タグレイヤーが1つでも有効なら True。レイヤーが無い・すべて無効なら False
    （フィールドが効かないので、箱の中はすべて変形し、箱の外は標準のデフォーマーと同じ動きになる）。
    ベベル（名前で限定する）、全体用、タグが見つからないものは None（切り替えられない）。
    """
    if deformer is None or deformer.GetType() not in BOX_TYPES or is_whole(deformer):
        return None
    doc = deformer.GetDocument()
    tag = get_selection_tag(deformer)
    if tag is None:
        return None
    fl = deformer[c4d.FIELDS]
    return any(l.GetChannelFlag(c4d.FIELDLAYER_CHANNELFLAG_ENABLE) for l in _weight_layers(fl, _weight_source(deformer, tag), doc))


def _weight_source(deformer, tag):
    """フィールドの変数タグレイヤーが指すもの: ぼかしていればその頂点マップ、いなければ選択範囲タグ。"""
    vmap = feather_tag(deformer)
    return vmap if vmap is not None else tag


def set_selection_limit(doc, deformer, on, undo=True):
    """「選択範囲に限定」のオン／オフ。変数タグレイヤーの「有効」を切り替える（レイヤーは消さない）。

    レイヤーが無いのにオンにしたときは、選択範囲タグのレイヤーをいちばん上に足す
    （ユーザーが足したぼかし等のレイヤーは残す）。アンドゥ1回。
    """
    if is_bevel(deformer):
        raise SDError(tr("ベベルは「選択範囲」欄のタグ名で限定するので、この切り替えはありません。",
                         "Bevel is limited by the tag name in its Selection field, so this option does not apply."))
    if deformer is None or deformer.GetType() not in BOX_TYPES:
        raise SDError(tr("PartDeform のデフォーマーを選択してください。", "Select a PartDeform deformer."))
    if is_whole(deformer):
        raise SDError(_whole_no_selection_message(deformer))
    tag = get_selection_tag(deformer)
    if tag is None:
        raise SDError(tr("「%s」が使う選択範囲タグが見つかりません。", "Cannot find the selection tag used by \"%s\".") % deformer.GetName())
    _stop_threads()
    src = _weight_source(deformer, tag)
    fl = deformer[c4d.FIELDS]
    layers = _weight_layers(fl, src, doc)
    if not layers and not on:
        return deformer  # もともと何も限定していない
    if undo:
        doc.StartUndo()
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
    try:
        if layers:
            for l in layers:
                l.SetChannelFlag(c4d.FIELDLAYER_CHANNELFLAG_ENABLE, bool(on))
        elif fl is None:
            fl = make_field_list(src)
        else:
            fl.InsertLayer(_new_weight_layer(src))
        deformer[c4d.FIELDS] = fl
        deformer.Message(c4d.MSG_UPDATE)
    finally:
        if undo:
            doc.EndUndo()
    c4d.EventAdd()
    return deformer


def _legacy_restriction_tag(deformer):
    # 旧版（制限タグで限定していた試作）で作ったデフォーマーの読み取り用
    tag = deformer.GetFirstTag()
    while tag:
        if tag.GetType() == c4d.Trestriction:
            return tag
        tag = tag.GetNext()
    return None


def get_selection_tag(deformer):
    """デフォーマーが使っている選択範囲タグを返す（無ければ None）。

    1) フィールドの変数タグレイヤーが指しているタグ（親オブジェクトのもの）
    2) 印に残したリンク
    3) 旧版の制限タグに書いた名前
    """
    parent = deformer.GetUp()
    if parent is None or is_whole(deformer):
        return None
    doc = deformer.GetDocument()
    if deformer.GetType() == c4d.Obevel:
        # ベベル: 「選択範囲」欄に書かれた名前のタグ（選択範囲タグの名前を変えると、この欄も合わせる必要がある）
        tag = find_tag_by_name(parent, deformer[BEVEL_SELECTION] or "", BEVEL_MODE_FOR_TAG)
        if tag is not None:
            return tag
        sub = _marker(deformer)
        if sub is not None:
            tag = sub.GetLink(MK_TAG, doc)
            if tag is not None and tag.GetObject() == parent:
                return tag
        return None
    for tag in weight_layer_targets(deformer, doc):
        if tag is not None and tag.GetType() in SELECTION_TAG_TYPES and tag.GetObject() == parent:
            return tag
    sub = _marker(deformer)
    if sub is not None:
        tag = sub.GetLink(MK_TAG, doc)
        if tag is not None and tag.GetObject() == parent:
            return tag
    rt = _legacy_restriction_tag(deformer)
    if rt is None:
        return None
    name = rt[c4d.RESTRICTIONTAG_NAME_01]
    tag = parent.GetFirstTag()
    while tag:
        if tag.GetType() in SELECTION_TAG_TYPES and tag.GetName() == name:
            return tag
        tag = tag.GetNext()
    return None


def find_tag_by_name(obj, name, types):
    tag = obj.GetFirstTag()
    while tag:
        if tag.GetType() in types and tag.GetName() == name:
            return tag
        tag = tag.GetNext()
    return None


def is_bevel(deformer):
    return deformer is not None and deformer.GetType() == c4d.Obevel


def _setup_bevel(bevel, tag, size_hint=None):
    """ベベルデフォーマーを、選択範囲タグ（名前）と、そのタグの種類に合うコンポーネントモードにする。"""
    mode = BEVEL_MODE_FOR_TAG.get(tag.GetType())
    if mode is None:
        raise SDError(tr("ベベルに使えない選択範囲タグです。", "This selection tag cannot be used for Bevel."))
    bevel[c4d.O_BEVEL_MODE_COMPONENT_TYPE] = mode
    # 「角度を使う」がオンだと、選んだエッジでも角度が浅いとベベルされないのでオフにする
    bevel[c4d.O_BEVEL_MODE_SELECTION_ANGLE_USE] = False
    bevel[BEVEL_SELECTION] = tag.GetName()
    if size_hint is not None:
        bevel[c4d.O_BEVEL_RADIUS] = max(size_hint * BEVEL_DEFAULT_RATIO, 0.01)


def _setup_bevel_whole(bevel, size_hint=None):
    """全体用のベベル: 「選択範囲」欄を空にして、隣の面との角度が BEVEL_WHOLE_ANGLE 以上のエッジだけ丸める。"""
    bevel[c4d.O_BEVEL_MODE_COMPONENT_TYPE] = BEVEL_MODE_EDGES
    bevel[c4d.O_BEVEL_MODE_SELECTION_ANGLE_USE] = True
    bevel[c4d.O_BEVEL_MODE_SELECTION_ANGLE_VAL] = BEVEL_WHOLE_ANGLE
    bevel[BEVEL_SELECTION] = ""
    if size_hint is not None:
        bevel[c4d.O_BEVEL_RADIUS] = max(size_hint * BEVEL_DEFAULT_RATIO, 0.01)


def _whole_no_selection_message(deformer):
    """全体用のデフォーマーでは使えない操作（選択範囲に限定など）の案内。"""
    parent = deformer.GetUp()
    if parent is not None and not parent.CheckType(c4d.Opolygon):
        return tr("「%s」はオブジェクト全体にかけています。メッシュになっていない「%s」では、選択範囲で限定できません"
                  "（C キーで編集可能にすると、一部だけにかけられます）。",
                  "\"%s\" works on the whole object. \"%s\" is not a mesh, so it cannot be limited to a selection "
                  "(make it editable with C to work on a part).") % (deformer.GetName(), parent.GetName())
    return tr("「%s」はオブジェクト全体にかけているので、選択範囲での限定はありません。一部だけにかけるときは、"
              "メッシュで選択してから「選択を取り直す」を押してください。",
              "\"%s\" works on the whole object, so there is no selection to limit to. To work on a part, "
              "select it on the mesh and press Update Selection.") % deformer.GetName()


def _selection_size(info):
    pts = info.points
    lo = c4d.Vector(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))
    hi = c4d.Vector(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))
    d = hi - lo
    return max(d.x, d.y, d.z)


def _point_tag_from_edges(doc, mesh, edge_tag):
    """エッジ選択タグの点から、ポイント選択タグ（プラグイン製）を作って mesh に付ける。アンドゥ記録あり。"""
    polys = mesh.GetAllPolygons()
    flags = edge_tag.GetBaseSelect().GetAll(mesh.GetPolygonCount() * 4)
    pts = set()
    for e, f in enumerate(flags):
        if not f:
            continue
        p = polys[e // 4]
        a, b = ((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))[e % 4]
        if a != b:
            pts.update((a, b))
    if len(pts) < 2:
        raise SDError(tr("エッジ選択タグ「%s」から点を取り出せませんでした。", "Could not get points from the edge selection tag \"%s\".") % edge_tag.GetName())
    tag = c4d.SelectionTag(c4d.Tpointselection)
    tag.SetName(_unique_tag_name(mesh, SELTAG_BASENAME))
    bs = tag.GetBaseSelect()
    for i in pts:
        bs.Select(i)
    _set_marker(tag, KIND_TAG)
    mesh.InsertTag(tag, mesh.GetLastTag())
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, tag)
    return tag


def affected_children(mesh):
    """フィールドの変数タグでは除外できず、一緒に変形してしまう子オブジェクト（デフォーマー以外）。"""
    out = []
    child = mesh.GetDown()
    while child:
        if not (child.GetInfo() & c4d.OBJECT_MODIFIER):
            out.append(child)
        child = child.GetNext()
    return out


# ---------------------------------------------------------------------------
# 小さな数学ヘルパー
# ---------------------------------------------------------------------------
def _poly_ids(p):
    if p.c == p.d:
        return (p.a, p.b, p.c)
    return (p.a, p.b, p.c, p.d)


def _perp(v):
    """v に直交する単位ベクトルを1つ返す。"""
    a = c4d.Vector(1, 0, 0) if abs(v.x) < 0.9 else c4d.Vector(0, 1, 0)
    w = v.Cross(a)
    if w.GetLength() < EPS:
        w = v.Cross(c4d.Vector(0, 0, 1))
    return w.GetNormalized()


def _eig_sym3(m):
    """3x3 対称行列の固有値・固有ベクトル（ヤコビ法）。固有値の小さい順。"""
    a = [list(row) for row in m]
    v = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    scale = sum(abs(a[i][j]) for i in range(3) for j in range(3)) + 1e-300
    for _ in range(64):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off <= 1e-14 * scale:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            apq = a[p][q]
            if abs(apq) <= 1e-300:
                continue
            theta = (a[q][q] - a[p][p]) / (2.0 * apq)
            t = (1.0 if theta >= 0.0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            c = 1.0 / math.sqrt(t * t + 1.0)
            s = t * c
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = c * akp - s * akq
                a[k][q] = s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = c * apk - s * aqk
                a[q][k] = s * apk + c * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p] = c * vkp - s * vkq
                v[k][q] = s * vkp + c * vkq
    vals = [a[0][0], a[1][1], a[2][2]]
    vecs = [c4d.Vector(v[0][i], v[1][i], v[2][i]).GetNormalized() for i in range(3)]
    order = sorted(range(3), key=lambda i: vals[i])
    return [vals[i] for i in order], [vecs[i] for i in order]


def _covariance(vectors, weights=None):
    n = len(vectors)
    if n == 0:
        return [[0.0] * 3 for _ in range(3)], c4d.Vector()
    if weights is None:
        weights = [1.0] * n
    wsum = sum(weights) or 1.0
    mean = c4d.Vector()
    for p, w in zip(vectors, weights):
        mean += p * w
    mean /= wsum
    cxx = cxy = cxz = cyy = cyz = czz = 0.0
    for p, w in zip(vectors, weights):
        d = p - mean
        cxx += w * d.x * d.x
        cxy += w * d.x * d.y
        cxz += w * d.x * d.z
        cyy += w * d.y * d.y
        cyz += w * d.y * d.z
        czz += w * d.z * d.z
    cov = [[cxx / wsum, cxy / wsum, cxz / wsum], [cxy / wsum, cyy / wsum, cyz / wsum], [cxz / wsum, cyz / wsum, czz / wsum]]
    return cov, mean


def _major_in_plane(points, normal):
    """normal に直交する面へ投影した点群の主方向（単位ベクトル、normal に直交）。"""
    proj = [p - normal * p.Dot(normal) for p in points]
    cov, _ = _covariance(proj)
    _, vecs = _eig_sym3(cov)
    u = vecs[2]
    u = u - normal * u.Dot(normal)
    if u.GetLength() < 1e-6:
        return _perp(normal)
    return u.GetNormalized()


def _orthonormal(x, y):
    """主軸 y を優先して (X, Y, Z) の正規直交系を作る。Z = X × Y。"""
    y = y.GetNormalized()
    x = x - y * x.Dot(y)
    if x.GetLength() < 1e-6:
        x = _perp(y)
    x = x.GetNormalized()
    z = x.Cross(y).GetNormalized()
    return x, y, z


def _extent(points, axis):
    vals = [p.Dot(axis) for p in points]
    return min(vals), max(vals)


# ---------------------------------------------------------------------------
# 選択範囲の解析
# ---------------------------------------------------------------------------
class SelectionInfo(object):
    """選択範囲の点・面・境界をまとめたもの（座標はオブジェクトのローカル空間）。"""

    def __init__(self, obj, point_ids, poly_ids, center=None):
        self.obj = obj
        all_pts = obj.GetAllPoints()
        polys = obj.GetAllPolygons()
        self.point_ids = sorted(point_ids)
        self.points = [all_pts[i] for i in self.point_ids]
        self.poly_ids = set(poly_ids)
        sset = set(point_ids)

        # 境界: 選択された点のうち、選択外のポリゴンにも属する点
        boundary = set()
        touching = []
        for i, p in enumerate(polys):
            ids = _poly_ids(p)
            if i in self.poly_ids:
                continue
            hit = False
            for v in ids:
                if v in sset:
                    boundary.add(v)
                    hit = True
            if hit:
                touching.append(i)
        self.boundary = [all_pts[i] for i in sorted(boundary)]

        # 法線: 選択ポリゴン（無ければ選択点に触れるポリゴン）の面積加重
        normal_polys = self.poly_ids if self.poly_ids else touching
        nsum = c4d.Vector()
        area = 0.0
        ncov = [[0.0] * 3 for _ in range(3)]
        for i in normal_polys:
            p = polys[i]
            v = (all_pts[p.c] - all_pts[p.a]).Cross(all_pts[p.d] - all_pts[p.b])
            ln = v.GetLength()
            if ln < EPS:
                continue
            nsum += v
            area += ln
            n = v / ln
            comps = (n.x, n.y, n.z)
            for r in range(3):
                for c in range(3):
                    ncov[r][c] += ln * comps[r] * comps[c]
        self.normal_sum = nsum
        self.area = area
        self.normal_cov = ncov
        self.coherence = (nsum.GetLength() / area) if area > EPS else 0.0
        self.object_center = center if center is not None else obj.GetMp()


def shape_children(obj):
    """obj の子のうち、形のあるもの（デフォーマーなど、ほかを変形するものを除く）。"""
    return [c for c in obj.GetChildren() if not (c.GetInfo() & c4d.OBJECT_MODIFIER)]


def _shape_points(root):
    """root と子孫の今の形（デフォーマーの変形は含めない）を、ワールド座標の点と、通し番号のポリゴンで返す。

    ジェネレーター（プリミティブ、サブディビジョンサーフェイス、クローナー等）はキャッシュの中身を使う。
    デフォーマーを子に持つと、キャッシュのポリゴンにも「入力」の印（BIT_CONTROLOBJECT）が付くので、
    キャッシュの中では印を見ない。本物の子は、親のジェネレーターに取り込まれている（親が子を入力にして
    キャッシュを作り、子に印がある）ときだけ外す。
    """
    pts = []
    polys = []

    def add(op):
        mg = op.GetMg()
        base = len(pts)
        pts.extend(mg * p for p in op.GetAllPoints())
        if op.IsInstanceOf(c4d.Opolygon):
            for p in op.GetAllPolygons():
                polys.append(c4d.CPolygon(p.a + base, p.b + base, p.c + base, p.d + base))

    def visit(op, in_cache):
        cache = op.GetCache()
        if cache is not None:
            visit(cache, True)
        elif op.IsInstanceOf(c4d.Opoint):
            add(op)
        consumes = (not in_cache) and cache is not None and bool(op.GetInfo() & c4d.OBJECT_INPUT)
        child = op.GetDown()
        while child:
            if in_cache:
                visit(child, True)
            elif not (child.GetInfo() & c4d.OBJECT_MODIFIER) and not (consumes and child.GetBit(c4d.BIT_CONTROLOBJECT)):
                visit(child, False)
            child = child.GetNext()

    visit(root, False)
    return pts, polys


def whole_info(obj, doc=None):
    """オブジェクト全体（子オブジェクトも含めた今の形）の SelectionInfo。座標は obj のローカル空間。

    デフォーマーは親だけでなく子オブジェクトもまとめて変形するので、箱は子も含めた大きさに合わせる。
    子の無いポリゴンオブジェクトは、そのメッシュの点そのもの（点番号がメッシュと同じ）。
    """
    if obj.CheckType(c4d.Opolygon) and not shape_children(obj):
        n = obj.GetPointCount()
        if n < 2:
            raise SDError(tr("「%s」には形がないので、大きさを決められません。", "\"%s\" has no shape, so its size cannot be found.") % obj.GetName())
        return SelectionInfo(obj, range(n), range(obj.GetPolygonCount()))
    doc = doc or obj.GetDocument()
    if doc is not None:
        # 作ったばかりのプリミティブなどはまだ中身（キャッシュ）が無いので、作らせる
        doc.ExecutePasses(None, False, False, True, c4d.BUILDFLAGS_NONE)
    pts, polys = _shape_points(obj)
    if len(pts) < 2:
        raise SDError(tr("「%s」には形がないので、大きさを決められません。", "\"%s\" has no shape, so its size cannot be found.") % obj.GetName())
    inv = ~obj.GetMg()
    local = [inv * p for p in pts]
    tmp = c4d.PolygonObject(len(local), len(polys))
    tmp.SetAllPoints(local)
    for i, p in enumerate(polys):
        tmp.SetPolygon(i, p)
    lo = c4d.Vector(min(p.x for p in local), min(p.y for p in local), min(p.z for p in local))
    hi = c4d.Vector(max(p.x for p in local), max(p.y for p in local), max(p.z for p in local))
    return SelectionInfo(tmp, range(len(local)), range(len(polys)), center=(lo + hi) * 0.5)


def whole_reason(doc, obj):
    """obj に作るとき全体用になるならその理由（"not_mesh" / "mode" / "empty"）、一部にかけるなら None。"""
    if not obj.CheckType(c4d.Opolygon):
        return "not_mesh"
    if doc.GetMode() not in COMPONENT_MODES:
        return "mode"
    if nothing_selected(doc, obj):
        return "empty"
    return None


def nothing_selected(doc, obj):
    """今のモード（ポイント・エッジ・ポリゴン）で何も選択していなければ True。

    そのときは全体用（オブジェクト全体にかける）にする。ほかのモードでは False。
    """
    mode = doc.GetMode()
    if mode == c4d.Mpolygons:
        return not any(obj.GetPolygonS().GetAll(obj.GetPolygonCount()))
    if mode == c4d.Mpoints:
        return not any(obj.GetPointS().GetAll(obj.GetPointCount()))
    if mode == c4d.Medges:
        return not _edge_ids_from(obj.GetEdgeS(), obj)
    return False


def selection_from_component_mode(doc, obj):
    """今のモードと選択から (タグ種別, 点ID集合, ポリゴンID集合, 説明) を返す。

    何も選択していないとき・ほかのモードのときは、呼ぶ側が全体用にする（whole_reason）。
    """
    mode = doc.GetMode()
    if mode not in COMPONENT_MODES:
        raise SDError(tr("ポイント・エッジ・ポリゴンのどれかのモードで、変形したい部分を選択してください。",
                         "Select the part to deform in Points, Edges or Polygons mode."))
    pcnt = obj.GetPointCount()
    vcnt = obj.GetPolygonCount()
    if pcnt < 2 or vcnt == 0:
        raise SDError(tr("「%s」にはポリゴンがありません。", "\"%s\" has no polygons.") % obj.GetName())
    polys = obj.GetAllPolygons()
    if mode == c4d.Mpolygons:
        flags = obj.GetPolygonS().GetAll(vcnt)
        poly_ids = [i for i, f in enumerate(flags) if f]
        pts = set()
        for i in poly_ids:
            pts.update(_poly_ids(polys[i]))
        return c4d.Tpolygonselection, pts, set(poly_ids), tr("ポリゴン %d 個", "%d polygons") % len(poly_ids)
    if mode == c4d.Mpoints:
        flags = obj.GetPointS().GetAll(pcnt)
        pts = set(i for i, f in enumerate(flags) if f)
        return c4d.Tpointselection, pts, _polys_inside(polys, pts), tr("ポイント %d 個", "%d points") % len(pts)
    edge_ids = _edge_ids_from(obj.GetEdgeS(), obj)
    pts = set()
    for e in edge_ids:
        p = polys[e // 4]
        pts.update(((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))[e % 4])
    return c4d.Tpointselection, pts, _polys_inside(polys, pts), tr("エッジ %d 本", "%d edges") % len(edge_ids)


def _polys_inside(polys, point_set):
    return set(i for i, p in enumerate(polys) if all(v in point_set for v in _poly_ids(p)))


def selection_from_tag(obj, tag):
    """選択範囲タグから SelectionInfo を作る。"""
    polys = obj.GetAllPolygons()
    bs = tag.GetBaseSelect()
    if tag.GetType() == c4d.Tpolygonselection:
        flags = bs.GetAll(obj.GetPolygonCount())
        poly_ids = set(i for i, f in enumerate(flags) if f)
        pts = set()
        for i in poly_ids:
            pts.update(_poly_ids(polys[i]))
    elif tag.GetType() == c4d.Tedgeselection:
        pts = set()
        for e in _edge_ids_from(bs, obj):
            p = polys[e // 4]
            pts.update(((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))[e % 4])
        poly_ids = _polys_inside(polys, pts)
    else:
        flags = bs.GetAll(obj.GetPointCount())
        pts = set(i for i, f in enumerate(flags) if f)
        poly_ids = _polys_inside(polys, pts)
    if len(pts) < 2:
        raise SDError(tr("選択範囲タグ「%s」の中身が空か、少なすぎます。", "The selection tag \"%s\" is empty or too small.") % tag.GetName())
    return SelectionInfo(obj, pts, poly_ids)


def _edge_ids_from(bs, obj):
    """エッジの BaseSelect（ポリゴン番号×4＋辺）から、長さのあるエッジの番号だけを返す。"""
    polys = obj.GetAllPolygons()
    out = []
    for e, f in enumerate(bs.GetAll(obj.GetPolygonCount() * 4)):
        if not f:
            continue
        p = polys[e // 4]
        a, b = ((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))[e % 4]
        if a != b:
            out.append(e)
    return out


def _all_edge_ids(obj):
    """すべてのエッジ（ポリゴン番号×4＋辺。三角形の長さの無い辺は除く）。エッジの全選択と同じ。"""
    out = []
    for i, p in enumerate(obj.GetAllPolygons()):
        for side, (a, b) in enumerate(((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))):
            if a != b:
                out.append(i * 4 + side)
    return out


def _poly_normal(pts, p):
    v = (pts[p.c] - pts[p.a]).Cross(pts[p.d] - pts[p.b])
    ln = v.GetLength()
    return v / ln if ln > EPS else None


def sharp_edge_ids(obj, angle, boundary=False):
    """隣の面との角度が angle 以上のエッジ（ポリゴン番号×4＋辺。両側のポリゴンの分とも）。

    ベベルデフォーマーの「角度を使う」と同じ選び方。boundary=True なら、隣の面が無い外周のエッジも含める。
    """
    pts = obj.GetAllPoints()
    polys = obj.GetAllPolygons()
    nb = c4d.utils.Neighbor()
    if not nb.Init(obj):
        raise SDError(tr("「%s」のエッジを調べられませんでした。", "Could not inspect the edges of \"%s\".") % obj.GetName())
    normals = [_poly_normal(pts, p) for p in polys]
    limit = math.cos(angle)
    out = []
    for i, p in enumerate(polys):
        for side, (a, b) in enumerate(((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))):
            if a == b:
                continue
            j = nb.GetNeighbor(a, b, i)
            if j < 0 or j == c4d.NOTOK:
                if boundary:
                    out.append(i * 4 + side)
                continue
            n1, n2 = normals[i], normals[j]
            if n1 is None or n2 is None:
                continue
            # 角度 = 2つの面の法線のなす角（平らなら 0°）
            if n1.Dot(n2) <= limit + 1e-9:
                out.append(i * 4 + side)
    return out


# ---------------------------------------------------------------------------
# 向き・起点・箱
# ---------------------------------------------------------------------------
def _selection_edges(info):
    """選択範囲のエッジ（両端とも選択範囲の点）のベクトル。重複なし。"""
    obj = info.obj
    allp = obj.GetAllPoints()
    polys = obj.GetAllPolygons()
    sset = set(info.point_ids)
    if info.poly_ids:
        source = info.poly_ids
    else:
        source = [i for i, p in enumerate(polys) if sum(1 for v in _poly_ids(p) if v in sset) >= 2]
    seen = set()
    out = []
    for i in source:
        ids = _poly_ids(polys[i])
        for k in range(len(ids)):
            a, b = ids[k], ids[(k + 1) % len(ids)]
            if a == b or a not in sset or b not in sset:
                continue
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            out.append(allp[b] - allp[a])
    return out


def _edge_aligned_axes(info, axis):
    """axis に直交する面の中で、選択範囲のエッジが並ぶ2方向（直交する単位ベクトル a, b）。

    エッジの向きを 90° ごとに折り返して（角度を4倍して）長さで重み付け平均する。
    円柱の輪のようにエッジの向きがばらばらで、揃った方向が無ければ None。
    """
    ref = _perp(axis)
    ref2 = axis.Cross(ref).GetNormalized()
    c_sum = s_sum = total = 0.0
    for d in _selection_edges(info):
        dp = d - axis * d.Dot(axis)
        length = dp.GetLength()
        if length < EPS:
            continue
        theta = math.atan2(dp.Dot(ref2), dp.Dot(ref))
        c_sum += length * math.cos(4.0 * theta)
        s_sum += length * math.sin(4.0 * theta)
        total += length
    if total < EPS or math.hypot(c_sum, s_sum) < EDGE_ALIGN_MIN * total:
        return None
    phi = math.atan2(s_sum, c_sum) / 4.0
    a = (ref * math.cos(phi) + ref2 * math.sin(phi)).GetNormalized()
    b = axis.Cross(a).GetNormalized()
    return a, b


def _axis_alignment(v):
    return max(abs(v.x), abs(v.y), abs(v.z))


def _in_plane_major(info, normal):
    """面の中の主方向。エッジが揃って並んでいればその向きに合わせる（長い方。
    ほぼ同じ長さならオブジェクトの軸に近い方）。揃っていなければ点の主成分分析。

    正方形に近い選択では主成分分析の向きが決まらず、エッジから斜めにずれた向きになるため。
    """
    pts = info.points
    aligned = _edge_aligned_axes(info, normal)
    if aligned is None:
        return _major_in_plane(pts, normal)
    a, b = aligned
    lo, hi = _extent(pts, a)
    ea = hi - lo
    lo, hi = _extent(pts, b)
    eb = hi - lo
    if abs(ea - eb) <= 0.05 * max(ea, eb, EPS):
        return a if _axis_alignment(a) >= _axis_alignment(b) else b
    return a if ea > eb else b


def _align_heading(info, axes):
    """主軸 Y まわりの回転（H 角度）を、選択範囲のエッジの流れに合わせる。今の X に近い方を新しい X にする。"""
    x, y, _z = axes
    aligned = _edge_aligned_axes(info, y)
    if aligned is None:
        return axes
    a, b = aligned
    nx = a if abs(a.Dot(x)) >= abs(b.Dot(x)) else b
    if nx.Dot(x) < 0:
        nx = -nx
    return _orthonormal(nx, y)


def auto_axes(info):
    """自動で (X, Y, Z) を決める。Y＝主軸（曲げる・ひねる軸）、X＝曲げ・せん断の方向。"""
    pts = info.points
    if info.area > EPS and info.coherence >= COHERENCE_SURFACE:
        # 面として揃っている（平らな面・ゆるい曲面・ドーム）
        n = info.normal_sum.GetNormalized()
        u = _in_plane_major(info, n)
        lo_n, hi_n = _extent(pts, n)
        lo_u, hi_u = _extent(pts, u)
        if (hi_n - lo_n) >= THICKNESS_RATIO * max(hi_u - lo_u, EPS):
            # 法線方向に厚みがある（ドーム・盛り上がり）: 主軸＝法線、曲げ方向＝面内の短い方向
            v = n.Cross(u)
            return _orthonormal(v, n)
        # 平らな面のパッチ: 主軸＝面内の最長方向、曲げ方向＝法線
        return _orthonormal(n, u)
    if info.area > EPS:
        # 法線がばらばら（突起・筒）: 法線とほぼ直交する方向＝突起の伸びる向きを主軸にする
        _, vecs = _eig_sym3(info.normal_cov)
        y = vecs[0]
        u = _major_in_plane(pts, y)
        return _align_heading(info, _orthonormal(y.Cross(u), y))
    # 面が無い（孤立した点など）: 点の主成分分析
    cov, _ = _covariance(pts)
    _, vecs = _eig_sym3(cov)
    return _orthonormal(vecs[0], vecs[2])


def root_is_max(info, y):
    """主軸 y の両端のうち、起点が +側（max）なら True。

    1) 未選択部分と接している点（境界）が片方の端に偏っていれば、その端。
    2) 決まらなければ、オブジェクトの中心に近い端。
    3) それも同じ（何も選択せずオブジェクト全体にかけたときなど）なら、オブジェクトの軸の
       マイナス側の端（縦長なら下）。標準のデフォーマーと同じ置き方にする。
    """
    pts = info.points
    ys = [p.Dot(y) for p in pts]
    lo, hi = min(ys), max(ys)
    length = hi - lo
    if length < EPS:
        return False
    band = END_BAND * length
    n_lo = n_hi = 0
    for b in info.boundary:
        t = b.Dot(y)
        if t <= lo + band:
            n_lo += 1
        if t >= hi - band:
            n_hi += 1
    if n_lo > 0 and n_lo >= 2 * n_hi:
        return False
    if n_hi > 0 and n_hi >= 2 * n_lo:
        return True
    # 決まらない: オブジェクトの中心に近い端
    lo_pts = [p for p, t in zip(pts, ys) if t <= lo + band]
    hi_pts = [p for p, t in zip(pts, ys) if t >= hi - band]
    c = info.object_center
    lo_c = sum(lo_pts, c4d.Vector()) / max(len(lo_pts), 1)
    hi_c = sum(hi_pts, c4d.Vector()) / max(len(hi_pts), 1)
    d_lo, d_hi = (lo_c - c).GetLength(), (hi_c - c).GetLength()
    if abs(d_hi - d_lo) > ROOT_TIE_RATIO * length:
        return d_hi < d_lo
    # 同じ: y のいちばん大きい成分がマイナスなら、+側の端がオブジェクトの軸のマイナス側
    comps = (y.x, y.y, y.z)
    return max(comps, key=abs) < 0


def orient_root(info, axes):
    """起点が -Y 側に来るように、必要なら X 軸まわりに 180° 回す。"""
    x, y, z = axes
    if root_is_max(info, y):
        return x, -y, -z
    return x, y, z


def _subsample(seq, n):
    if len(seq) <= n:
        return list(seq)
    step = len(seq) / float(n)
    return [seq[int(i * step)] for i in range(n)]


def _nearest_axis(d, candidates, max_angle_deg):
    """候補軸（±）のうち、d から max_angle_deg 以内でいちばん近いもの（d と同じ向き）。無ければ None。"""
    limit = math.cos(math.radians(max_angle_deg))
    best = None
    for c in candidates:
        c = c.GetNormalized()
        dot = d.Dot(c)
        if abs(dot) >= limit and (best is None or abs(dot) > best[0]):
            best = (abs(dot), c if dot > 0 else -c)
    return best[1] if best else None


def _snap_direction(d, candidates, max_angle_deg):
    """d に近い候補軸（±）があれば、その軸に揃える。"""
    axis = _nearest_axis(d, candidates, max_angle_deg)
    return axis if axis is not None else d


def boundary_direction(info):
    """未選択部分との境目から、境目からいちばん遠い部分へ向かう方向（単位ベクトル）。

    突起なら付け根→先端、端だけが未選択とつながる面なら、つながっている端→反対の端。
    境目が選択範囲を囲んでいて方向が出ない（面の真ん中だけ選んだ等）ときは None。
    """
    if not info.boundary or len(info.points) < 2:
        return None
    pts = info.points
    b_centre = sum(info.boundary, c4d.Vector()) / len(info.boundary)
    bs = _subsample(info.boundary, 160)
    ss = _subsample(pts, 2048)
    dist2 = [min((p - b).GetLengthSquared() for b in bs) for p in ss]
    dmax2 = max(dist2)
    if dmax2 < EPS:
        return None
    far = [p for p, d2 in zip(ss, dist2) if d2 >= 0.64 * dmax2]  # 最遠の 80% 以上
    f_centre = sum(far, c4d.Vector()) / len(far)
    offset = f_centre - b_centre
    lo = c4d.Vector(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))
    hi = c4d.Vector(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))
    if offset.GetLength() < BOUNDARY_OFFSET_RATIO * (hi - lo).GetLength():
        return None
    return offset.GetNormalized()


def auto_frame(info):
    """自動の向き (X, Y, Z)。起点（-Y 側）は未選択部分とつながっている側にする。

    1) 境目→境目から遠い部分の方向が出れば、それを主軸にする。面の上でエッジの流れに
       近ければその向きで確定。そうでなければ、オブジェクトの軸→選択範囲の形の主軸の順に、
       近いものへ揃える。
    2) 出なければ、形から主軸を決め、起点は境目の偏り→オブジェクトの中心の順で決める。
    """
    y = boundary_direction(info)
    if y is None:
        return orient_root(info, auto_axes(info))
    surface = info.area > EPS and info.coherence >= COHERENCE_SURFACE
    y_edge = None
    if surface:
        # 面の上では、まずエッジの流れの向きに揃える（斜めの面でもエッジに沿った箱にする）
        aligned = _edge_aligned_axes(info, info.normal_sum.GetNormalized())
        if aligned is not None:
            y_edge = _nearest_axis(y, aligned, SNAP_ANGLE)
    if y_edge is not None:
        # エッジの向きはトポロジーから決まる正確な向きなので、これで確定する。
        # このあと形の主成分分析に揃えると、凸が偏って並ぶ面などでは点の分布につられて
        # 箱が数度傾き、先端のずれが辺の場所によって変わってしまう（1.0.0 の不具合）。
        y = y_edge
    else:
        cov, _ = _covariance(info.points)
        _vals, pca = _eig_sym3(cov)
        y = _snap_direction(y, (c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1)), SNAP_ANGLE)
        y = _snap_direction(y, pca, SNAP_ANGLE)
    # 曲げ方向 X: 面なら法線の側（面が反り返る向き）、それ以外は主軸に直交する断面の薄い方向
    if surface:
        n = info.normal_sum.GetNormalized()
        xn = n - y * n.Dot(y)
        if xn.GetLength() > 0.3:
            return _align_heading(info, _orthonormal(xn, y))
    u = _major_in_plane(info.points, y)
    return _align_heading(info, _orthonormal(y.Cross(u), y))


def whole_frame(info):
    """全体用の向き (X, Y, Z): オブジェクトの軸にそろえ、いちばん長い軸を主軸（起点はマイナス側の端）、
    残りのうち薄い方を曲げる向き（デフォーマーの X）にする。

    標準のデフォーマーをオブジェクトの大きさに合わせて置くのと同じ考え方。形の主成分で決めると、
    子オブジェクトを含むグループなどでは点の多い部分につられて、長い方向から外れることがあるため。
    同じくらいの長さなら、主軸は Y → X → Z、曲げる向きは X → Z → Y の順に選ぶ。
    """
    pts = info.points
    comps = [[p.x for p in pts], [p.y for p in pts], [p.z for p in pts]]
    ext = [max(c) - min(c) for c in comps]
    tol = max(ext) * 0.01 + EPS
    main = next(a for a in (1, 0, 2) if ext[a] >= max(ext) - tol)
    rest = [a for a in (0, 2, 1) if a != main]
    thin = min(ext[a] for a in rest)
    bend = next(a for a in rest if ext[a] <= thin + tol)
    e = (c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1))
    return _orthonormal(e[bend], e[main])


def fit_box(info, axes, dtype):
    """軸 (X, Y, Z) のもとで選択範囲を囲む箱。(行列, サイズ) を返す。"""
    x, y, z = axes
    pts = info.points
    lo_x, hi_x = _extent(pts, x)
    lo_y, hi_y = _extent(pts, y)
    lo_z, hi_z = _extent(pts, z)
    center = x * ((lo_x + hi_x) * 0.5) + y * ((lo_y + hi_y) * 0.5) + z * ((lo_z + hi_z) * 0.5)
    sx, sy, sz = hi_x - lo_x, hi_y - lo_y, hi_z - lo_z
    biggest = max(sx, sy, sz)
    if biggest < EPS:
        raise SDError(tr("選択範囲の大きさが0です。", "The selection has zero size."))
    minimum = max(biggest * MIN_SIZE_RATIO, 1e-3)
    sx, sy, sz = max(sx, minimum), max(sy, minimum), max(sz, minimum)
    # どの種類も箱は選択範囲にぴったり（シアーだけ広げることはしない）
    return c4d.Matrix(center, x, y, z), c4d.Vector(sx, sy, sz)


def shear_lever(size, angle):
    """シアーの強度 100% のときの、先端のずれ量（シーンの単位）。

    実測（C4D 2027）: 先端のずれ＝強度 × (cos(角度)·X幅/2, 0, sin(角度)·Z幅/2)。
    湾曲・フィレットは途中の曲がり方だけを変え、先端のずれ量は変えない。
    """
    return math.hypot(math.cos(angle) * size.x * 0.5, math.sin(angle) * size.z * 0.5)


# 強度（%）を長さに換算して見せる種類と、その量の名前
LENGTH_AMOUNT_LABEL = {
    c4d.Oshear: tr("シアー: 先端のずれ", "Shear: tip offset"),
    c4d.Otaper: tr("テーパー: 先端の片側の絞り", "Taper: tip inset (per side)"),
    c4d.Obulge: tr("膨張: 中央の片側のふくらみ", "Bulge: middle bulge (per side)"),
    c4d.Obevel: tr("ベベル: オフセット", "Bevel: offset"),
}


def amount_lever(deformer):
    """強度 100% のときの量（シーンの単位）。長さで見せない種類なら None。

    実測（C4D 2027）:
    - シアー: 先端のずれ＝強度 × (cos(角度)·X幅/2, 0, sin(角度)·Z幅/2)（箱の幅で変わる）
    - テーパー: 先端の点が「強度 × 軸からの距離」だけ内側へ（＋で絞り、−で広がり）
    - 膨張: 中央の点が「強度 × 軸からの距離」だけ外側へ
    テーパー・膨張は箱の大きさに関係しないので、選択範囲のいちばん外側＝箱の幅の広い方の側面
    （X・Z の大きい方の半分）での量とする。湾曲・フィレットはどれも途中の形だけを変える。
    """
    dtype = deformer.GetType()
    if dtype == c4d.Obevel:
        # ベベルのオフセットはもともと長さ（「比例」モードのときだけ長さではないので対象外）
        if deformer[c4d.O_BEVEL_OFFSET_MODE] == BEVEL_OFFSET_PROPORTIONAL:
            return None
        return 1.0
    size = deformer[c4d.DEFORMOBJECT_SIZE]
    if dtype == c4d.Oshear:
        return shear_lever(size, deformer[c4d.DEFORMOBJECT_ANGLE])
    if dtype in (c4d.Otaper, c4d.Obulge):
        return max(size.x, size.z) * 0.5
    return None


def length_param(deformer):
    """長さの欄で書き換えるパラメーター（ベベルはオフセット、ほかは強度）。"""
    return c4d.O_BEVEL_RADIUS if is_bevel(deformer) else c4d.DEFORMOBJECT_STRENGTH


def amount_length(deformer):
    """強度を長さに換算した量（シーンの単位、符号付き）。長さで見せない種類なら None。"""
    lever = amount_lever(deformer)
    if lever is None:
        return None
    return deformer[length_param(deformer)] * lever


def amount_slider_range(deformer):
    """パネルのスライダーの範囲（シーンの単位）。数値欄にはこの外の値も入力できる。

    シアー: ±主軸の長さの半分（約 27°。作成時のずれ＝長さの 20% が細かく調整できる範囲）
    テーパー・膨張: ±片側の幅（強度 ±100% 相当。テーパー 100% で先端が軸に集まる）
    ベベル: 0〜オブジェクトの大きさ（最大の半径）の 20%（オフセットは負にならない）
    """
    dtype = deformer.GetType()
    if dtype == c4d.Obevel:
        mesh = deformer.GetUp()
        rad = mesh.GetRad() if mesh is not None else c4d.Vector(100.0)
        return 0.0, max(max(rad.x, rad.y, rad.z) * 0.2, 1.0)
    size = deformer[c4d.DEFORMOBJECT_SIZE]
    if dtype == c4d.Oshear:
        limit = size.y * 0.5
    elif dtype in (c4d.Otaper, c4d.Obulge):
        limit = max(size.x, size.z) * 0.5
    else:
        return None
    limit = max(limit, 1e-3)
    return -limit, limit


def set_amount_length(doc, deformer, value, undo=True):
    """量を長さで指定して、強度（%）を逆算して入れる。

    undo=True ならアンドゥ1回分として記録する。スライダーのドラッグ中は undo=False で
    何度も呼び、離したときに undo=True で1回だけ記録する。
    """
    _stop_threads()
    lever = amount_lever(deformer) if deformer is not None else None
    if lever is None:
        raise SDError(tr("シアー・テーパー・膨張・ベベル（比例モード以外）のPartDeform のデフォーマーを選択してください。", "Select a PartDeform Shear, Taper, Bulge or Bevel deformer (Bevel: not in Proportional offset mode)."))
    if lever < EPS:
        raise SDError(tr("デフォーマーの幅が0なので、量を決められません。", "The deformer has zero width, so the amount cannot be set."))
    param = length_param(deformer)
    strength = value / lever
    if is_bevel(deformer):
        strength = max(strength, 0.0)  # ベベルのオフセットは負にできない
    if undo:
        doc.StartUndo()
        try:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
            deformer[param] = strength
        finally:
            doc.EndUndo()
    else:
        deformer[param] = strength
    c4d.EventAdd()
    return deformer


# ---------------------------------------------------------------------------
# パネルの数値欄（1段目＝量、2段目＝方向）
# ---------------------------------------------------------------------------
# 1段目を角度で見せる種類（屈曲の強度＝曲げる角度、ツイストの角度＝ひねる角度）
ANGLE_AMOUNT_LABEL = {
    c4d.Obend: tr("屈曲: 強度（曲げる角度）", "Bend: strength (bend angle)"),
    c4d.Otwist: tr("ツイスト: 角度（ひねる角度）", "Twist: angle"),
}
# 2段目（DEFORMOBJECT_ANGLE＝曲げ・ずらす向き）を見せる種類
DIRECTION_LABEL = {
    c4d.Obend: tr("屈曲: 角度（曲げる向き）", "Bend: angle (direction)"),
    c4d.Oshear: tr("シアー: 角度（ずらす向き）", "Shear: angle (direction)"),
}
# スライダーの範囲（属性マネージャーと同じ。ツイストは逆向きにもひねれるよう屈曲の強度と同じ ±360°）
ANGLE_AMOUNT_SLIDER = math.radians(360.0)
DIRECTION_SLIDER = (0.0, math.radians(360.0))

UNIT_LENGTH = "length"
UNIT_ANGLE = "angle"


def amount_row(deformer):
    """パネルの1段目（量）の中身: (名前, 単位, 値, スライダー範囲)。この欄を使わない種類なら None。

    シアー・テーパー・膨張・ベベルは長さ（強度を実寸に換算）、屈曲・ツイストは角度（そのまま）。
    """
    if deformer is None:
        return None
    dtype = deformer.GetType()
    if dtype in ANGLE_AMOUNT_LABEL:
        limit = ANGLE_AMOUNT_SLIDER
        return ANGLE_AMOUNT_LABEL[dtype], UNIT_ANGLE, deformer[AMOUNT_PARAM[dtype]], (-limit, limit)
    if dtype in LENGTH_AMOUNT_LABEL and amount_lever(deformer) is not None:
        return LENGTH_AMOUNT_LABEL[dtype], UNIT_LENGTH, amount_length(deformer), amount_slider_range(deformer)
    return None


def amount_params(deformer):
    """1段目を動かすと書き換わるパラメーター（ドラッグ前の値に戻すため）。"""
    dtype = deformer.GetType()
    return (AMOUNT_PARAM[dtype],) if dtype in ANGLE_AMOUNT_LABEL else (length_param(deformer),)


def set_amount(doc, deformer, value, undo=True):
    """1段目の値を入れる。長さの種類は強度を逆算し、角度の種類はそのまま入れる。"""
    if deformer is not None and deformer.GetType() in ANGLE_AMOUNT_LABEL:
        return _set_params(doc, deformer, {AMOUNT_PARAM[deformer.GetType()]: value}, undo)
    return set_amount_length(doc, deformer, value, undo)


def direction_row(deformer):
    """パネルの2段目（方向）の中身: (名前, 単位, 値, スライダー範囲)。この欄を使わない種類なら None。"""
    if deformer is None or deformer.GetType() not in DIRECTION_LABEL:
        return None
    return DIRECTION_LABEL[deformer.GetType()], UNIT_ANGLE, deformer[c4d.DEFORMOBJECT_ANGLE], DIRECTION_SLIDER


def direction_params(deformer):
    """2段目を動かすと書き換わるパラメーター（シアーは先端のずれを保つため強度も変わる）。"""
    if deformer.GetType() == c4d.Oshear:
        return c4d.DEFORMOBJECT_ANGLE, c4d.DEFORMOBJECT_STRENGTH
    return (c4d.DEFORMOBJECT_ANGLE,)


def set_direction(doc, deformer, angle, undo=True, keep_shift=None):
    """屈曲・シアーの角度（曲げ・ずらす向き）を入れる。

    シアーは向きで箱の X 幅・Z 幅のどちらを使うかが変わり、同じ強度でもずれ量が変わるので、
    先端のずれ（keep_shift、無ければ今のずれ）が変わらないよう強度を換算し直す
    （「起点と方向」のボタンで箱の幅が変わったときと同じ考え方）。新しい向きで幅が0なら強度はそのまま。
    """
    if deformer is None or deformer.GetType() not in DIRECTION_LABEL:
        raise SDError(tr("屈曲かシアーのPartDeform のデフォーマーを選択してください。", "Select a PartDeform Bend or Shear deformer."))
    values = {c4d.DEFORMOBJECT_ANGLE: angle}
    if deformer.GetType() == c4d.Oshear:
        shift = shear_shift(deformer) if keep_shift is None else keep_shift
        lever = shear_lever(deformer[c4d.DEFORMOBJECT_SIZE], angle)
        if lever > EPS:
            values[c4d.DEFORMOBJECT_STRENGTH] = shift / lever
    return _set_params(doc, deformer, values, undo)


def _set_params(doc, deformer, values, undo):
    """パラメーターをまとめて書き換える。undo=True ならアンドゥ1回分。"""
    _stop_threads()
    if undo:
        doc.StartUndo()
        try:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
            for param, value in values.items():
                deformer[param] = value
        finally:
            doc.EndUndo()
    else:
        for param, value in values.items():
            deformer[param] = value
    c4d.EventAdd()
    return deformer


def shear_shift(deformer):
    """シアーの先端のずれ量（シーンの単位、符号付き）。"""
    return deformer[c4d.DEFORMOBJECT_STRENGTH] * shear_lever(
        deformer[c4d.DEFORMOBJECT_SIZE], deformer[c4d.DEFORMOBJECT_ANGLE])


def set_shear_shift(doc, deformer, shift):
    """先端のずれ量を指定して、シアーの強度（%）を逆算して入れる。アンドゥ1回。"""
    if deformer is None or deformer.GetType() != c4d.Oshear:
        raise SDError(tr("シアーのPartDeform のデフォーマーを選択してください。", "Select a PartDeform Shear deformer."))
    return set_amount_length(doc, deformer, shift)


def default_amount(dtype, size, angle=0.0):
    """作成時（と別単位の種類からの切り替え時）の強さ。

    シアーのずれ量は「強度 × 箱の X 幅 / 2」なので、箱を選択範囲にぴったり合わせると、
    薄い面（X＝法線）では % が大きくないと効かない。先端が主軸の長さの SHEAR_DEFAULT_SHIFT
    だけずれる強度を箱の大きさから逆算する。angle はシアーの角度（ずらす向き）。屈曲から切り替えると
    屈曲の向きを引き継ぐので、その向きで使う幅で逆算する（0° の幅で逆算すると、ずれが何倍にもなる）。
    """
    if dtype == c4d.Oshear:
        return SHEAR_DEFAULT_SHIFT * size.y / max(shear_lever(size, angle), EPS)
    if dtype == c4d.Obevel:
        return max(max(size.x, size.y, size.z) * BEVEL_DEFAULT_RATIO, 0.01)
    return DEFAULT_AMOUNT[dtype]


# ---------------------------------------------------------------------------
# 境目のぼかし
# ---------------------------------------------------------------------------
# 選んだ範囲の内側で、境目（選んでいない部分とのつなぎ目）に向かって効きを 0 まで弱める。
# 重みは頂点マップタグに入れ、フィールドの変数タグレイヤーを選択範囲タグからその頂点マップに向け替える
# （標準の頂点マップとフィールドなので、プラグインが無くても同じ形になる）。
# 距離は面に沿って測る（離れた別の部分へは漏れない）。幅は長さで、デフォーマーごとに持つ。
FEATHER_LABEL = tr("ぼかし（境目から内側へ弱める幅）", "Feather (fades inward from the border)")
_distance_cache = {}


def _border_distances(mesh, tag):
    """選択範囲タグの点ごとの、境目からの面に沿った距離。(選択の点番号のリスト, {点番号: 距離}) を返す。

    境目＝選択の点のうち、選択外のポリゴンにも属する点（距離 0）。選んだポリゴンの辺と対角線をたどる
    ダイクストラ法で測る。境目が無い（すべて選んでいる等）点は辞書に入らない（＝十分遠い）。
    スライダーのドラッグ中に何度も呼ぶので、メッシュとタグが変わるまで使い回す。
    """
    key = (id(mesh), id(tag))
    dirty = (mesh.GetDirty(c4d.DIRTYFLAGS_DATA), tag.GetDirty(c4d.DIRTYFLAGS_DATA))
    hit = _distance_cache.get(key)
    if hit is not None and hit[0] is mesh and hit[1] is tag and hit[2] == dirty:
        return hit[3], hit[4]
    info = selection_from_tag(mesh, tag)
    sel = set(info.point_ids)
    pts = mesh.GetAllPoints()
    adj = {}
    border = set()
    for i, p in enumerate(mesh.GetAllPolygons()):
        ids = _poly_ids(p)
        if i not in info.poly_ids:
            border.update(v for v in ids if v in sel)
            continue  # 選択外のポリゴンの中はたどらない
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                u, v = ids[a], ids[b]
                if u in sel and v in sel:
                    d = (pts[u] - pts[v]).GetLength()
                    adj.setdefault(u, []).append((v, d))
                    adj.setdefault(v, []).append((u, d))
    dist = dict.fromkeys(border, 0.0)
    heap = [(0.0, v) for v in border]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float("inf")):
            continue
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    _distance_cache.clear()
    _distance_cache[key] = (mesh, tag, dirty, info.point_ids, dist)
    return info.point_ids, dist


def _feather_weights(mesh, tag, width):
    """頂点マップの重み（点ごと 0〜1）。選択の外は 0、境目で 0、境目から width 以上内側で 1（なめらかな S 字）。"""
    ids, dist = _border_distances(mesh, tag)
    weights = [0.0] * mesh.GetPointCount()
    for i in ids:
        t = min(dist.get(i, width) / width, 1.0)
        weights[i] = t * t * (3.0 - 2.0 * t)
    return weights


def _relink_layers(deformer, old, new, doc):
    """フィールドの変数タグレイヤーのうち old を指すものを new に向け替える（「有効」はそのまま）。向け替えた数を返す。"""
    fl = deformer[c4d.FIELDS]
    layers = _weight_layers(fl, old, doc)
    for layer in layers:
        layer.SetLinkedObject(new)
    if layers:
        deformer[c4d.FIELDS] = fl
    return len(layers)


def _feather_used_elsewhere(mesh, vmap, deformer):
    return any(d is not deformer and feather_tag(d) == vmap for d in sd_deformers_under(mesh))


def _apply_feather(doc, deformer, mesh, tag, width, undo=True):
    """ぼかしの頂点マップを作る／書き直し、フィールドのレイヤーをそれに向ける。width<=0 なら選択範囲タグに戻して消す。

    アンドゥは呼び出し側の StartUndo の中で（undo=False ならアンドゥを積まない＝スライダーのドラッグ中）。
    """
    old = feather_tag(deformer)
    if width <= 0.0:
        if undo:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
        if old is not None:
            _relink_layers(deformer, old, tag, doc)
        _set_marker(deformer, KIND_DEFORMER, tag, feather=(0.0, None))
        if old is not None and is_marked(old, KIND_FEATHER) and not _feather_used_elsewhere(mesh, old, deformer):
            if undo:
                doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old)
            old.Remove()
        deformer.Message(c4d.MSG_UPDATE)
        return
    weights = _feather_weights(mesh, tag, width)
    vmap = old
    if vmap is None or vmap.GetDataCount() != len(weights) or _feather_used_elsewhere(mesh, vmap, deformer):
        # 点の数が変わっていたら（モデリングで増減）作り直す
        vmap = c4d.VariableTag(c4d.Tvertexmap, len(weights))
        vmap.SetName(_unique_tag_name(mesh, FEATHER_BASENAME))
        _set_marker(vmap, KIND_FEATHER)
        mesh.InsertTag(vmap, tag)
        if undo:
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, vmap)
    elif undo:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, vmap)
    vmap.SetAllHighlevelData(weights)
    vmap.Message(c4d.MSG_UPDATE)
    if undo:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
    if vmap is not old:
        if not _relink_layers(deformer, old if old is not None else tag, vmap, doc):
            # レイヤーが無い（限定していない）なら、「有効」オフで入れておく（限定をオンにすれば効く）
            fl = deformer[c4d.FIELDS] or c4d.FieldList()
            fl.InsertLayer(_new_weight_layer(vmap, enabled=False))
            deformer[c4d.FIELDS] = fl
    _set_marker(deformer, KIND_DEFORMER, tag, feather=(width, vmap))
    if old is not None and vmap is not old and is_marked(old, KIND_FEATHER) and not _feather_used_elsewhere(mesh, old, deformer):
        if undo:
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old)
        old.Remove()
    deformer.Message(c4d.MSG_UPDATE)


def _feather_target(deformer):
    """ぼかしを使える PartDeform のデフォーマーなら (メッシュ, 選択範囲タグ)。使えなければ SDError。"""
    if deformer is None or not is_sd_deformer(deformer):
        raise SDError(tr("PartDeform のデフォーマーを選択してください。", "Select a PartDeform deformer."))
    if deformer.GetType() not in BOX_TYPES:
        raise SDError(tr("ベベルには境目のぼかしはありません。", "Bevel has no feather."))
    if is_whole(deformer):
        raise SDError(tr("「%s」はオブジェクト全体にかけているので、ぼかす境目がありません。", "\"%s\" works on the whole object, so there is no border to feather.") % deformer.GetName())
    mesh = _mesh_of(deformer)
    tag = get_selection_tag(deformer)
    if tag is None:
        raise SDError(tr("「%s」が使う選択範囲タグが見つかりません。", "Cannot find the selection tag used by \"%s\".") % deformer.GetName())
    return mesh, tag


def set_feather(doc, deformer, width, undo=True):
    """境目のぼかしの幅（長さ）を入れる。0 以下でぼかしを外す。undo=True ならアンドゥ1回分。"""
    mesh, tag = _feather_target(deformer)
    width = max(float(width), 0.0)
    _stop_threads()
    if undo:
        doc.StartUndo()
    try:
        _apply_feather(doc, deformer, mesh, tag, width, undo)
    finally:
        if undo:
            doc.EndUndo()
    c4d.EventAdd()
    return deformer


def feather_row(deformer):
    """パネルの3段目（ぼかし）の中身: (名前, 単位, 値, スライダー範囲)。使えない種類・全体用なら None。"""
    try:
        _feather_target(deformer)
    except SDError:
        return None
    size = deformer[c4d.DEFORMOBJECT_SIZE]
    return FEATHER_LABEL, UNIT_LENGTH, feather_width(deformer), (0.0, max(0.5 * max(size.x, size.y, size.z), 1.0))


def _refresh_feather(doc, deformer, mesh, tag, undo=True):
    """選択範囲や形が変わったあとに、ぼかしの重みを測り直す（ぼかしていなければ何もしない）。"""
    width = feather_width(deformer)
    if width > 0.0 and tag is not None:
        _apply_feather(doc, deformer, mesh, tag, width, undo)


def _axes_of(deformer):
    m = deformer.GetMl()
    return _orthonormal(m.v1, m.v2)


def _apply_box(doc, deformer, mat, size, undo=True):
    if undo:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
    deformer.SetMl(mat)
    deformer[c4d.DEFORMOBJECT_SIZE] = size
    deformer.Message(c4d.MSG_UPDATE)


# ---------------------------------------------------------------------------
# 対象の取得
# ---------------------------------------------------------------------------
def _active_objects(doc):
    return doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE) or []


def active_sd_deformer(doc):
    """アクティブなプラグイン製デフォーマー（1つ目）。無ければ None。"""
    for o in _active_objects(doc):
        if is_sd_deformer(o):
            return o
    return None


def sd_deformers_under(obj):
    return [c for c in obj.GetChildren() if is_sd_deformer(c)]


def edit_target(doc):
    """向き・再フィットの対象。選択中のプラグイン製デフォーマー、
    または選択中のオブジェクトの下にプラグイン製デフォーマーが1つだけあればそれ。"""
    d = active_sd_deformer(doc)
    if d is not None:
        return d
    act = _active_objects(doc)
    if len(act) == 1:
        ds = sd_deformers_under(act[0])
        if len(ds) == 1:
            return ds[0]
        if len(ds) > 1:
            raise SDError(tr("「%s」にはPartDeform のデフォーマーが %d 個あります。どれか1つを選択してください。", "\"%s\" has %d PartDeform deformers. Select one of them.") % (act[0].GetName(), len(ds)))
    raise SDError(tr("PartDeform のデフォーマーを選択してください。", "Select a PartDeform deformer."))


def freeze_targets(doc):
    """フリーズの対象: 選択中のプラグイン製デフォーマーと、
    選択中のオブジェクトの直下にあるプラグイン製デフォーマーすべて（階層順）。"""
    found = []
    for o in _active_objects(doc):
        cands = [o] if is_sd_deformer(o) else sd_deformers_under(o)
        for d in cands:
            if d not in found:
                found.append(d)
    order = {}
    idx = [0]

    def walk(op):
        while op:
            order[op] = idx[0]
            idx[0] += 1
            walk(op.GetDown())
            op = op.GetNext()

    walk(doc.GetFirstObject())
    found.sort(key=lambda d: order.get(d, 0))
    return found


def _mesh_of(deformer):
    parent = deformer.GetUp()
    if parent is None or not parent.CheckType(c4d.Opolygon):
        raise SDError(tr("「%s」の親が編集可能なポリゴンオブジェクトではありません。", "The parent of \"%s\" is not an editable polygon object.") % deformer.GetName())
    return parent


def _parent_of(deformer):
    """全体用のデフォーマーの親（ポリゴンでなくてもよい）。"""
    parent = deformer.GetUp()
    if parent is None:
        raise SDError(tr("「%s」に親のオブジェクトがありません。", "\"%s\" has no parent object.") % deformer.GetName())
    return parent


def _info_of(deformer):
    if is_whole(deformer):
        return whole_info(_parent_of(deformer))
    mesh = _mesh_of(deformer)
    tag = get_selection_tag(deformer)
    if tag is None:
        raise SDError(tr("「%s」が使う選択範囲タグが見つかりません（フィールドの変数タグレイヤーに選択範囲タグを入れてください）。", "Cannot find the selection tag used by \"%s\" (put a selection tag into a Variable Tag layer in its Fields).") % deformer.GetName())
    return selection_from_tag(mesh, tag)


# ---------------------------------------------------------------------------
# 作成・種類の切り替え
# ---------------------------------------------------------------------------
def _unique_tag_name(obj, base):
    names = set()
    t = obj.GetFirstTag()
    while t:
        names.add(t.GetName())
        t = t.GetNext()
    if base not in names:
        return base
    i = 1
    while "%s.%d" % (base, i) in names:
        i += 1
    return "%s.%d" % (base, i)


def _deformer_name(dtype, tag_name):
    return "%s [%s]" % (c4d.GetObjectName(dtype), tag_name)


def _new_deformer(doc, dtype):
    d = c4d.BaseObject(dtype)
    if d is None:
        raise SDError(tr("デフォーマーを作れませんでした。", "Could not create the deformer."))
    # メニューから作ったときと同じ初期化（フィールドの初期化など）
    d.Message(c4d.MSG_MENUPREPARE, doc)
    if dtype in BOX_TYPES:
        d[c4d.DEFORMOBJECT_MODE] = c4d.DEFORMOBJECT_MODE_LIMIT
    return d


def _usable_tag(doc, mesh, tag, dtype):
    """dtype で使える選択範囲タグ。箱の種類はフィールドでエッジ選択タグを使えないので、点のタグを作る。"""
    if dtype in BOX_TYPES and tag.GetType() == c4d.Tedgeselection:
        return _point_tag_from_edges(doc, mesh, tag)
    return tag


def _configure(new, dtype, tag, info, axes, amount=None, fields=None, limit=True):
    """新しいデフォーマーに選択範囲・箱・強さを入れ、ローカル行列を返す（挿入前に呼ぶ）。

    fields を渡さないときは、選択範囲タグのレイヤーを入れる（limit=False なら「有効」オフで）。
    tag=None は全体用: ベベルは角だけ丸め、箱の種類はフィールドを入れない（fields を渡せばそれを入れる）。
    """
    if dtype == c4d.Obevel:
        if tag is None:
            _setup_bevel_whole(new, _selection_size(info))
        else:
            _setup_bevel(new, tag, _selection_size(info))
        if amount is not None:
            new[c4d.O_BEVEL_RADIUS] = amount
        return c4d.Matrix()
    mat, size = fit_box(info, axes, dtype)
    new[c4d.DEFORMOBJECT_SIZE] = size
    if amount is None:
        # 方向の角度は呼び出し側（種類の切り替え）が先に入れている
        angle = new[c4d.DEFORMOBJECT_ANGLE] if dtype in DIRECTION_ANGLE_TYPES else 0.0
        amount = default_amount(dtype, size, angle or 0.0)
    new[AMOUNT_PARAM[dtype]] = amount
    if fields is not None:
        new[c4d.FIELDS] = fields
    elif tag is not None:
        new[c4d.FIELDS] = make_field_list(tag, limit)
    return mat


def _axes_for(deformer, info):
    """新しい箱の向き: 元が箱の種類ならその向き、ベベル（箱が無い）なら自動判定（全体用はオブジェクトの軸）。"""
    if deformer.GetType() in BOX_TYPES:
        return _axes_of(deformer)
    return whole_frame(info) if is_whole(deformer) else auto_frame(info)


def create(doc, dtype, limit=True):
    """選択中のオブジェクトにデフォーマーを作る。

    ポリゴンオブジェクトでポイント・エッジ・ポリゴンを選んでいれば、その部分用（選択範囲タグ付き）。
    何も選んでいない・モデルモードなど・メッシュになっていないオブジェクトなら、全体用（_create_whole）。
    limit=False: 選択範囲に限定しない（フィールドのレイヤーは「有効」オフで入れる）。ベベルは常に限定。
    """
    if dtype not in DEFORMER_TYPES:
        raise SDError(tr("未対応のデフォーマーです。", "Unsupported deformer type."))
    _stop_threads()
    act = _active_objects(doc)
    if len(act) != 1:
        raise SDError(tr("変形したいオブジェクトを1つだけ選択してください。", "Select exactly one object to deform."))
    obj = act[0]
    if obj.GetInfo() & c4d.OBJECT_MODIFIER:
        raise SDError(tr("「%s」はほかを変形する側のオブジェクトです。変形したいオブジェクトを選択してください。",
                         "\"%s\" deforms other objects. Select the object you want to deform.") % obj.GetName())
    if whole_reason(doc, obj) is not None:
        return _create_whole(doc, obj, dtype)

    tag_type, pts, poly_ids, _desc = selection_from_component_mode(doc, obj)
    if len(pts) < 2:
        raise SDError(tr("選択範囲が小さすぎます（ポイント2個以上を含めてください）。", "The selection is too small (include at least 2 points)."))
    edge_ids = None
    if dtype == c4d.Obevel and doc.GetMode() == c4d.Medges:
        # ベベルはエッジのままで使う（箱の種類は、エッジの点をポイント選択タグにする）
        tag_type = c4d.Tedgeselection
        edge_ids = _edge_ids_from(obj.GetEdgeS(), obj)
    info = SelectionInfo(obj, pts, poly_ids)
    axes = auto_frame(info) if dtype in BOX_TYPES else None

    doc.StartUndo()
    try:
        tag = c4d.SelectionTag(tag_type)
        tag.SetName(_unique_tag_name(obj, SELTAG_BASENAME))
        bs = tag.GetBaseSelect()
        bs.DeselectAll()
        if tag_type == c4d.Tedgeselection:
            ids = edge_ids
        elif tag_type == c4d.Tpolygonselection:
            ids = poly_ids
        else:
            ids = pts
        for i in ids:
            bs.Select(i)
        _set_marker(tag, KIND_TAG)
        obj.InsertTag(tag, obj.GetLastTag())
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, tag)

        d = _new_deformer(doc, dtype)
        d.SetName(_deformer_name(dtype, tag.GetName()))
        mat = _configure(d, dtype, tag, info, axes, limit=limit)
        _set_marker(d, KIND_DEFORMER, tag)
        d.InsertUnderLast(obj)
        d.SetMl(mat)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, d)

        doc.AddUndo(c4d.UNDOTYPE_BITS, obj)
        doc.SetActiveObject(d, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return d


def _create_whole(doc, obj, dtype):
    """全体用のデフォーマーを obj の子に作る（選択範囲タグもフィールドのレイヤーも入れない）。

    箱は子オブジェクトも含めた今の形に合わせ、向きはオブジェクトの軸（いちばん長い軸が主軸）、
    起点はその軸のマイナス側の端（whole_frame）。
    """
    info = whole_info(obj, doc)
    axes = whole_frame(info) if dtype in BOX_TYPES else None
    doc.StartUndo()
    try:
        d = _new_deformer(doc, dtype)
        d.SetName(_deformer_name(dtype, WHOLE_LABEL))
        mat = _configure(d, dtype, None, info, axes)
        _set_marker(d, KIND_DEFORMER, whole=True)
        d.InsertUnderLast(obj)
        d.SetMl(mat)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, d)
        doc.AddUndo(c4d.UNDOTYPE_BITS, obj)
        doc.SetActiveObject(d, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return d


def switch_type(doc, deformer, dtype, limit=True):
    """プラグイン製デフォーマーを別の種類に入れ替える（箱・向き・タグはそのまま）。

    箱の種類同士はフィールドごと引き継ぐので「選択範囲に限定」もそのまま。
    ベベルから箱の種類にするときだけ、limit で限定するかを決める。
    """
    if dtype not in DEFORMER_TYPES:
        raise SDError(tr("未対応のデフォーマーです。", "Unsupported deformer type."))
    old_type = deformer.GetType()
    if old_type == dtype:
        return deformer
    _stop_threads()
    whole = is_whole(deformer)
    if whole:
        mesh = _parent_of(deformer)
        old_tag = None
        whole_shape = whole_info(mesh, doc)
    else:
        mesh = _mesh_of(deformer)
        old_tag = get_selection_tag(deformer)
        if old_tag is None:
            raise SDError(tr("「%s」が使う選択範囲タグが見つかりません。", "Cannot find the selection tag used by \"%s\".") % deformer.GetName())

    doc.StartUndo()
    try:
        if whole:
            tag, info, label_old, label_new = None, whole_shape, WHOLE_LABEL, WHOLE_LABEL
        else:
            tag = _usable_tag(doc, mesh, old_tag, dtype)
            info = selection_from_tag(mesh, tag)
            label_old, label_new = old_tag.GetName(), tag.GetName()
        new = _new_deformer(doc, dtype)
        # 名前: プラグインが付けた名前のままなら種類名を差し替える
        if deformer.GetName() == _deformer_name(old_type, label_old):
            new.SetName(_deformer_name(dtype, label_new))
        else:
            new.SetName(deformer.GetName())
        for pid in (
            c4d.ID_BASEOBJECT_VISIBILITY_EDITOR,
            c4d.ID_BASEOBJECT_VISIBILITY_RENDER,
            c4d.ID_BASEOBJECT_USECOLOR,
            c4d.ID_BASEOBJECT_COLOR,
        ):
            new[pid] = deformer[pid]
        # 箱の種類同士: フィールド（ぼかし等を足していればそれも）、モード、方向の角度を引き継ぐ
        fields = None
        # ぼかし: 箱の種類同士なら頂点マップごと引き継ぐ。ベベルにするときは外す（下で頂点マップを消す）
        vmap = feather_tag(deformer)
        feather = (feather_width(deformer), vmap) if old_type in BOX_TYPES and dtype in BOX_TYPES else (0.0, None)
        if old_type in BOX_TYPES and dtype in BOX_TYPES:
            new[c4d.DEFORMOBJECT_MODE] = deformer[c4d.DEFORMOBJECT_MODE]
            fl = deformer[c4d.FIELDS]
            if fl is not None and (whole or _weight_source(deformer, tag) in weight_layer_targets(deformer, doc)):
                # 全体用はユーザーが足したフィールドだけなので、そのまま写す。
                # 旧版（制限タグ）のデフォーマーは make_field_list でフィールド方式に移す
                fields = fl
            if old_type in DIRECTION_ANGLE_TYPES and dtype in DIRECTION_ANGLE_TYPES:
                new[c4d.DEFORMOBJECT_ANGLE] = deformer[c4d.DEFORMOBJECT_ANGLE]
        # 強さ: 単位が同じなら引き継ぐ。違えば初期値
        amount = deformer[AMOUNT_PARAM[old_type]] if AMOUNT_UNIT[old_type] == AMOUNT_UNIT[dtype] else None
        # 旧版でシアーだけ広げていた箱も直るように、今の向きのまま箱を合わせ直す
        mat = _configure(new, dtype, tag, info, _axes_for(deformer, info), amount, fields, limit)
        new.SetDeformMode(deformer.GetDeformMode())
        layer = deformer.GetLayerObject(doc)
        if layer is not None:
            new.SetLayerObject(layer)
        t = deformer.GetFirstTag()
        while t:
            if t.GetType() != c4d.Trestriction:
                new.InsertTag(t.GetClone(c4d.COPYFLAGS_NONE), new.GetLastTag())
            t = t.GetNext()
        _set_marker(new, KIND_DEFORMER, tag, whole=whole, feather=feather if fields is not None else (0.0, None))

        new.InsertAfter(deformer)
        new.SetMl(mat)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, new)
        doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, deformer)
        deformer.Remove()
        if vmap is not None and feather_tag(new) is None and is_marked(vmap, KIND_FEATHER):
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, vmap)  # ベベルにした・引き継げなかったぼかしの頂点マップ
            vmap.Remove()
        # ベベル（エッジ）から箱の種類にしたときは、使われなくなったエッジ選択タグを消す
        if old_tag is not None and tag != old_tag and is_marked(old_tag, KIND_TAG) and not _tag_still_used(mesh, old_tag, []):
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old_tag)
            old_tag.Remove()
        doc.SetActiveObject(new, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return new


def add_stacked(doc, deformer, dtype, limit=True):
    """deformer と同じ選択範囲・同じ向きで、dtype のデフォーマーをすぐ後ろに重ねて追加する。

    選択範囲タグは共有する（フリーズは、どのデフォーマーにも使われなくなったときにタグを消す）。
    フィールドは元のデフォーマーのものを写すので、ぼかし等を足していればそれも同じになる。
    ベベル（エッジ）に箱の種類を重ねるときだけは、エッジの点からポイント選択タグを作る。
    「選択範囲に限定」は元のデフォーマーのフィールドと同じ。ベベルに重ねるときだけ limit で決める。
    """
    if dtype not in DEFORMER_TYPES:
        raise SDError(tr("未対応のデフォーマーです。", "Unsupported deformer type."))
    _stop_threads()
    whole = is_whole(deformer)
    if whole:
        mesh = _parent_of(deformer)
        old_tag = None
        whole_shape = whole_info(mesh, doc)
    else:
        mesh = _mesh_of(deformer)
        old_tag = get_selection_tag(deformer)
        if old_tag is None:
            raise SDError(tr("「%s」が使う選択範囲タグが見つかりません。", "Cannot find the selection tag used by \"%s\".") % deformer.GetName())

    doc.StartUndo()
    try:
        if whole:
            tag, info = None, whole_shape
        else:
            tag = _usable_tag(doc, mesh, old_tag, dtype)
            info = selection_from_tag(mesh, tag)
        new = _new_deformer(doc, dtype)
        new.SetName(_deformer_name(dtype, WHOLE_LABEL if whole else tag.GetName()))
        fields = None
        if deformer.GetType() in BOX_TYPES and dtype in BOX_TYPES:
            fl = deformer[c4d.FIELDS]
            if fl is not None and (whole or _weight_source(deformer, tag) in weight_layer_targets(deformer, doc)):
                fields = fl
        src_vmap = feather_tag(deformer) if fields is not None else None
        mat = _configure(new, dtype, tag, info, _axes_for(deformer, info), None, fields, limit)
        _set_marker(new, KIND_DEFORMER, tag, whole=whole, feather=(0.0, None))

        new.InsertAfter(deformer)
        new.SetMl(mat)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, new)
        if src_vmap is not None:
            # ぼかしはデフォーマーごとに持つ（あとで別々に変えられる）ので、頂点マップを複製して向け替える
            clone = src_vmap.GetClone(c4d.COPYFLAGS_NONE)
            clone.SetName(_unique_tag_name(mesh, FEATHER_BASENAME))
            _set_marker(clone, KIND_FEATHER)
            mesh.InsertTag(clone, src_vmap)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, clone)
            _relink_layers(new, src_vmap, clone, doc)
            _set_marker(new, KIND_DEFORMER, tag, whole=whole, feather=(feather_width(deformer), clone))
        doc.AddUndo(c4d.UNDOTYPE_BITS, deformer)
        doc.SetActiveObject(new, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return new


def _relink_fields(deformer, old_tag, new_tag, doc, limit=True):
    """フィールドの変数タグレイヤーのリンクだけを old_tag → new_tag に付け替える（ほかのレイヤーは残す）。

    old_tag=None（全体用から一部用にするとき）は、new_tag のレイヤーを足す（limit=False なら「有効」オフで）。
    ユーザーが足したレイヤーがあれば残す。
    """
    fl = deformer[c4d.FIELDS]
    root = fl.GetLayersRoot() if fl is not None else None
    if old_tag is None:
        if root is not None and root.GetDown() is not None:
            fl.InsertLayer(_new_weight_layer(new_tag, limit))
            deformer[c4d.FIELDS] = fl
        else:
            deformer[c4d.FIELDS] = make_field_list(new_tag, limit)
        return
    changed = False
    if root is not None:
        for layer in _iter_layers(root.GetDown()):
            if layer.GetType() == c4d.FLweight and layer.GetLinkedObject(doc) == old_tag:
                layer.SetLinkedObject(new_tag)
                changed = True
    deformer[c4d.FIELDS] = fl if changed else make_field_list(new_tag)


def _unlink_fields(deformer, tag, doc):
    """フィールドから tag を指す変数タグレイヤーを外す（全体用にするとき。ユーザーが足したレイヤーは残す）。"""
    if tag is None:
        return
    fl = deformer[c4d.FIELDS]
    layers = _weight_layers(fl, tag, doc)
    if not layers:
        return
    for layer in layers:
        layer.Remove()
    deformer[c4d.FIELDS] = fl


def _refit_in_place(doc, deformer, info, axes=None):
    """info の範囲に箱を合わせ直す。axes を渡せばその向き、無ければ今の向き（アンドゥは呼び出し側の StartUndo の中で）。"""
    mat, size = fit_box(info, axes if axes is not None else _axes_of(deformer), deformer.GetType())
    is_shear = deformer.GetType() == c4d.Oshear
    old_shift = shear_shift(deformer) if is_shear else 0.0
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
    deformer.SetMl(mat)
    deformer[c4d.DEFORMOBJECT_SIZE] = size
    if is_shear:
        lever = shear_lever(size, deformer[c4d.DEFORMOBJECT_ANGLE])
        if lever > EPS:
            deformer[c4d.DEFORMOBJECT_STRENGTH] = old_shift / lever
    deformer.Message(c4d.MSG_UPDATE)


def recapture_selection(doc, deformer, limit=True):
    """親メッシュの今の選択（今のモード）で、デフォーマーの選択範囲タグを取り直す。アンドゥ1回。(deformer, tag) を返す。

    - 選択の種類が今のタグと同じで、そのタグがプラグイン製なら、タグの中身を書き換える
      （同じタグを共有して重ねたデフォーマーも、それぞれの向きのまま箱を合わせ直す）。
    - 種類が違う（ポリゴン→ポイント等）か、ユーザー自身のタグなら、新しいタグを作って付け替える。
      使われなくなったプラグイン製の古いタグは消す。
    - 全体用から一部用にするときは、タグのレイヤーを足す（limit=False なら「有効」オフで）。
    - 何も選んでいない・モデルモードなどなら、全体用にする（tag は None）。
    - 向きと起点は、作成時と同じく新しい選択範囲で自動判定し直す（起点＝非選択側）。
    """
    _stop_threads()
    mesh = _parent_of(deformer)
    if not mesh.CheckType(c4d.Opolygon):
        raise SDError(tr("「%s」はメッシュになっていないので、選択を取り直せません（C キーで編集可能にすると、一部だけにかけられます）。"
                         "今の形にデフォーマーの大きさを合わせ直すときは「フィット」を使ってください。",
                         "\"%s\" is not a mesh, so the selection cannot be updated (make it editable with C to work on a part). "
                         "To fit the deformer to the current shape, use Fit.") % mesh.GetName())
    if whole_reason(doc, mesh) is not None:
        return _recapture_whole(doc, deformer, mesh), None
    dtype = deformer.GetType()
    tag_type, pts, poly_ids, _desc = selection_from_component_mode(doc, mesh)
    if len(pts) < 2:
        raise SDError(tr("選択範囲が小さすぎます（ポイント2個以上を含めてください）。", "The selection is too small (include at least 2 points)."))
    ids = pts
    if dtype == c4d.Obevel and doc.GetMode() == c4d.Medges:
        tag_type = c4d.Tedgeselection
        ids = _edge_ids_from(mesh.GetEdgeS(), mesh)
    elif tag_type == c4d.Tpolygonselection:
        ids = poly_ids
    old_tag = get_selection_tag(deformer)
    old_label = WHOLE_LABEL if is_whole(deformer) else (old_tag.GetName() if old_tag is not None else None)

    doc.StartUndo()
    try:
        if old_tag is not None and old_tag.GetType() == tag_type and is_marked(old_tag, KIND_TAG):
            tag = old_tag
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
        else:
            tag = c4d.SelectionTag(tag_type)
            tag.SetName(_unique_tag_name(mesh, SELTAG_BASENAME))
            _set_marker(tag, KIND_TAG)
            mesh.InsertTag(tag, mesh.GetLastTag())
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, tag)
        bs = tag.GetBaseSelect()
        bs.DeselectAll()
        for i in ids:
            bs.Select(i)

        doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
        if tag != old_tag:
            if old_label is not None and deformer.GetName() == _deformer_name(dtype, old_label):
                deformer.SetName(_deformer_name(dtype, tag.GetName()))
            if dtype == c4d.Obevel:
                _setup_bevel(deformer, tag)
            elif feather_tag(deformer) is None:
                _relink_fields(deformer, old_tag, tag, doc, limit)
            # ぼかしていれば、レイヤーは頂点マップを指したまま（下で新しい選択範囲で重みを測り直す）
            _set_marker(deformer, KIND_DEFORMER, tag)
        elif dtype == c4d.Obevel:
            _setup_bevel(deformer, tag)

        # 新しい選択範囲で向きと起点を自動判定し直し、箱を合わせる
        # （このデフォーマーと、同じタグを使う箱の種類のデフォーマー。重ねたもの同士は同じ向きにそろえる）
        info = selection_from_tag(mesh, tag)
        axes = auto_frame(info)
        for d in sd_deformers_under(mesh):
            if d.GetType() in BOX_TYPES and (d == deformer or get_selection_tag(d) == tag):
                _refit_in_place(doc, d, info, axes)
                _refresh_feather(doc, d, mesh, tag)

        if old_tag is not None and tag != old_tag and is_marked(old_tag, KIND_TAG) and not _tag_still_used(mesh, old_tag, []):
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old_tag)
            old_tag.Remove()
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return deformer, tag


def _recapture_whole(doc, deformer, mesh):
    """デフォーマーを全体用にする（何も選んでいないとき・モデルモードなどの「選択を取り直す」）。アンドゥ1回。

    フィールドからプラグインのタグのレイヤーを外し（ユーザーのレイヤーは残す）、使われなくなったタグは消す。
    ベベルは角だけ丸める設定にする（オフセットはそのまま）。箱は全体に合わせ、向きと起点は自動判定し直す。
    """
    dtype = deformer.GetType()
    was_whole = is_whole(deformer)
    old_tag = get_selection_tag(deformer)
    info = whole_info(mesh, doc)
    doc.StartUndo()
    try:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, deformer)
        if old_tag is not None and deformer.GetName() == _deformer_name(dtype, old_tag.GetName()):
            deformer.SetName(_deformer_name(dtype, WHOLE_LABEL))
        vmap = feather_tag(deformer)
        if dtype == c4d.Obevel:
            if not was_whole:
                _setup_bevel_whole(deformer)
        else:
            _unlink_fields(deformer, vmap if vmap is not None else old_tag, doc)
        _set_marker(deformer, KIND_DEFORMER, whole=True, feather=(0.0, None))  # 全体用には境目が無いのでぼかしも外す
        if dtype in BOX_TYPES:
            _refit_in_place(doc, deformer, info, whole_frame(info))
        if vmap is not None and is_marked(vmap, KIND_FEATHER) and not _feather_used_elsewhere(mesh, vmap, deformer):
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, vmap)
            vmap.Remove()
        if old_tag is not None and is_marked(old_tag, KIND_TAG) and not _tag_still_used(mesh, old_tag, []):
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old_tag)
            old_tag.Remove()
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return deformer


def create_or_switch(doc, dtype, add=False, limit=True):
    """パネル・メニューの種類ボタン。

    デフォーマー選択中: 通常は種類の切り替え、add=True（Shift＋クリック）なら同じ選択範囲に重ねて追加。
    それ以外: 選択範囲から作成。
    limit: 新しく選択範囲タグのレイヤーを入れるとき（作成、ベベルから箱の種類へ）に限定するか。
    """
    d = active_sd_deformer(doc)
    if d is not None:
        if add:
            return add_stacked(doc, d, dtype, limit), "add"
        return switch_type(doc, d, dtype, limit), "switch"
    return create(doc, dtype, limit), "create"


# ---------------------------------------------------------------------------
# 向きの変更・再フィット
# ---------------------------------------------------------------------------
def _reorient(doc, deformer, make_axes, refresh_feather=False):
    if is_bevel(deformer):
        raise SDError(tr("ベベルには大きさや向きがありません（選択範囲のエッジ・ポリゴン・ポイントにかかります）。", "Bevel has no size or direction (it works on the selected edges, polygons or points)."))
    _stop_threads()
    info = _info_of(deformer)
    axes = make_axes(info, _axes_of(deformer))
    mat, size = fit_box(info, axes, deformer.GetType())
    is_shear = deformer.GetType() == c4d.Oshear
    old_shift = shear_shift(deformer) if is_shear else 0.0
    doc.StartUndo()
    try:
        _apply_box(doc, deformer, mat, size)
        if is_shear:
            # シアーの強度は箱の幅に対する割合。箱が変わっても実際のずれ量が同じになるよう換算する
            lever = shear_lever(size, deformer[c4d.DEFORMOBJECT_ANGLE])
            if lever > EPS:
                deformer[c4d.DEFORMOBJECT_STRENGTH] = old_shift / lever
        if refresh_feather and not is_whole(deformer):
            # メッシュを編集したあとのフィット: 境目からの距離も変わるので、ぼかしの重みを測り直す
            _refresh_feather(doc, deformer, deformer.GetUp(), get_selection_tag(deformer))
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return deformer


def refit(doc, deformer):
    """今の向きのまま、選択範囲タグの範囲に箱を合わせ直す（ぼかしていれば、その重みも測り直す）。"""
    return _reorient(doc, deformer, lambda info, axes: axes, refresh_feather=True)


def reset_auto(doc, deformer):
    """向きを自動判定に戻して合わせ直す（全体用はオブジェクトの軸にそろえた向き）。"""
    make = whole_frame if is_whole(deformer) else auto_frame
    return _reorient(doc, deformer, lambda info, axes: make(info))


def cycle_axis(doc, deformer):
    """主軸を切り替える（今の X を新しい主軸に。起点は自動判定）。"""

    def make(info, axes):
        x, y, z = axes
        return orient_root(info, (z, x, y))

    return _reorient(doc, deformer, make)


def flip(doc, deformer):
    """起点と先端を入れ替える（X 軸まわりに 180°）。"""
    return _reorient(doc, deformer, lambda info, axes: (axes[0], -axes[1], -axes[2]))


def rotate90(doc, deformer):
    """主軸まわりに 90° 回す（曲げ・せん断の方向が変わる）。"""
    return _reorient(doc, deformer, lambda info, axes: (axes[2], axes[1], -axes[0]))


def set_root_face(doc, deformer, axis, sign):
    """箱の面 (axis: 0=X,1=Y,2=Z / sign: +1,-1) を起点にする。"""

    def make(info, axes):
        x, y, z = axes
        if axis == 1:
            return (x, -y, -z) if sign > 0 else (x, y, z)
        if axis == 0:
            ny = x * (-sign)
            return _orthonormal(y, ny)
        ny = z * (-sign)
        return _orthonormal(x, ny)

    return _reorient(doc, deformer, make)


# ---------------------------------------------------------------------------
# 起点クリック（ビュー上のクリック位置から起点の面を決める）
# ---------------------------------------------------------------------------
_collider_cache = {}


def _collider_for(op):
    key = id(op)
    dirty = op.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CACHE)
    hit = _collider_cache.get(key)
    if hit is not None and hit[0] is op and hit[1] == dirty:
        return hit[2]
    rc = c4d.utils.GeRayCollider()
    if not rc.Init(op, True):
        return None
    _collider_cache.clear()
    _collider_cache[key] = (op, dirty, rc)
    return rc


def candidate_faces(deformer):
    """起点にできる面 [(axis, sign)]。薄すぎる軸の面は除く。"""
    size = deformer[c4d.DEFORMOBJECT_SIZE]
    s = (size.x, size.y, size.z)
    biggest = max(s)
    out = []
    for axis in range(3):
        if s[axis] >= biggest * 0.15:
            out.append((axis, 1))
            out.append((axis, -1))
    return out


def face_band(deformer, axis, sign, ratio=0.15):
    """箱の面 (axis, sign) の側にある、選択範囲の「端の帯」（ポリゴンの点番号のリスト, 点番号）。

    帯の幅は、その軸の長さの ratio。起点クリックで、どこが起点になるかをメッシュの上に示すのに使う。
    帯にまるごと入るポリゴンが無ければ、帯に1点でもかかる選択ポリゴンを返す。
    """
    mesh = deformer.GetUp()
    if mesh is None or not mesh.CheckType(c4d.Opolygon):
        return [], []  # メッシュでない親（全体用）は、メッシュの点番号で描けないので帯なし
    if is_whole(deformer):
        # 描くのは親メッシュの上なので、子オブジェクトは含めずメッシュの点だけで帯を決める
        info = SelectionInfo(mesh, range(mesh.GetPointCount()), range(mesh.GetPolygonCount()))
    else:
        tag = get_selection_tag(deformer)
        if tag is None:
            return [], []
        info = selection_from_tag(mesh, tag)
    inv = ~deformer.GetMl()
    half = deformer[c4d.DEFORMOBJECT_SIZE] * 0.5
    h = (half.x, half.y, half.z)[axis]
    width = max(2.0 * h * ratio, 1e-3)
    allp = mesh.GetAllPoints()

    def coord(p):
        q = inv * p
        return (q.x, q.y, q.z)[axis]

    band = set(i for i in info.point_ids if h - sign * coord(allp[i]) <= width)
    polys = mesh.GetAllPolygons()
    source = info.poly_ids if info.poly_ids else range(len(polys))
    inside = []
    touching = []
    for i in source:
        ids = _poly_ids(polys[i])
        hits = sum(1 for v in ids if v in band)
        if hits == len(ids):
            inside.append(ids)
        elif hits and i in info.poly_ids:
            touching.append(ids)
    return (inside or touching), sorted(band)


def face_corners_world(deformer, axis, sign):
    """箱の面の4隅（ワールド座標）。"""
    size = deformer[c4d.DEFORMOBJECT_SIZE] * 0.5
    h = (size.x, size.y, size.z)
    e = (c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1))
    j, k = [i for i in range(3) if i != axis]
    c = e[axis] * (sign * h[axis])
    mg = deformer.GetMg()
    return [
        mg * (c + e[j] * (sj * h[j]) + e[k] * (sk * h[k]))
        for sj, sk in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def _face_toward(q, faces):
    """箱の中心から見て、点 q（デフォーマーのローカル）が実寸で一番離れている軸の面。

    箱は選択範囲にぴったりなので、選択した面はそのまま箱の側面上にある。
    「一番近い面」で選ぶと、付け根付近の側面をクリックしても側面が選ばれてしまう。
    中心からの距離で選べば、付け根付近→底面、先端付近→上面、長辺の中ほど→その側面になる。
    """
    comps = (q.x, q.y, q.z)
    axes = sorted(set(a for a, _s in faces))
    axis = max(axes, key=lambda a: abs(comps[a]))
    sign = 1 if comps[axis] > 0 else -1
    return axis, sign


def _ray_box(o, d, h):
    # デフォーマーのローカル空間でのレイと箱の交点（入口）。無ければ None
    tmin, tmax = -1e30, 1e30
    oc = (o.x, o.y, o.z)
    dc = (d.x, d.y, d.z)
    for i in range(3):
        if abs(dc[i]) < 1e-12:
            if oc[i] < -h[i] or oc[i] > h[i]:
                return None
            continue
        t1 = (-h[i] - oc[i]) / dc[i]
        t2 = (h[i] - oc[i]) / dc[i]
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    if tmax < 0:
        return None
    t = tmin if tmin >= 0 else tmax
    return o + d * t


def face_from_view(deformer, bd, x, y, mesh_only=False):
    """ビューのピクセル (x, y) に一番近い箱の面 (axis, sign)。決まらなければ None。

    mesh_only=True なら、対象のメッシュ（変形後の見た目）にレイが当たったときだけ面を返し、
    当たらなければ None（起点クリックで「対象の外をクリックしたら抜ける」の判定に使う）。
    """
    faces = candidate_faces(deformer)
    if not faces:
        return None
    mesh = deformer.GetUp()
    size = deformer[c4d.DEFORMOBJECT_SIZE] * 0.5
    h = (size.x, size.y, size.z)
    dmg = deformer.GetMg()
    inv_d = ~dmg

    p0 = bd.SW(c4d.Vector(x, y, 0.0))
    p1 = bd.SW(c4d.Vector(x, y, 1000.0))
    wdir = (p1 - p0).GetNormalized()

    q = None
    if mesh is not None and mesh.CheckType(c4d.Opolygon):
        # 1) 見えているメッシュ（変形後）にレイを当てる
        target = mesh.GetDeformCache() or mesh
        rc = _collider_for(target)
        if rc is not None:
            mg = mesh.GetMg()
            inv = ~mg
            lo = inv * p0
            ldir = inv.MulV(wdir).GetNormalized()
            if rc.Intersect(lo, ldir, 1e9):
                hit = rc.GetNearestIntersection()
                if hit:
                    face = hit.get("face_id", -1)
                    if 0 <= face < mesh.GetPolygonCount():
                        # 変形後のヒットを、変形前のポリゴン中心に置き換える
                        pts = mesh.GetAllPoints()
                        ids = _poly_ids(mesh.GetPolygon(face))
                        centre = sum((pts[i] for i in ids), c4d.Vector()) / len(ids)
                        q = inv_d * (mg * centre)
                    else:
                        q = inv_d * (mg * hit["hitpos"])
    if q is None and mesh_only:
        return None
    if q is None:
        # 2) 箱そのものにレイを当てる
        q = _ray_box(inv_d * p0, inv_d.MulV(wdir).GetNormalized(), h)
    if q is not None:
        return _face_toward(q, faces)
    # 3) 画面上で一番近い面の中心
    best = None
    for axis, sign in faces:
        e = (c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1))[axis]
        sp = bd.WS(dmg * (e * (sign * h[axis])))
        d2 = (sp.x - x) ** 2 + (sp.y - y) ** 2
        if best is None or d2 < best[0]:
            best = (d2, (axis, sign))
    return best[1] if best else None


# ---------------------------------------------------------------------------
# フリーズ
# ---------------------------------------------------------------------------
def _deformers_affecting(mesh, exclude):
    """mesh を変形しうる有効なデフォーマー（mesh と祖先の直下にあるもの）。"""
    out = []
    node = mesh
    while node is not None:
        child = node.GetDown()
        while child:
            if child is not exclude and (child.GetInfo() & c4d.OBJECT_MODIFIER) and child.GetDeformMode():
                out.append(child)
            child = child.GetNext()
        node = node.GetUp()
    return out


def _evaluate_only(doc, mesh, deformer):
    """deformer だけを効かせたときの mesh のポイント（ローカル座標）。"""
    others = _deformers_affecting(mesh, deformer)
    was_on = deformer.GetDeformMode()
    try:
        for o in others:
            o.SetDeformMode(False)
        deformer.SetDeformMode(True)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        cache = mesh.GetDeformCache()
        if cache is None:
            raise SDError(tr("「%s」の変形結果を取得できませんでした。", "Could not get the deformed result of \"%s\".") % mesh.GetName())
        pts = cache.GetAllPoints()
    finally:
        for o in others:
            o.SetDeformMode(True)
        deformer.SetDeformMode(was_on)
    if len(pts) != mesh.GetPointCount():
        raise SDError(tr("「%s」の変形結果のポイント数が元と違います。", "The deformed result of \"%s\" has a different point count.") % mesh.GetName())
    return pts


def _apply_bevel_tool(doc, mesh, bevel, tag):
    """ベベルデフォーマーと同じ設定で、ベベルツール（ID_XBEVELTOOL）を mesh に直接かける。

    ベベルは面を増やす（トポロジーが変わる）ので、ポイント位置の書き戻しでは焼き込めない。
    ツールならオブジェクトを作り直さずに、UV・選択範囲タグ・Nゴンも更新される。
    C4D 2027 で、点・エッジ・ポリゴンの3モードともデフォーマーと同じ形になることを確認済み。
    全体用（タグなし）は、ツールに「角度を使う」が無いので、デフォーマーと同じ基準で角のエッジを選んでからかける。
    """
    mode = bevel[c4d.O_BEVEL_MODE_COMPONENT_TYPE]
    selection = {0: mesh.GetPointS, 1: mesh.GetEdgeS, 2: mesh.GetPolygonS}[mode]()
    if is_whole(bevel):
        if mode == BEVEL_MODE_EDGES:
            if bevel[c4d.O_BEVEL_MODE_SELECTION_ANGLE_USE]:
                ids = sharp_edge_ids(mesh, bevel[c4d.O_BEVEL_MODE_SELECTION_ANGLE_VAL], BEVEL_WHOLE_BOUNDARY)
            else:
                ids = _all_edge_ids(mesh)
        else:
            ids = range(mesh.GetPointCount() if mode == 0 else mesh.GetPolygonCount())
        if not ids:
            # 丸める角が無い（平らな板など）。デフォーマーも何もしていないので形はそのまま。
            # 選択なしでツールをかけると「全部」になってしまうので、かけない
            return
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, mesh)
        selection.DeselectAll()
        for i in ids:
            selection.Select(i)
    else:
        if tag is None:
            raise SDError(tr("「%s」が使う選択範囲タグが見つかりません。", "Cannot find the selection tag used by \"%s\".") % bevel.GetName())
        if BEVEL_MODE_FOR_TAG.get(tag.GetType()) != mode:
            raise SDError(tr("「%s」のコンポーネントモードと、選択範囲タグ「%s」の種類が合いません。", "The component mode of \"%s\" does not match the type of the selection tag \"%s\".") % (bevel.GetName(), tag.GetName()))
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, mesh)
        tag.GetBaseSelect().CopyTo(selection)
    bc = c4d.BaseContainer()
    src = bevel.GetDataInstance()
    for pid in BEVEL_TOOL_PARAMS:
        if src.GetType(pid) == c4d.DA_ALIASLINK:
            link = src.GetLink(pid, doc)
            if link is not None:
                bc.SetLink(pid, link)
            continue
        value = src.GetData(pid)
        if value is not None:
            bc.SetData(pid, value)
    ok = c4d.utils.SendModelingCommand(c4d.ID_XBEVELTOOL, [mesh], BEVEL_TOOL_MODE[mode], bc, doc)
    if not ok:
        raise SDError(tr("「%s」を焼き込めませんでした（ベベルツールが失敗しました）。", "Could not bake \"%s\" (the Bevel tool failed).") % bevel.GetName())
    mesh.Message(c4d.MSG_UPDATE)


def _tag_still_used(mesh, tag, removed):
    for d in sd_deformers_under(mesh):
        if d in removed:
            continue
        if get_selection_tag(d) == tag:
            return True
    return False


def freeze(doc, deformers):
    """デフォーマーの変形を元のポリゴンに書き込み、デフォーマーとプラグイン製タグを消す。
    オブジェクトは作り直さないので、タグ・マテリアル・UV・階層はそのまま残る。アンドゥは1回。"""
    if not deformers:
        raise SDError(tr("フリーズするPartDeform のデフォーマーがありません。デフォーマーか、その親のオブジェクトを選択してください。", "No PartDeform deformer to freeze. Select a deformer or its parent object."))
    for d in deformers:
        parent = d.GetUp()
        if is_whole(d) and parent is not None and not parent.CheckType(c4d.Opolygon):
            raise SDError(tr("「%s」はメッシュになっていない「%s」にかけているので、フリーズできません"
                             "（C キーで編集可能にしてから、もう一度フリーズしてください）。",
                             "\"%s\" works on \"%s\", which is not a mesh, so it cannot be frozen "
                             "(make it editable with C, then freeze again).") % (d.GetName(), parent.GetName()))
        _mesh_of(d)
    _stop_threads()
    meshes = []
    removed = []
    doc.StartUndo()
    try:
        for d in deformers:
            mesh = _mesh_of(d)
            tag = get_selection_tag(d)
            vmap = feather_tag(d)
            if is_bevel(d):
                _apply_bevel_tool(doc, mesh, d, tag)
            else:
                pts = _evaluate_only(doc, mesh, d)  # ぼかしの重みも効いた形
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, mesh)
                mesh.SetAllPoints(pts)
                mesh.Message(c4d.MSG_UPDATE)
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, d)
            d.Remove()
            removed.append(d)
            if vmap is not None and is_marked(vmap, KIND_FEATHER) and not _feather_used_elsewhere(mesh, vmap, d):
                doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, vmap)
                vmap.Remove()
            if tag is not None and is_marked(tag, KIND_TAG) and not _tag_still_used(mesh, tag, removed):
                doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, tag)
                tag.Remove()
            if mesh not in meshes:
                meshes.append(mesh)
        if meshes:
            for m in meshes:
                doc.AddUndo(c4d.UNDOTYPE_BITS, m)
            doc.SetActiveObject(meshes[0], c4d.SELECTION_NEW)
            for m in meshes[1:]:
                doc.SetActiveObject(m, c4d.SELECTION_ADD)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return meshes
