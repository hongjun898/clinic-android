#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch-version.py —— 把应用版本号写进 Capacitor 生成的 Android 工程。

背景（为什么必须有这一步）：
  Capacitor 每次 `npx cap add android` 都会重新生成 android/ 目录，
  模板里的 app/build.gradle 硬编码：
      versionCode 1
      versionName "1.0"
  package.json 的 version **不会**影响 Android 的升级判定。
  只要 versionCode 恒为 1，手机就无法「覆盖安装升级」——
  Android 要求新包的 versionCode **严格大于**已安装包的 versionCode，
  否则安装器直接报「应用未安装 / 已存在更高版本」。

用法：
  python3 tools/patch-version.py <app/build.gradle 路径> <versionName> [versionCode]

  versionCode 省略时按 versionName 自动推算：major*10000 + minor*100 + patch
  例：2.22.0 → 20200；2.22.4 → 20204。

设计要点：
  · versionCode 是**整数属性**，不在 APK 的字符串池里，用 grep 查不到；
    校验必须用 aapt2 dump badging 读 versionCode。
  · 只改第一次出现的 versionCode / versionName（位于 defaultConfig 块内）；
    后续 buildTypes / productFlavors 里若也有同名属性，不应误改。
  · 改写前做存在性断言，找不到就 exit 2 —— 防止 Capacitor 模板结构变化后
    脚本静默「成功但没改」，那种包在手机上依然装不上。
"""
import re
import sys
import os


def fail(msg, code=2):
    sys.stderr.write("错误：" + msg + "\n")
    sys.exit(code)


def parse_code(name):
    """2.22.0 → 20200；容忍 v 前缀与非数字后缀。"""
    m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(name).strip())
    if not m:
        return None
    major = int(m.group(1) or 0)
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    if not (0 <= minor <= 99 and 0 <= patch <= 99):
        fail("版本号各段需 <= 99，当前 %s" % name)
    return major * 10000 + minor * 100 + patch


def main():
    if len(sys.argv) < 3:
        fail("用法：patch-version.py <build.gradle> <versionName> [versionCode]")

    path = sys.argv[1]
    vname = sys.argv[2].lstrip("v")
    vcode = int(sys.argv[3]) if len(sys.argv) > 3 else parse_code(vname)
    if vcode is None:
        fail("无法从 %r 推算 versionCode，请显式传入" % vname)
    if vcode <= 0:
        fail("versionCode 必须为正整数，当前 %s" % vcode)

    if not os.path.isfile(path):
        fail("找不到 build.gradle：%s" % path)

    src = open(path, "r", encoding="utf-8").read()

    # ---- versionName：只改第一个（defaultConfig 内） ----
    if not re.search(r'versionName\s+"[^"]*"', src):
        fail("模板里找不到 versionName，Capacitor 结构可能已变，请人工核对")
    new, n1 = re.subn(r'versionName\s+"[^"]*"',
                      'versionName "%s"' % vname, src, count=1)

    # ---- versionCode：只改第一个 ----
    if not re.search(r'versionCode\s+\d+', new):
        fail("模板里找不到 versionCode，Capacitor 结构可能已变，请人工核对")
    new, n2 = re.subn(r'versionCode\s+\d+',
                      'versionCode %d' % vcode, new, count=1)

    if n1 != 1 or n2 != 1:
        fail("替换次数异常：versionName=%d versionCode=%d" % (n1, n2))

    open(path, "w", encoding="utf-8").write(new)

    # 回读断言：确认真的写进去了（防止编码/写盘问题）
    back = open(path, "r", encoding="utf-8").read()
    if ('versionName "%s"' % vname) not in back:
        fail("回读校验失败：versionName 未写入")
    if ("versionCode %d" % vcode) not in back:
        fail("回读校验失败：versionCode 未写入")

    print("已写入 %s：versionName=%s versionCode=%d" % (path, vname, vcode))
    for line in back.splitlines():
        if "versionCode" in line or "versionName" in line:
            print("   " + line.strip())


if __name__ == "__main__":
    main()
