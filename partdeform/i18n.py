# -*- coding: utf-8 -*-
"""表示言語（日本語／英語）の切り替え。

C4D の表示言語が日本語なら日本語、それ以外（英語・ドイツ語など）は英語で表示する。
文字列はコードの中に tr("日本語", "English") の形で並べて書く（文脈が分かり、訳し漏れも見つけやすい）。

環境変数 PARTDEFORM_LANG に ja / en を入れると、C4D の表示言語に関係なくその言語にする。
"""
import os

import c4d

LANGUAGES = ("ja", "en")

_override = None
_detected = None


def _detect():
    env = os.environ.get("PARTDEFORM_LANG", "").strip().lower()
    if env in LANGUAGES:
        return env
    # C4D の表示言語は、インストール済みの言語のうち default_language が True のもの
    i = 0
    while True:
        try:
            lang = c4d.GeGetLanguage(i)
        except Exception:
            break
        if not lang:
            break
        if lang.get("default_language"):
            return "ja" if str(lang.get("extensions", "")).lower().startswith("ja") else "en"
        i += 1
    return "en"


def language():
    """今の表示言語（"ja" か "en"）。"""
    global _detected
    if _override is not None:
        return _override
    if _detected is None:
        _detected = _detect()
    return _detected


def set_language(lang):
    """表示言語を強制する（テスト用。None で自動に戻す）。

    モジュールの読み込み時に作る文字列（ボタンの名前など）は、変えたあとにモジュールを読み直すと反映される。
    """
    global _override
    _override = lang if lang in LANGUAGES else None


def tr(ja, en):
    """今の表示言語の文字列を返す。"""
    return ja if language() == "ja" else en
