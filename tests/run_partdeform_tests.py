# -*- coding: utf-8 -*-
"""PartDeform の通しテスト（C4D 2027 のスクリプトマネージャーで実行）。

新しいドキュメントを作り、3パターン（突起・平らな面・エッジ選択）で
登録済みのコマンドを呼んで、作成（フィールドで限定）・保存→再読込・種類の切り替え・
再フィット・フリーズ・アンドゥを確かめる。
ユーザーのドキュメントには触らない。結果はコンソールに出る。
"""
import math
import os
import tempfile

import c4d

from partdeform import core, i18n, ui

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("OK   " if cond else "FAIL ") + name + (("  " + detail) if detail else ""))


def make_editable(doc, prim):
    doc.InsertObject(prim)
    res = c4d.utils.SendModelingCommand(c4d.MCOMMAND_MAKEEDITABLE, [prim], c4d.MODELINGCOMMANDMODE_ALL, c4d.BaseContainer(), doc)
    obj = res[0]
    doc.InsertObject(obj)
    return obj


def build_scene(doc):
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    mat.SetName("TestMat")
    doc.InsertMaterial(mat)

    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 3
    cube.SetName("Protrusion")
    cube = make_editable(doc, cube)
    pts = cube.GetAllPoints()
    ps = cube.GetPolygonS()
    ps.DeselectAll()
    for i, p in enumerate(cube.GetAllPolygons()):
        c = (pts[p.a] + pts[p.b] + pts[p.c] + pts[p.d]) / 4
        if abs(c.y - 100) < 1e-3 and abs(c.x) < 1e-3 and abs(c.z) < 1e-3:
            ps.Select(i)
    bc = c4d.BaseContainer()
    bc[c4d.MDATA_EXTRUDE_OFFSET] = 200.0
    bc[c4d.MDATA_EXTRUDE_SUBDIVISION] = 6
    c4d.utils.SendModelingCommand(c4d.ID_MODELING_EXTRUDE_TOOL, [cube], c4d.MODELINGCOMMANDMODE_POLYGONSELECTION, bc, doc)
    cube.SetRelPos(c4d.Vector(-500, 0, 0))
    probe = c4d.BaseObject(c4d.Ocube)
    probe[c4d.PRIM_CUBE_LEN] = c4d.Vector(20)
    probe.SetName("ChildProbe")
    probe = make_editable(doc, probe)
    probe.Remove()
    doc.InsertObject(probe, parent=cube)
    probe.SetRelPos(c4d.Vector(0, 280, 0))

    plane = c4d.BaseObject(c4d.Oplane)
    plane[c4d.PRIM_PLANE_WIDTH] = plane[c4d.PRIM_PLANE_HEIGHT] = 400
    plane[c4d.PRIM_PLANE_SUBW] = plane[c4d.PRIM_PLANE_SUBH] = 20
    plane.SetName("FlatPatch")
    plane = make_editable(doc, plane)

    cyl = c4d.BaseObject(c4d.Ocylinder)
    cyl[c4d.PRIM_CYLINDER_RADIUS] = 50
    cyl[c4d.PRIM_CYLINDER_HEIGHT] = 300
    cyl[c4d.PRIM_CYLINDER_HSUB] = 12
    cyl[c4d.PRIM_CYLINDER_SEG] = 16
    cyl.SetName("EdgeTube")
    cyl = make_editable(doc, cyl)
    cyl.SetRelPos(c4d.Vector(500, 0, 0))

    # 円柱の側面から -Z 方向に押し出した突起（主軸が円柱の軸と紛らわしい形）
    boss = c4d.BaseObject(c4d.Ocylinder)
    boss[c4d.PRIM_CYLINDER_RADIUS] = 50
    boss[c4d.PRIM_CYLINDER_HEIGHT] = 200
    boss[c4d.PRIM_CYLINDER_HSUB] = 4
    boss[c4d.PRIM_CYLINDER_SEG] = 16
    boss.SetName("SideBoss")
    boss = make_editable(doc, boss)
    select_polys(boss, lambda c: c.z < -45)
    bc = c4d.BaseContainer()
    bc[c4d.MDATA_EXTRUDE_OFFSET] = 150.0
    bc[c4d.MDATA_EXTRUDE_SUBDIVISION] = 3
    c4d.utils.SendModelingCommand(c4d.ID_MODELING_EXTRUDE_TOOL, [boss], c4d.MODELINGCOMMANDMODE_POLYGONSELECTION, bc, doc)
    boss.SetRelPos(c4d.Vector(0, 0, -600))

    for o in (cube, plane, cyl, boss):
        t = o.MakeTag(c4d.Ttexture)
        t[c4d.TEXTURETAG_MATERIAL] = mat
        t[c4d.TEXTURETAG_PROJECTION] = c4d.TEXTURETAG_PROJECTION_UVW
    c4d.EventAdd()
    return cube, plane, cyl


def centre(pts, p):
    ids = core._poly_ids(p)
    return sum((pts[i] for i in ids), c4d.Vector()) / len(ids)


def select_polys(obj, pred):
    pts = obj.GetAllPoints()
    bs = obj.GetPolygonS()
    bs.DeselectAll()
    for i, p in enumerate(obj.GetAllPolygons()):
        if pred(centre(pts, p)):
            bs.Select(i)


def select_edges(obj, pred):
    pts = obj.GetAllPoints()
    es = obj.GetEdgeS()
    es.DeselectAll()
    for i, p in enumerate(obj.GetAllPolygons()):
        for side, (a, b) in enumerate(((p.a, p.b), (p.b, p.c), (p.c, p.d), (p.d, p.a))):
            if a != b and pred(pts[a]) and pred(pts[b]):
                es.Select(i * 4 + side)


def snapshot(doc, name):
    o = doc.SearchObject(name)
    uv = o.GetTag(c4d.Tuvw)
    return {
        "points": o.GetAllPoints(),
        "tags": [(t.GetType(), t.GetName()) for t in o.GetTags()],
        "children": [c.GetName() for c in o.GetChildren()],
        "uv": [uv.GetSlow(i) for i in range(uv.GetDataCount())] if uv else None,
        "polys": o.GetPolygonCount(),
    }


def max_diff(a, b):
    return max((a[i] - b[i]).GetLength() for i in range(len(a))) if a else 0.0


def deformed_points(doc, obj):
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    cache = obj.GetDeformCache()
    return cache.GetAllPoints() if cache else obj.GetAllPoints()


def box_fits(d, info):
    """箱の大きさが、今の向きでの選択範囲の幅と一致するか（薄い軸は最小サイズまで）。"""
    m = d.GetMl()
    axes = core._orthonormal(m.v1, m.v2)
    ext = [hi - lo for lo, hi in (core._extent(info.points, a) for a in axes)]
    minimum = max(max(ext) * core.MIN_SIZE_RATIO, 1e-3)
    size = d[c4d.DEFORMOBJECT_SIZE]
    return all(abs(s - max(e, minimum)) < 1e-3 for s, e in zip((size.x, size.y, size.z), ext))


def max_shift(doc, obj, before_points):
    pts = deformed_points(doc, obj)
    return max((pts[i] - before_points[i]).GetLength() for i in range(len(pts)))


def test_face_shear(doc):
    """立方体の平らな面にシアー: 箱は面にぴったり、ずれ量は長さの約20%、90°回転してもずれ量は同じ。"""
    print("--- FaceShear ---")
    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 4
    cube.SetName("FaceShear")
    cube = make_editable(doc, cube)
    cube.SetRelPos(c4d.Vector(0, 0, 600))
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(cube, lambda c: c.x > 99)
    before = cube.GetAllPoints()

    c4d.CallCommand(core.ID_CMD_SHEAR)
    d = core.active_sd_deformer(doc)
    check("FaceShear: シアーを作成", d is not None and d.GetType() == c4d.Oshear)
    if d is None:
        return
    info = core.selection_from_tag(cube, core.get_selection_tag(d))
    size = d[c4d.DEFORMOBJECT_SIZE]
    check("FaceShear: 箱は面にぴったり", box_fits(d, info), str(size))
    check("FaceShear: 薄い方向（法線）が X", abs(abs(d.GetMl().v1.x) - 1.0) < 1e-6 and size.x < 0.1 * size.y, str(d.GetMl().v1))
    shift = max_shift(doc, cube, before)
    check("FaceShear: ずれ量は長さの約20%", abs(shift - 0.2 * size.y) < 0.05 * size.y, "%.2f / %.2f" % (shift, size.y))

    ui.do_reorient(doc, core.refit, None)  # パネルの「フィット」と同じ処理
    shift_refit = max_shift(doc, cube, before)
    check("FaceShear: 再フィットでずれ量が変わらない", abs(shift_refit - shift) < 1e-3, "%.3f -> %.3f" % (shift, shift_refit))
    core.rotate90(doc, core.active_sd_deformer(doc))
    d = core.active_sd_deformer(doc)
    shift_rot = max_shift(doc, cube, before)
    check("FaceShear: 90°回転しても箱はぴったり", box_fits(d, info), str(d[c4d.DEFORMOBJECT_SIZE]))
    check("FaceShear: 90°回転してもずれ量が同じ", abs(shift_rot - shift) < 0.05 * shift, "%.2f -> %.2f" % (shift, shift_rot))

    # ずれ量を長さで指定（パネルの「シアーの先端のずれ」と同じ処理）
    check("FaceShear: 表示のずれ量＝実際のずれ量", abs(core.shear_shift(d) - shift_rot) < 1e-3, "%.3f / %.3f" % (core.shear_shift(d), shift_rot))
    core.set_shear_shift(doc, d, 25.0)
    got = max_shift(doc, cube, before)
    check("FaceShear: ずれ量 25 を指定→実際に 25 ずれる", abs(got - 25.0) < 1e-3, "%.4f（強度 %.1f%%）" % (got, d[c4d.DEFORMOBJECT_STRENGTH] * 100))
    d[c4d.DEFORMOBJECT_ANGLE] = math.radians(30.0)
    strength_before = d[c4d.DEFORMOBJECT_STRENGTH]
    core.set_shear_shift(doc, d, 12.5)
    got = max_shift(doc, cube, before)
    check("FaceShear: 角度 30° でもずれ量の指定どおり", abs(got - 12.5) < 1e-3, "%.4f" % got)
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    d = core.sd_deformers_under(doc.SearchObject("FaceShear"))[0]
    check("FaceShear: ずれ量の指定はアンドゥ1回で戻る", abs(d[c4d.DEFORMOBJECT_STRENGTH] - strength_before) < 1e-9,
          "%.4f / %.4f" % (d[c4d.DEFORMOBJECT_STRENGTH], strength_before))

    # テーパー・膨張も長さで指定（いちばん外側の点が、箱の幅の広い方向にその量だけ動く）
    for dtype, cmd, label in ((c4d.Otaper, core.ID_CMD_TAPER, "テーパー"), (c4d.Obulge, core.ID_CMD_BULGE, "膨張")):
        doc.SetActiveObject(d, c4d.SELECTION_NEW)
        c4d.CallCommand(cmd)
        d = core.active_sd_deformer(doc)
        if d is None or d.GetType() != dtype:
            check("FaceShear: %sに切り替え" % label, False)
            continue
        core.set_amount_length(doc, d, 10.0)
        m = d.GetMl()
        size = d[c4d.DEFORMOBJECT_SIZE]
        wide = m.v1.GetNormalized() if size.x >= size.z else m.v3.GetNormalized()
        pts = deformed_points(doc, cube)
        moved = max(abs((pts[i] - before[i]).Dot(wide)) for i in range(len(pts)))
        check("FaceShear: %s 10 を指定→外側の点が 10 動く" % label, abs(moved - 10.0) < 1e-3 and abs(core.amount_length(d) - 10.0) < 1e-6,
              "%.4f（強度 %.1f%%）" % (moved, d[c4d.DEFORMOBJECT_STRENGTH] * 100))


def test_tilted_square_patch(doc):
    """斜めに傾いた面の、正方形に近い選択（周りは未選択）: 箱の向きがパッチのエッジに揃い、大きさもぴったり。

    ユーザーのシーン（立方体の斜めの面で 2×2 を選んでシアー）で H 角度がずれた件の再現。
    """
    print("--- TiltedSquare ---")
    plane = c4d.BaseObject(c4d.Oplane)
    plane[c4d.PRIM_PLANE_WIDTH] = plane[c4d.PRIM_PLANE_HEIGHT] = 400
    plane[c4d.PRIM_PLANE_SUBW] = plane[c4d.PRIM_PLANE_SUBH] = 4
    plane.SetName("TiltedSquare")
    plane = make_editable(doc, plane)
    plane.SetRelPos(c4d.Vector(0, 300, -600))
    # 面を Z 軸まわりに 32°、Y 軸まわりに 20° 傾ける（ポイントを直接回す。オブジェクトの軸はそのまま）
    rot = c4d.utils.HPBToMatrix(c4d.Vector(math.radians(20.0), 0.0, math.radians(32.0)))
    plane.SetAllPoints([rot * p for p in plane.GetAllPoints()])
    plane.Message(c4d.MSG_UPDATE)
    edge_u = (rot * c4d.Vector(1, 0, 0) - rot * c4d.Vector(0, 0, 0)).GetNormalized()
    edge_v = (rot * c4d.Vector(0, 0, 1) - rot * c4d.Vector(0, 0, 0)).GetNormalized()
    doc.SetActiveObject(plane, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    inv = ~rot
    select_polys(plane, lambda c: abs((inv * c).x) < 100 and abs((inv * c).z) < 100)  # 中央の 2×2
    d, how = core.create_or_switch(doc, c4d.Oshear)
    m = d.GetMl()
    y = m.v2.GetNormalized()
    z = m.v3.GetNormalized()
    aligned = max(abs(y.Dot(edge_u)), abs(y.Dot(edge_v))) > 0.9999 and max(abs(z.Dot(edge_u)), abs(z.Dot(edge_v))) > 0.9999
    check("TiltedSquare: 箱の向きがパッチのエッジに揃う", aligned, "Y=%s Z=%s" % (y, z))
    size = d[c4d.DEFORMOBJECT_SIZE]
    check("TiltedSquare: 箱の大きさが選択範囲ぴったり（200×200）", abs(size.y - 200) < 0.01 and abs(size.z - 200) < 0.01, str(size))


def test_recapture(doc):
    """選択を取り直す: 同じ種類ならタグを書き換えて箱を合わせ直す。種類が変われば付け替えて古いタグを消す。アンドゥ1回。"""
    print("--- Recapture ---")
    plane = c4d.BaseObject(c4d.Oplane)
    plane[c4d.PRIM_PLANE_WIDTH] = plane[c4d.PRIM_PLANE_HEIGHT] = 400
    plane[c4d.PRIM_PLANE_SUBW] = plane[c4d.PRIM_PLANE_SUBH] = 20
    plane.SetName("Recapture")
    plane = make_editable(doc, plane)
    plane.SetRelPos(c4d.Vector(600, 0, -600))
    original = plane.GetAllPoints()
    doc.SetActiveObject(plane, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(plane, lambda c: c.x > 0 and abs(c.z) < 60)
    d, _how = core.create_or_switch(doc, c4d.Obend)
    tag = core.get_selection_tag(d)

    # 別の場所を選び直して（メッシュの選択はデフォーマーを選んでも残る）、取り直す
    select_polys(plane, lambda c: c.x < -100 and abs(c.z) < 40)
    want = set(i for i, f in enumerate(plane.GetPolygonS().GetAll(plane.GetPolygonCount())) if f)
    doc.SetActiveObject(d, c4d.SELECTION_NEW)
    d, tag2 = core.recapture_selection(doc, d)
    got = set(i for i, f in enumerate(tag2.GetBaseSelect().GetAll(plane.GetPolygonCount())) if f)
    check("Recapture: 同じ種類なら同じタグを書き換える", tag2 == tag and got == want, "%d polys" % len(got))
    info = core.selection_from_tag(plane, tag2)
    check("Recapture: 箱が新しい選択範囲に合う", box_fits(d, info) and d.GetMl().off.x < -100, str(d.GetMl().off))
    # 新しい範囲は板の外周（x=-200）側。非選択側は内側の x=-100 なので、起点は x=-100、主軸は -X 向き
    m = d.GetMl()
    bottom = m.off - m.v2 * (d[c4d.DEFORMOBJECT_SIZE].y * 0.5)
    check("Recapture: 起点を判定し直す（非選択側）", (m.v2 - c4d.Vector(-1, 0, 0)).GetLength() < 1e-6 and abs(bottom.x + 100) < 1e-3,
          "Y=%s 起点=%s" % (m.v2, bottom))
    moved = deformed_points(doc, plane)
    inside = set(info.point_ids)
    outside_move = max((moved[i] - original[i]).GetLength() for i in range(len(original)) if i not in inside)
    check("Recapture: 新しい選択範囲の外は動かない", outside_move < 1e-4, "%.5f" % outside_move)

    # ポイントで選び直す → ポイント選択タグに付け替え、古いポリゴン選択タグは消える
    doc.SetMode(c4d.Mpoints)
    ps = plane.GetPointS()
    ps.DeselectAll()
    for i, p in enumerate(plane.GetAllPoints()):
        if p.x > 100 and abs(p.z) < 50:
            ps.Select(i)
    d, tag3 = core.recapture_selection(doc, d)
    check("Recapture: 種類が変わればポイント選択タグに付け替え", tag3.GetType() == c4d.Tpointselection and core.weight_layer_targets(d, doc) == [tag3])
    check("Recapture: 古いポリゴン選択タグは消える", plane.GetTag(c4d.Tpolygonselection) is None
          or not plane.GetTag(c4d.Tpolygonselection).GetName().startswith(core.SELTAG_BASENAME))
    c4d.StopAllThreads()
    doc.DoUndo()
    plane = doc.SearchObject("Recapture")
    d = core.sd_deformers_under(plane)[0]
    t = core.get_selection_tag(d)
    check("Recapture: アンドゥ1回で前の選択範囲に戻る", t is not None and t.GetType() == c4d.Tpolygonselection
          and d.GetMl().off.x < -100, t.GetName() if t else "")

    # ベベル（エッジ）も取り直せる
    doc.SetActiveObject(plane, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Medges)
    select_edges(plane, lambda p: abs(p.z) < 1 and p.x > 0)
    b, _how = core.create(doc, c4d.Obevel), None
    btag = core.get_selection_tag(b)
    select_edges(plane, lambda p: abs(p.x) < 1 and p.z > 0)
    want_edges = set(core._edge_ids_from(plane.GetEdgeS(), plane))
    doc.SetActiveObject(b, c4d.SELECTION_NEW)
    b, btag2 = core.recapture_selection(doc, b)
    got_edges = set(core._edge_ids_from(btag2.GetBaseSelect(), plane))
    check("Recapture: ベベルのエッジも取り直せる", btag2 == btag and btag2.GetType() == c4d.Tedgeselection and got_edges == want_edges
          and b[core.BEVEL_SELECTION] == btag2.GetName(), "%d edges" % len(got_edges))


def test_add_stacked(doc):
    """Shift＋クリックの「追加」: 同じ選択範囲・同じ向きで重ね、フリーズで両方の変形が焼き込まれ、タグも消える。"""
    print("--- AddStacked ---")
    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 4
    cube.SetName("AddStacked")
    cube = make_editable(doc, cube)
    cube.SetRelPos(c4d.Vector(600, 0, 600))
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(cube, lambda c: c.y > 99)
    c4d.CallCommand(core.ID_CMD_TAPER)
    first = core.active_sd_deformer(doc)
    d2, how = core.create_or_switch(doc, c4d.Otwist, add=True)
    check("AddStacked: 追加になる", how == "add" and d2.GetType() == c4d.Otwist)
    ds = core.sd_deformers_under(cube)
    check("AddStacked: 2つ重なり、元は残る", len(ds) == 2 and ds[0].GetType() == c4d.Otaper and ds[1].GetType() == c4d.Otwist,
          str([x.GetName() for x in ds]))
    check("AddStacked: 同じ選択範囲タグを共有", core.get_selection_tag(ds[0]) == core.get_selection_tag(ds[1]))
    check("AddStacked: 同じ向き", (ds[0].GetMl().v2 - ds[1].GetMl().v2).GetLength() < 1e-6 and (ds[0].GetMl().off - ds[1].GetMl().off).GetLength() < 1e-6)
    check("AddStacked: 追加したものが選択される", core.active_sd_deformer(doc) == ds[1])
    expected = deformed_points(doc, cube)
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    ui.do_freeze(doc)  # パネルの「フリーズ」と同じ処理
    cube = doc.SearchObject("AddStacked")
    frozen = cube.GetAllPoints()
    check("AddStacked: フリーズで両方の変形が焼き込まれる", max_diff(frozen, expected) < 1e-3, "%.5f" % max_diff(frozen, expected))
    check("AddStacked: 共有タグも消える", not any(t.GetName().startswith(core.SELTAG_BASENAME) for t in cube.GetTags()) and not core.sd_deformers_under(cube))
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    cube = doc.SearchObject("AddStacked")
    check("AddStacked: アンドゥ1回で2つとも戻る", len(core.sd_deformers_under(cube)) == 2)


def test_panel_rows(doc):
    """パネルの数値欄: 屈曲・ツイストは1段目（量）が角度、屈曲・シアーは2段目（方向）に角度。
    シアーは向きを変えても先端のずれ量を保つ。どれもアンドゥ1回で戻る。"""
    print("--- PanelRows ---")

    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 4
    cube.SetName("PanelRows")
    cube = make_editable(doc, cube)
    cube.SetRelPos(c4d.Vector(-600, 0, 600))
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(cube, lambda c: c.y > 99)
    before = cube.GetAllPoints()
    deg = math.radians

    # 屈曲: 1段目＝強度（曲げる角度）、2段目＝角度（曲げる向き）
    c4d.CallCommand(core.ID_CMD_BEND)
    d = core.active_sd_deformer(doc)
    check("PanelRows: 屈曲を作成", d is not None and d.GetType() == c4d.Obend)
    if d is None:
        return
    row = core.amount_row(d)
    check("PanelRows: 屈曲の1段目は強度（角度、スライダー ±360°）",
          row is not None and row[1] == core.UNIT_ANGLE and abs(row[2] - d[c4d.DEFORMOBJECT_STRENGTH]) < 1e-9
          and abs(row[3][1] - deg(360.0)) < 1e-9, str(row))
    ui.do_amount(doc, deg(30.0))
    check("PanelRows: 屈曲の強度を 30° に", abs(d[c4d.DEFORMOBJECT_STRENGTH] - deg(30.0)) < 1e-9,
          "%.3f°" % math.degrees(d[c4d.DEFORMOBJECT_STRENGTH]))
    row = core.direction_row(d)
    check("PanelRows: 屈曲の2段目は角度（向き）", row is not None and row[1] == core.UNIT_ANGLE, str(row))
    angle_before = d[c4d.DEFORMOBJECT_ANGLE]
    ui.do_direction(doc, deg(90.0))
    check("PanelRows: 屈曲の向きを 90° に（強度はそのまま）",
          abs(d[c4d.DEFORMOBJECT_ANGLE] - deg(90.0)) < 1e-9 and abs(d[c4d.DEFORMOBJECT_STRENGTH] - deg(30.0)) < 1e-9)
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    cube = doc.SearchObject("PanelRows")
    d = core.sd_deformers_under(cube)[0]
    check("PanelRows: 屈曲の向きはアンドゥ1回で戻る",
          abs(d[c4d.DEFORMOBJECT_ANGLE] - angle_before) < 1e-9 and abs(d[c4d.DEFORMOBJECT_STRENGTH] - deg(30.0)) < 1e-9)

    # ツイスト: 1段目＝角度（ひねる角度）、2段目は無し
    doc.SetActiveObject(d, c4d.SELECTION_NEW)
    c4d.CallCommand(core.ID_CMD_TWIST)
    d = core.active_sd_deformer(doc)
    row = core.amount_row(d)
    check("PanelRows: ツイストの1段目は角度",
          d.GetType() == c4d.Otwist and row is not None and row[1] == core.UNIT_ANGLE
          and abs(row[2] - d[c4d.DEFORMOBJECT_ANGLE]) < 1e-9, str(row))
    check("PanelRows: ツイストに2段目は無い", core.direction_row(d) is None)
    ui.do_amount(doc, deg(-120.0))
    moved = max_shift(doc, cube, before)
    check("PanelRows: ツイストの角度を -120° に（実際にひねれる）",
          abs(d[c4d.DEFORMOBJECT_ANGLE] - deg(-120.0)) < 1e-9 and moved > 1.0, "動いた量 %.2f" % moved)

    # テーパー: 1段目は長さ、2段目は無し
    c4d.CallCommand(core.ID_CMD_TAPER)
    d = core.active_sd_deformer(doc)
    row = core.amount_row(d)
    check("PanelRows: テーパーの1段目は長さ、2段目は無し",
          d.GetType() == c4d.Otaper and row is not None and row[1] == core.UNIT_LENGTH and core.direction_row(d) is None)

    # シアー: 2段目＝角度（ずらす向き）。向きを変えても先端のずれ量は保つ
    c4d.CallCommand(core.ID_CMD_SHEAR)
    d = core.active_sd_deformer(doc)
    row = core.direction_row(d)
    check("PanelRows: シアーの2段目は角度（向き）",
          d.GetType() == c4d.Oshear and row is not None and row[1] == core.UNIT_ANGLE, str(row))
    shift0 = core.shear_shift(d)
    strength0, angle0 = d[c4d.DEFORMOBJECT_STRENGTH], d[c4d.DEFORMOBJECT_ANGLE]
    ui.do_direction(doc, deg(60.0))
    got = max_shift(doc, cube, before)
    check("PanelRows: シアーの向きを 60° にしてもずれ量はそのまま",
          abs(d[c4d.DEFORMOBJECT_ANGLE] - deg(60.0)) < 1e-9 and abs(core.shear_shift(d) - shift0) < 1e-6
          and abs(got - abs(shift0)) < 1e-3, "ずれ %.4f → %.4f（強度 %.1f%% → %.1f%%）"
          % (abs(shift0), got, strength0 * 100.0, d[c4d.DEFORMOBJECT_STRENGTH] * 100.0))
    c4d.StopAllThreads()
    doc.DoUndo()
    cube = doc.SearchObject("PanelRows")
    d = core.sd_deformers_under(cube)[0]
    check("PanelRows: シアーの向きはアンドゥ1回で強度ごと戻る",
          abs(d[c4d.DEFORMOBJECT_ANGLE] - angle0) < 1e-9 and abs(d[c4d.DEFORMOBJECT_STRENGTH] - strength0) < 1e-9)

    # 屈曲で向きを 90° にしてからシアーへ: 向きを引き継ぎ、ずれは作成時と同じ（主軸の長さの 20%）
    doc.SetActiveObject(d, c4d.SELECTION_NEW)
    c4d.CallCommand(core.ID_CMD_BEND)
    ui.do_direction(doc, deg(90.0))
    c4d.CallCommand(core.ID_CMD_SHEAR)
    d = core.active_sd_deformer(doc)
    expect = core.SHEAR_DEFAULT_SHIFT * d[c4d.DEFORMOBJECT_SIZE].y
    check("PanelRows: 向き 90° の屈曲→シアーでも、ずれは主軸の長さの 20%",
          d.GetType() == c4d.Oshear and abs(d[c4d.DEFORMOBJECT_ANGLE] - deg(90.0)) < 1e-9
          and abs(core.shear_shift(d) - expect) < 1e-6, "%.3f / %.3f" % (core.shear_shift(d), expect))


def test_pick_hit(doc):
    """起点クリックの当たり判定: 対象のメッシュの上なら端が決まり、外（何もない所）なら None（＝起点モードを抜ける）。"""
    print("--- PickHit ---")
    bd = doc.GetActiveBaseDraw()
    if bd is None:
        check("PickHit: ビューがある", False)
        return
    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 4
    cube.SetName("PickHit")
    cube = make_editable(doc, cube)
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(cube, lambda c: c.y > 99)
    c4d.CallCommand(core.ID_CMD_BEND)
    d = core.active_sd_deformer(doc)
    pts = deformed_points(doc, cube)
    mg = cube.GetMg()
    # 面の中心（変形後）を画面に投影して、その画素でクリックしたことにする（その画素のレイは必ずメッシュに当たる）
    on = None
    for p in cube.GetAllPolygons():
        ids = core._poly_ids(p)
        sp = bd.WS(mg * (sum((pts[i] for i in ids), c4d.Vector()) / len(ids)))
        on = core.face_from_view(d, bd, sp.x, sp.y, mesh_only=True)
        if on is not None:
            break
    check("PickHit: メッシュの上では端が決まる", on is not None, str(on))
    # メッシュから大きく離れた点（はるか上空）を投影した画素: メッシュには当たらない
    far = bd.WS(mg.off + c4d.Vector(0, 1e5, 0))
    off = core.face_from_view(d, bd, far.x, far.y, mesh_only=True)
    fallback = core.face_from_view(d, bd, far.x, far.y)
    check("PickHit: メッシュの外では None（モードを抜ける）、従来の判定では端が決まる", off is None and fallback is not None,
          "%s / %s" % (off, fallback))


def test_legacy_marker_and_language(doc):
    """試作版（テスト用ID 1000010 の印）で作ったデフォーマーも PartDeform のデフォーマーとして扱える。
    表示言語の切り替え（日本語／英語）が効く。"""
    print("--- LegacyAndLanguage ---")
    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 2
    cube.SetName("Legacy")
    cube = make_editable(doc, cube)
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Mpolygons)
    select_polys(cube, lambda c: c.y > 99)
    c4d.CallCommand(core.ID_CMD_TWIST)
    d = core.active_sd_deformer(doc)
    tag = core.get_selection_tag(d)
    # 印を試作版のキーへ移す（試作版で保存したシーンと同じ状態）
    for node in (d, tag):
        bc = node.GetDataInstance()
        sub = bc.GetContainer(core.ID_MARKER)
        bc.RemoveData(core.ID_MARKER)
        bc.SetContainer(core.ID_MARKER_LEGACY, sub)
    check("Legacy: 試作版の印のデフォーマーも扱える",
          core.is_sd_deformer(d) and core.is_marked(tag, core.KIND_TAG) and core.sd_deformers_under(cube) == [d])
    # 試作版の印と同じキーでも、中身が自分の印の形でなければ印とみなさない
    other = c4d.BaseObject(c4d.Obend)
    bc = other.GetDataInstance()
    foreign = c4d.BaseContainer()
    foreign.SetInt32(1, 5)
    bc.SetContainer(core.ID_MARKER_LEGACY, foreign)
    check("Legacy: 他のプラグインのデータは印とみなさない", not core.is_sd_deformer(other))

    detected = i18n.language()
    try:
        i18n.set_language("en")
        en = i18n.tr("起点", "Anchor")
        i18n.set_language("ja")
        ja = i18n.tr("起点", "Anchor")
    finally:
        i18n.set_language(None)
    check("Language: 日本語／英語を切り替えられる（今の C4D の表示言語: %s）" % detected,
          en == "Anchor" and ja == "起点" and detected in i18n.LANGUAGES and i18n.language() == detected)


def sorted_points(pts):
    return sorted((round(p.x, 2), round(p.y, 2), round(p.z, 2)) for p in pts)


def test_bevel(doc):
    """ベベル: エッジから作成（名前で限定）、オフセットを長さで指定、切り替え・重ね、フリーズ（ベベルツール）とアンドゥ。"""
    print("--- Bevel ---")
    cube = c4d.BaseObject(c4d.Ocube)
    cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(200)
    cube[c4d.PRIM_CUBE_SUBX] = cube[c4d.PRIM_CUBE_SUBY] = cube[c4d.PRIM_CUBE_SUBZ] = 2
    cube.SetName("BevelBox")
    cube = make_editable(doc, cube)
    cube.SetRelPos(c4d.Vector(-600, 0, 600))
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    doc.SetMode(c4d.Medges)
    # 上面の外周のエッジ（ポイントが2つとも上面の外周にあるもの）
    select_edges(cube, lambda p: p.y > 99 and (abs(p.x) > 99 or abs(p.z) > 99))
    before_pts = cube.GetPointCount()
    uv_before = cube.GetTag(c4d.Tuvw) is not None

    d, how = core.create_or_switch(doc, c4d.Obevel)
    tag = core.get_selection_tag(d)
    check("Bevel: エッジ選択から作成", how == "create" and d.GetType() == c4d.Obevel and tag is not None and tag.GetType() == c4d.Tedgeselection,
          d.GetName())
    check("Bevel: 選択範囲欄にタグの名前（文字列）", d[core.BEVEL_SELECTION] == tag.GetName() and d[c4d.O_BEVEL_MODE_COMPONENT_TYPE] == 1
          and not d[c4d.O_BEVEL_MODE_SELECTION_ANGLE_USE])
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    cache_pts = cube.GetDeformCache().GetPointCount()
    name = d[core.BEVEL_SELECTION]
    d[core.BEVEL_SELECTION] = ""  # 選択範囲なし＝全エッジ
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    all_pts = cube.GetDeformCache().GetPointCount()
    d[core.BEVEL_SELECTION] = name
    check("Bevel: 選んだエッジだけベベル（全エッジより少ない）", before_pts < cache_pts < all_pts, "%d -> %d（全エッジなら %d）" % (before_pts, cache_pts, all_pts))

    core.set_amount_length(doc, d, 12.0)
    check("Bevel: オフセットを長さで指定", abs(d[c4d.O_BEVEL_RADIUS] - 12.0) < 1e-6 and abs(core.amount_length(d) - 12.0) < 1e-6
          and core.amount_slider_range(d)[0] == 0.0)
    try:
        core.flip(doc, d)
        check("Bevel: 向きの変更はエラーで止める", False)
    except core.SDError:
        check("Bevel: 向きの変更はエラーで止める", True)

    # フリーズ: デフォーマーの形と、ベベルツールで焼き込んだ形が同じ
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    expected = sorted_points(cube.GetDeformCache().GetAllPoints())
    expected_polys = cube.GetDeformCache().GetPolygonCount()
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    meshes = core.freeze(doc, core.freeze_targets(doc))
    cube = doc.SearchObject("BevelBox")
    check("Bevel: フリーズ後の形＝デフォーマーの形", sorted_points(cube.GetAllPoints()) == expected and cube.GetPolygonCount() == expected_polys,
          "%d pts / %d polys" % (cube.GetPointCount(), cube.GetPolygonCount()))
    uv = cube.GetTag(c4d.Tuvw)
    check("Bevel: フリーズ後も UV が残り面数に合う", uv_before and uv is not None and uv.GetDataCount() == cube.GetPolygonCount())
    check("Bevel: フリーズでデフォーマーとタグが消える", not core.sd_deformers_under(cube)
          and not any(t.GetType() == c4d.Tedgeselection and t.GetName().startswith(core.SELTAG_BASENAME) for t in cube.GetTags()))
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    cube = doc.SearchObject("BevelBox")
    ds = core.sd_deformers_under(cube)
    check("Bevel: フリーズはアンドゥ1回で戻る", cube.GetPointCount() == before_pts and len(ds) == 1, "%d pts" % cube.GetPointCount())

    # ベベル（エッジ）→ テーパー: エッジの点からポイント選択タグを作り、使われなくなったエッジのタグは消す
    d = ds[0]
    doc.SetActiveObject(d, c4d.SELECTION_NEW)
    t = core.switch_type(doc, d, c4d.Otaper)
    ttag = core.get_selection_tag(t)
    check("Bevel: ベベル→テーパーでポイント選択タグに", t.GetType() == c4d.Otaper and ttag is not None and ttag.GetType() == c4d.Tpointselection
          and ttag in core.weight_layer_targets(t, doc), ttag.GetName() if ttag else "")
    check("Bevel: 使われなくなったエッジのタグは消える", cube.GetTag(c4d.Tedgeselection) is None
          or not cube.GetTag(c4d.Tedgeselection).GetName().startswith(core.SELTAG_BASENAME))
    # テーパーに Shift＋クリックでベベルを重ねる（ポイントモードのベベル）
    b, how = core.create_or_switch(doc, c4d.Obevel, add=True)
    check("Bevel: テーパーにベベルを重ねる", how == "add" and b.GetType() == c4d.Obevel and b[c4d.O_BEVEL_MODE_COMPONENT_TYPE] == 0
          and core.get_selection_tag(b) == ttag)
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    doc.SetActiveObject(cube, c4d.SELECTION_NEW)
    core.freeze(doc, core.freeze_targets(doc))
    cube = doc.SearchObject("BevelBox")
    check("Bevel: テーパー＋ベベルをまとめてフリーズ", not core.sd_deformers_under(cube) and cube.GetPointCount() > before_pts
          and not any(t.GetName().startswith(core.SELTAG_BASENAME) for t in cube.GetTags()), "%d pts" % cube.GetPointCount())
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    cube = doc.SearchObject("BevelBox")
    check("Bevel: まとめたフリーズもアンドゥ1回で戻る", len(core.sd_deformers_under(cube)) == 2 and cube.GetPointCount() == before_pts)


def run_pattern(doc, name, mode, select, create_cmd, switch_cmd, expect_y, expect_bottom):
    print("--- %s ---" % name)
    obj = doc.SearchObject(name)
    doc.SetActiveObject(obj, c4d.SELECTION_NEW)
    doc.SetMode(mode)
    select(obj)
    before = snapshot(doc, name)

    c4d.CallCommand(create_cmd)
    d = core.active_sd_deformer(doc)
    check(name + ": コマンドで作成", d is not None and d.GetUp() == obj, d.GetName() if d else "")
    if d is None:
        return
    m = d.GetMl()
    size = d[c4d.DEFORMOBJECT_SIZE]
    bottom = m.off - m.v2 * (size.y * 0.5)
    check(name + ": 主軸の向き", (m.v2 - expect_y).GetLength() < 1e-3, "Y=%s" % m.v2)
    check(name + ": 箱の底面＝起点", (bottom - expect_bottom).GetLength() < 1e-2, "bottom=%s" % bottom)

    # 限定はフィールドの変数タグレイヤーで行い、制限タグは使わない
    tag = core.get_selection_tag(d)
    targets = core.weight_layer_targets(d, doc)
    check(name + ": フィールドに選択範囲タグ", tag is not None and len(targets) == 1 and targets[0] == tag,
          tag.GetName() if tag else "")
    check(name + ": 制限タグを使っていない", d.GetTag(c4d.Trestriction) is None)
    children = [c.GetName() for c in core.affected_children(obj)]
    if name == "Protrusion":
        check(name + ": 子オブジェクトを検出（注意を出す）", children == ["ChildProbe"], str(children))

    # 保存→再読込しても同じ形に変形する
    def_pts = deformed_points(doc, obj)
    path = os.path.join(tempfile.gettempdir(), "sd_reload_test.c4d")
    c4d.documents.SaveDocument(doc, path, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, c4d.FORMAT_C4DEXPORT)
    loaded = c4d.documents.LoadDocument(path, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS)
    lobj = loaded.SearchObject(name)
    loaded.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    lcache = lobj.GetDeformCache()
    reload_diff = max_diff(lcache.GetAllPoints(), def_pts) if lcache else -1.0
    check(name + ": 保存→再読込でも同じ変形", lcache is not None and reload_diff < 1e-4, "%.6f" % reload_diff)
    c4d.StopAllThreads()
    c4d.documents.KillDocument(loaded)
    os.remove(path)
    info = core.selection_from_tag(obj, tag)
    inside = set(info.point_ids)
    outside_move = max([(def_pts[i] - before["points"][i]).GetLength() for i in range(len(def_pts)) if i not in inside] or [0])
    inside_move = max([(def_pts[i] - before["points"][i]).GetLength() for i in inside] or [0])
    check(name + ": 選択外は動かない", outside_move < 1e-4, "%.5f" % outside_move)
    check(name + ": 選択内は動く", inside_move > 1.0, "%.2f" % inside_move)

    # 種類の切り替え（箱と向きはそのまま）
    c4d.CallCommand(switch_cmd)
    d2 = core.active_sd_deformer(doc)
    check(name + ": 種類の切り替え", d2 is not None and d2.GetType() != d.GetType() and (d2.GetMl().v2 - m.v2).GetLength() < 1e-6, d2.GetName() if d2 else "")
    check(name + ": 切り替え後も箱は選択範囲にぴったり", box_fits(d2, info), str(d2[c4d.DEFORMOBJECT_SIZE]))

    # 再フィット（向きを保ったまま箱が変わらない）
    m2, s2 = d2.GetMl(), d2[c4d.DEFORMOBJECT_SIZE]
    ui.do_reorient(doc, core.refit, None)  # パネルの「フィット」と同じ処理
    d3 = core.active_sd_deformer(doc)
    check(name + ": 再フィット", (d3.GetMl().off - m2.off).GetLength() < 1e-6 and (d3[c4d.DEFORMOBJECT_SIZE] - s2).GetLength() < 1e-6)

    # フリーズ
    expected = deformed_points(doc, obj)
    ui.do_freeze(doc)  # パネルの「フリーズ」と同じ処理
    after = snapshot(doc, name)
    check(name + ": フリーズ後の形＝変形結果", max_diff(after["points"], expected) < 1e-4, "%.6f" % max_diff(after["points"], expected))
    check(name + ": フリーズでデフォーマーが消える", after["children"] == before["children"], str(after["children"]))
    check(name + ": タグ・マテリアル・UVが残る", after["tags"] == before["tags"] and after["polys"] == before["polys"] and after["uv"] == before["uv"])

    # アンドゥ1回で戻る（フリーズ前＝デフォーマーあり）
    c4d.StopAllThreads()  # 描画スレッドを止めてから書き換える（止めないと C4D が落ちることがある）
    doc.DoUndo()
    back = snapshot(doc, name)
    obj_back = doc.SearchObject(name)
    check(name + ": アンドゥ1回で戻る", max_diff(back["points"], before["points"]) < 1e-6 and len(core.sd_deformers_under(obj_back)) == 1,
          "diff=%.6f deformers=%d" % (max_diff(back["points"], before["points"]), len(core.sd_deformers_under(obj_back))))
    # もう一度フリーズして確定状態で残す
    doc.SetActiveObject(obj_back, c4d.SELECTION_NEW)
    ui.do_freeze(doc)  # パネルの「フリーズ」と同じ処理


def main(keep_document=False):
    previous = c4d.documents.GetActiveDocument()
    doc = c4d.documents.BaseDocument()
    doc.SetDocumentName("partdeform_test")
    c4d.documents.InsertBaseDocument(doc)
    c4d.documents.SetActiveDocument(doc)
    doc = c4d.documents.GetActiveDocument()
    try:
        _run_all(doc)
    finally:
        if not keep_document:
            # テスト用ドキュメントを閉じ、元のドキュメントに戻す
            c4d.StopAllThreads()
            c4d.documents.KillDocument(doc)
            if previous is not None and previous.IsAlive():
                c4d.documents.SetActiveDocument(previous)
        c4d.EventAdd()
    n_fail = sum(1 for r in RESULTS if not r[1])
    print("=== %d 件中 %d 件 OK, %d 件 FAIL ===" % (len(RESULTS), len(RESULTS) - n_fail, n_fail))
    return RESULTS


def _run_all(doc):
    build_scene(doc)

    run_pattern(doc, "Protrusion", c4d.Mpolygons, lambda o: select_polys(o, lambda c: c.y > 100.01),
                core.ID_CMD_BEND, core.ID_CMD_TWIST, c4d.Vector(0, 1, 0), c4d.Vector(0, 100, 0))
    run_pattern(doc, "FlatPatch", c4d.Mpolygons, lambda o: select_polys(o, lambda c: c.x > 0 and abs(c.z) < 60),
                core.ID_CMD_TAPER, core.ID_CMD_BEND, c4d.Vector(1, 0, 0), c4d.Vector(0, 0, 0))
    run_pattern(doc, "EdgeTube", c4d.Medges, lambda o: select_edges(o, lambda p: p.y > 40),
                core.ID_CMD_BULGE, core.ID_CMD_SHEAR, c4d.Vector(0, 1, 0), c4d.Vector(0, 50, 0))
    # 起点は未選択側（円柱の側面との付け根 z = -50·cos22.5°）、主軸は付け根→先端の -Z
    run_pattern(doc, "SideBoss", c4d.Mpolygons, lambda o: select_polys(o, lambda c: c.z < -52),
                core.ID_CMD_BEND, core.ID_CMD_TAPER, c4d.Vector(0, 0, -1),
                c4d.Vector(0, 0, -50.0 * math.cos(math.radians(22.5))))
    test_face_shear(doc)
    test_tilted_square_patch(doc)
    test_recapture(doc)
    test_add_stacked(doc)
    test_bevel(doc)
    test_panel_rows(doc)
    test_pick_hit(doc)
    test_legacy_marker_and_language(doc)


if __name__ == "__main__":
    # スクリプトマネージャーから実行したときは、結果を見られるようにテスト用ドキュメントを残す
    main(keep_document=True)
