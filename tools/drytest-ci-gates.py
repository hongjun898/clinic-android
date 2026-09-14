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

    # 第 38 轮新增：Python 自检里的「前景几何」闸门（图标必须撑满 66dp 安全圆，exit 4）。
    # 这条闸门防的是「图标又变小」的回归 —— 用户实测反馈过「图标太小」，
    # 若把 FOREGROUND_SCALE 改小或忘了裁源图留白，必须让 CI 直接变红。
    gen = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools", "make-android-icons.py")
    gen_src = open(gen, encoding="utf-8").read()
    check("生成脚本含前景几何自检（撑满安全圆）",
          "前景几何自检" in gen_src and "safe_r" in gen_src)
    check("生成脚本几何自检失败返回 4",
          "return 4" in gen_src)
    check("缩放系数不再含已证伪的角距修正 _WORST_CORNER_RATIO",
          "_WORST_CORNER_RATIO" not in gen_src.replace("_WORST_CORNER_RATIO =", "") or
          "1.2264" not in gen_src)
    check("生成脚本会裁掉源图透明留白（trim_alpha_padding）",
          "trim_alpha_padding" in gen_src and "src_content" in gen_src)

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

    # ----------------------------------------------------------
    # [G] 版本号闸门（第 40 轮新增）
    # ----------------------------------------------------------
    # 背景：Capacitor 模板把 build.gradle 的 versionCode 硬编码为 1，
    # 而 Android 只允许 versionCode 严格更大的包覆盖安装。
    # 少了这一步，用户手机上「装不上新版」。versionCode 是整数属性、
    # 不在字符串池里，grep/unzip 查不到，必须用 aapt2 dump badging 读。
    print("\n" + "=" * 68)
    print("[G] 版本号闸门（versionCode 必须递增，否则手机无法覆盖安装）")
    print("=" * 68)

    # G1：workflow 顶层必须定义 APP_VERSION（唯一改动处）
    m_env = re.search(r"^env:\s*\n((?:[ \t]+.*\n)+)", yml, re.M)
    env_block = m_env.group(1) if m_env else ""
    check("workflow 顶层定义 env.APP_VERSION", "APP_VERSION:" in env_block,
          env_block.strip().replace("\n", " | "))

    # G2：必须有「写入应用版本号」步骤，且在 cap add android 之后
    i_add = yml.find("npx cap add android")
    i_ver = yml.find("patch-version.py")
    check("存在写入版本号的步骤", i_ver > 0)
    check("版本号写入在 cap add android 之后（模板刚生成就改）",
          i_add > 0 and i_ver > i_add, "add=%d ver=%d" % (i_add, i_ver))

    # G3：版本步骤必须真的调用 patch-version.py 并传入 APP_VERSION
    m_v = re.search(r"写入应用版本号.*?run: \|\n(.*?)\n\s+- name:", yml, re.S)
    vblock = m_v.group(1) if m_v else ""
    check("版本步骤调用 tools/patch-version.py",
          "python3 tools/patch-version.py" in vblock)
    check("版本步骤传入 $APP_VERSION", "$APP_VERSION" in vblock)
    check("版本步骤写入 android/app/build.gradle",
          "android/app/build.gradle" in vblock)

    # G4：产物校验里必须有 versionCode 硬断言（且真的会 exit 1）
    m_c = re.search(r"校验产物.*?run: \|\n(.*?)\n\s+- name:", yml, re.S)
    cblock = m_c.group(1) if m_c else ""
    ccode = "\n".join(ln for ln in cblock.splitlines()
                      if not ln.strip().startswith("#"))
    check("产物校验读 versionCode（aapt2 dump badging）",
          "versionCode" in ccode and "badging.txt" in ccode)
    check("产物校验断言 versionCode == 期望值",
          'if [ "$BC" != "$EXPECT_CODE" ]' in ccode and "exit 1" in ccode)
    check("产物校验断言 versionCode > 1（防模板默认 1 蒙混过关）",
          '[ "$BC" -le 1 ]' in ccode)
    check("产物校验断言 versionName == APP_VERSION",
          'versionName=\'$APP_VERSION\'' in ccode)
    check("期望 versionCode 由 APP_VERSION 推算",
          "EXPECT_CODE=$(" in ccode and "10000" in ccode)

    # G5：patch-version.py 本身必须存在且带自检（结构与回读断言）
    pv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "patch-version.py")
    check("tools/patch-version.py 存在", os.path.isfile(pv))
    if os.path.isfile(pv):
        pv_src = open(pv, encoding="utf-8").read()
        check("patch-version.py 断言模板里有 versionName（结构变了要报错）",
              "找不到 versionName" in pv_src)
        check("patch-version.py 断言模板里有 versionCode",
              "找不到 versionCode" in pv_src)
        check("patch-version.py 写盘后回读校验",
              "回读校验失败" in pv_src)
        check("patch-version.py 只改第一处（count=1，不误伤 buildTypes）",
              pv_src.count("count=1") >= 2)
        check("patch-version.py 失败返回码为 2",
              "sys.exit(code)" in pv_src or "exit(2)" in pv_src)

    # G6：反向用例 —— 用真实模板跑一遍，确认真的能改、且幂等
    import tempfile as _tf
    import subprocess as _sp
    if os.path.isfile(pv):
        tpl = ('android {\n  defaultConfig {\n    versionCode 1\n'
               '    versionName "1.0"\n  }\n}\n')
        d = _tf.mkdtemp(prefix="vergate_")
        gp = os.path.join(d, "build.gradle")
        open(gp, "w", encoding="utf-8").write(tpl)
        r = _sp.run([sys.executable, pv, gp, "2.22.0"],
                    capture_output=True, text=True, encoding="utf-8")
        check("反向：真实模板能被改写（rc=0）", r.returncode == 0,
              (r.stderr or "").strip()[:120])
        out = open(gp, encoding="utf-8").read()
        check("反向：versionCode 变为 22200", "versionCode 22200" in out)
        check("反向：versionName 变为 2.22.0", 'versionName "2.22.0"' in out)
        # 幂等：再跑一次结果不变
        _sp.run([sys.executable, pv, gp, "2.22.0"],
                capture_output=True, text=True, encoding="utf-8")
        out2 = open(gp, encoding="utf-8").read()
        check("反向：重复执行幂等", out2 == out)
        # 结构异常要报错（不能静默成功）
        bad = os.path.join(d, "bad.gradle")
        open(bad, "w", encoding="utf-8").write("android { }")
        rb = _sp.run([sys.executable, pv, bad, "2.22.0"],
                     capture_output=True, text=True, encoding="utf-8")
        check("反向：模板缺 versionName 时报错退出（不静默成功）",
              rb.returncode == 2)
        # 版本号自动推算
        rc2 = _sp.run([sys.executable, "-c",
                       "import sys; sys.path.insert(0, r'%s'); "
                       "import importlib.util as u; "
                       "s=u.spec_from_file_location('pv', r'%s'); "
                       "m=u.module_from_spec(s); s.loader.exec_module(m); "
                       "print(m.parse_code('2.22.4'), m.parse_code('3.0.0'))"
                       % (os.path.dirname(pv), pv)],
                      capture_output=True, text=True, encoding="utf-8")
        check("反向：版本→versionCode 换算正确（2.22.4→22204, 3.0.0→30000, 2.22.0→22200）",
              rc2.stdout.strip() == "22204 30000", rc2.stdout.strip())

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
