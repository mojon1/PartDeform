# -*- coding: utf-8 -*-
"""選択範囲デフォーマー（Selection Deformer） for Cinema 4D 2027

ポリゴン・ポイント・エッジを選んだ状態から、標準デフォーマー
（屈曲・シアー・テーパー・ツイスト・膨張）を、選択範囲に合わせた
大きさと向きで1クリックでセットする。フリーズで変形を確定できる。
"""
import os
import sys

import c4d

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from seldeform import ui  # noqa: E402


if __name__ == "__main__":
    # RegisterToolPlugin は呼び出し元モジュールの __res__ を探すので、.pyp に渡されたものを ui にも渡す
    if "__res__" in globals():
        ui.__res__ = globals()["__res__"]
    ui.register()
