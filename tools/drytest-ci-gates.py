#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
干跑 CI 第 10 步「注入应用图标」里的三道硬闸门。

为什么需要这个脚本：
  本地（Windows + PortableGit 退化环境）无法可靠地跑 GitHub Actions 的 shell 片段：
  bash.exe 缺 find/wc/head/dirname，且 `for d in mdpi ...` 的 $d 展开也不可靠。
  但闸门本身只是「文件存在性判断」，语义完全可以用 Python 等价复现 —— 而且
  这里用的是**真·shell 内建 glob**（os.path.glob 与 shell glob 语义一致），
  不依赖任何外部命令，恰好也就是 CI 里改写后的写法。

覆盖：
  A. 闸门 1 —— drawable-xxxhdpi/ic_launcher_foreground.png 必须存在
  B. 闸门 2 —— mipmap-*/ 下不得残留 ic_launcher_foreground.png
  C. 闸门 3 —— 5 档传统图标（ic_launcher.png / ic_launcher_round.png）齐全
  D. 反向用例：故意造出「前景图错位」→ 闸门 2 必须报错
  E. 反向用例：故意删掉一档传统图标 → 闸门 3 必须报错
  F. 一致性：脚本里的闸门判据必须与 build-apk.yml 文本逐条对得上
     （防止「改了一处忘另一处」的假绿）

用法：
  python tools/drytest-ci-gates.py
"""

import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
YML = os.path.join(ROOT, ".github", "workflows", "build-apk.yml")

DPIS = ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  [OK]   " if ok else "  [FAIL] ") + name + (("  -- " + detail) if detail else ""))


# ---------------------------------------------------------------- 闸门实现
# 注意：下面这三段就是 CI 里那三道闸门的等价语义。
#   glob.glob("mipmap-*/x.png")  ==  shell 的 `ls -d mipmap-*/x.png 2>/dev/null`
# 都是纯内建行为，不依赖 find/grep/wc。

def gate1(res):
    """前景图必须在 drawable-<dpi>/（5 档齐全）；返回缺失列表（空 = 通过）"""
    missing = []
    for d in DPIS:
        if not os.path.isfile(os.path.join(res, "drawable-" + d, "ic_launcher_foreground.png")):
            missing.append("drawable-%s/ic_launcher_foreground.png" % d)
    return missing


def gate2(res):
    """mipmap-*/ 下不得残留前景图；返回残留列表（空 = 通过）"""
    left = []
    for d in os.listdir(res) if os.path.isdir(res) else []:
        if not d.startswith("mipmap-"):
            continue
        p = os.path.join(res, d, "ic_launcher_foreground.png")
        if os.path.isfile(p):
            left.append(p)
    return left


def gate3(res):
    """5 档传统图标齐全；返回缺失列表（空 = 通过）"""
    missing = []
    for d in DPIS:
        for f in ("ic_launcher.png", "ic_launcher_round.png"):
            if not os.path.isfile(os.path.join(res, "mipmap-" + d, f)):
                missing.append("mipmap-%s/%s" % (d, f))
    return missing


def run_gates(res):
    return {
        "g1": gate1(res),
        "g2": gate2(res),
        "g3": gate3(res),
        "pass": (gate1(res) == [] and gate2(res) == [] and gate3(res) == []),
    }


    # ---------------------------------------------------------- 环境准备
def make_env(foreground_dir="drawable-xxxhdpi", skip_traditional=None):
    """复刻 make-android-icons.py 的产物布局"""
    res = tempfile.mkdtemp(prefix="clinic_res_")
    # 前景图（5 档）——注意 foreground_dir 用 "-xxxhdpi" 作为「基准档」占位，
    # 实际每档都按 DPIS 展开，与 make-android-icons.py 一致。
    base = foreground_dir.rsplit("-", 1)[0]  # "drawable" 或 "mipmap"
    for d in DPIS:
        fdir = os.path.join(res, base + "-" + d)
        os.makedirs(fdir, exist_ok=True)
        with open(os.path.join(fdir, "ic_launcher_foreground.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nFAKE")
    # 传统图标（5 档 ×2）
    for d in DPIS:
        os.makedirs(os.path.join(res, "mipmap-" + d), exist_ok=True)
        for f in ("ic_launcher.png", "ic_launcher_round.png"):
            if skip_traditional and (d, f) == skip_traditional:
                continue
            with open(os.path.join(res, "mipmap-" + d, f), "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\nFAKE")
    # 自适应 XML
    anydpi = os.path.join(res, "mipmap-anydpi-v26")
    os.makedirs(anydpi, exist_ok=True)
    with open(os.path.join(anydpi, "ic_launcher.xml"), "w", encoding="utf-8") as f:
        f.write("<adaptive-icon>\n"
                "  <background android:drawable=\"@color/ic_launcher_background\"/>\n"
                "  <foreground android:drawable=\"@drawable/ic_launcher_foreground\"/>\n"
                "</adaptive-icon>\n")
    with open(os.path.join(anydpi, "ic_launcher_round.xml"), "w", encoding="utf-8") as f:
        f.write("<adaptive-icon>\n"
                "  <background android:drawable=\"@color/ic_launcher_background\"/>\n"
                "  <foreground android:drawable=\"@drawable/ic_launcher_foreground\"/>\n"
                "</adaptive-icon>\n")
    # color 资源
    v = os.path.join(res, "values")
    os.makedirs(v, exist_ok=True)
    with open(os.path.join(v, "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
        f.write("<resources>\n  <color name=\"ic_launcher_background\">#FFFFFF</color>\n</resources>\n")
    return res


def main():
    print("=" * 68)
    print("CI 第 10 步 图标硬闸门 · 干跑")
    print("=" * 68)

    # ---------------------------------------------------------- A/B/C 正例
    res = make_env()
    try:
        r = run_gates(res)
        print("\n[A/B/C] 正确布局（前景图在 drawable-*、mipmap 干净、5 档齐全）")
        check("闸门1 前景图在 drawable-<dpi>/ 5 档齐全", r["g1"] == [], "缺失=%r" % (r["g1"],))
        check("闸门2 mipmap-*/ 无前景图残留", r["g2"] == [], "残留=%r" % (r["g2"],))
        check("闸门3 传统图标 5 档齐全", r["g3"] == [], "缺失=%r" % (r["g3"],))
        check("三道闸门整体通过", r["pass"])
    finally:
        shutil.rmtree(res, ignore_errors=True)

    # ---------------------------------------------------------- D 反向：错位
    res = make_env(foreground_dir="mipmap-xxxhdpi")  # 故意写错目录
    try:
        r = run_gates(res)
        print("\n[D] 反向用例：前景图错位到 mipmap-*/（真实事故的形态）")
        check("闸门1 应判失败（drawable 下 5 档全缺）", len(r["g1"]) == 5, "缺失=%d" % len(r["g1"]))
        check("闸门2 应检出 5 个残留", len(r["g2"]) == 5, "检出=%d" % len(r["g2"]))
        check("整体应判失败", r["pass"] is False)
    finally:
        shutil.rmtree(res, ignore_errors=True)

    # ---------------------------------------------------------- E 反向：缺档
    res = make_env(skip_traditional=("xxhdpi", "ic_launcher_round.png"))
    try:
        r = run_gates(res)
        print("\n[E] 反向用例：缺一档 ic_launcher_round.png")
        check("闸门3 应报缺失", r["g3"] == ["mipmap-xxhdpi/ic_launcher_round.png"],
              "缺失=%r" % (r["g3"],))
        check("整体应判失败", r["pass"] is False)
    finally:
        shutil.rmtree(res, ignore_errors=True)

    # ---------------------------------------------------------- F 一致性
    print("\n[F] 与 build-apk.yml 的判据一致性（防「改一处忘一处」）")
    with open(YML, "r", encoding="utf-8") as f:
        yml = f.read()

    # 抽出第 10 步那一整段 run 块
    m = re.search(r"注入应用图标（与服务端统一）.*?run: \|\n(.*?)\n\s+- name:", yml, re.S)
    block = m.group(1) if m else ""
    check("能在 YAML 中定位到第 10 步 run 块", bool(block))

    # 先把注释行去掉，避免「注释里提到陷阱写法」被误判成真的用了陷阱写法
    code_lines = [ln for ln in block.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)

    check("闸门1 循环 5 档并断言 drawable-$d/ic_launcher_foreground.png",
          'test -f "android/app/src/main/res/drawable-$d/ic_launcher_foreground.png"' in code)
    check("闸门2 用 [ -f ... ] 内建判断，未用 find|grep -q",
          '[ -f "android/app/src/main/res/mipmap-$d/ic_launcher_foreground.png" ]' in code
          and ("grep -q" not in code))
    check("闸门3 覆盖 5 档 × 2 个文件",
          "for d in mdpi hdpi xhdpi xxhdpi xxxhdpi" in code
          and "ic_launcher.png" in code
          and "ic_launcher_round.png" in code)
    check("三处失败路径都 exit 1", code.count("exit 1") >= 3,
          "exit 1 出现 %d 次" % code.count("exit 1"))
    check("主闸门交给 Python 自检（make-android-icons.py 内部 exit 2）",
          "python3 tools/make-android-icons.py" in code)

    # 反向：全文件（去掉注释后）不得残留 pipefail 陷阱写法
    yml_code = "\n".join(
        ln for ln in yml.splitlines() if not ln.strip().startswith("#")
    )
    bad = [ln.strip() for ln in yml_code.splitlines()
           if "find " in ln and "grep -q" in ln and "|" in ln]
    check("全文件不存在 find ... | grep -q 陷阱写法", not bad, "命中=%r" % (bad,))

    # 关键：闸门1/2/3 的顺序（先 drawable 存在、再 mipmap 干净、再传统齐全）
    i1 = block.find("硬闸门 1")
    i2 = block.find("硬闸门 2")
    i3 = block.find("硬闸门 3")
    check("三道闸门顺序正确", 0 <= i1 < i2 < i3)

    # ---------------------------------------------------------- 汇总
    total = len(results)
    failed = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 68)
    print("合计 %d 项，失败 %d 项" % (total, len(failed)))
    for n in failed:
        print("  FAILED: " + n)
    print("=" * 68)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
