# -*- coding: utf-8 -*-
"""配布用の zip を作る（C4D の外で、普通の Python で実行する）。

    python tools/build_release.py

- バージョンは partdeform/__init__.py の __version__ から読む。
- CHANGELOG.md にその版の見出し（## x.y.z）が無ければ止める。
- コミット済みの内容（HEAD）から、改行を LF にそろえて zip にする（作業中の変更は入らない）。
- zip の中は PartDeform/ フォルダ1つ（更新は上書きで済むよう、フォルダ名に番号は付けない）。
  中に VERSION.txt を入れる。テストや開発用のファイルは入れない。
- zip の名前は dist/PartDeform-v<版>-plugin.zip（GitHub が自動で付ける「Source code」の
  PartDeform-<版>.zip と区別するため）。
"""
import io
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = "PartDeform"
INCLUDE = ["PartDeform.pyp", "partdeform", "res", "LICENSE", "README.md", "README_ja.md", "CHANGELOG.md"]
REPO_URL = "https://github.com/mojon1/PartDeform"


def read_version():
    text = open(os.path.join(ROOT, "partdeform", "__init__.py"), encoding="utf-8").read()
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        sys.exit("partdeform/__init__.py に __version__ が見つかりません。")
    return m.group(1)


def git(*args):
    return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=ROOT, check=True,
                          capture_output=True).stdout


def main():
    version = read_version()
    changelog = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    if not re.search(r"^## %s\b" % re.escape(version), changelog, re.M):
        sys.exit("CHANGELOG.md に「## %s」の項目がありません。" % version)
    if git("status", "--porcelain", "--", *INCLUDE).strip():
        print("注意: 配布に入るファイルにコミットしていない変更があります（zip にはコミット済みの内容だけが入ります）。")

    archive = git("archive", "--format=zip", "--prefix=%s/" % FOLDER, "HEAD", *INCLUDE)
    commit = git("rev-parse", "--short", "HEAD").decode().strip()
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "%s-v%s-plugin.zip" % (FOLDER, version))
    with zipfile.ZipFile(io.BytesIO(archive)) as src, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info.filename))
        dst.writestr("%s/VERSION.txt" % FOLDER,
                     "PartDeform %s\n%s\nbuilt from commit %s\n" % (version, REPO_URL, commit))

    with zipfile.ZipFile(out) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        crlf = [n for n in names if b"\r\n" in z.read(n)]
    if crlf:
        sys.exit("改行が CRLF のファイルがあります: %s" % crlf)
    print("作成: %s（%d ファイル、%d バイト）" % (os.path.relpath(out, ROOT), len(names), os.path.getsize(out)))


if __name__ == "__main__":
    main()
