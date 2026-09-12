#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI 阶段给 Capacitor 生成的 Android 工程注入「与服务端统一」的应用图标。

为什么需要这个脚本？
  · `npx cap add android` 会用 Capacitor 的**默认模板图标**（蓝底 Capacitor 标志）覆盖
    android/app/src/main/res/mipmap-*/ic_launcher.png；
  · 而 `capacitor.config.json` 里**没有任何图标字段**（Capacitor 只认 appId/appName/webDir），
    官方要求把图标放在 `android/app/src/main/res/`，所以必须在 `cap add android` 之后注入；
  · 网页侧（favicon / 侧边栏品牌位）与 fnOS 服务端用的是同一张 256×256 PNG，
    这里把它派生成 Android 全套 mipmap，做到「三端同图」。

产物：
  · mipmap-mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi/ic_launcher.png     —— 传统方形图标（向下兼容）
  · mipmap-mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi/ic_launcher_round.png
  · mipmap-anydpi-v26/ic_launcher.xml                          —— 自适应图标描述
  · mipmap-anydpi-v26/ic_launcher_round.xml
  · drawable-mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi/ic_launcher_foreground.png
                                                              —— 自适应前景（图标本体，留安全边距）
  · values/ic_launcher_background.xml                          —— 自适应背景色

⚠️ 前景图必须落在 **drawable-<dpi>/**（而不是 mipmap-<dpi>）：
   adaptive-icon XML 里写的是 `android:drawable="@drawable/ic_launcher_foreground"`，
   若把 PNG 放进 mipmap-*/，AAPT2 就找不到 drawable/ic_launcher_foreground，
   自适应图标链接失败 → 启动器读不到图标 → 桌面**没有图标**（本脚本曾踩此坑）。

用法：
  python3 tools/make-android-icons.py <图标源png> <android/app/src/main/res 目录>
"""

import os
import re
import sys
import glob

from PIL import Image

# 各 dpi 的传统图标边长（48dp 基准）
LEGACY_SIZES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

# 自适应图标画布 108dp，系统只保证中心 66dp 圆内完整可见（66/108 = 0.6111）。
#
# ⚠️ 缩放系数不是拍脑袋定的，必须按**源图实体的外接半径**反算：
#   源图 ICON_256.PNG 的徽章是近乎满幅的圆角方块（bbox 17..239），
#   四角离画布中心 156.98px，而源图半宽只有 128px —— 即外接半径是半宽的 1.227 倍。
#   若按「占画布 61%」直接缩放，四角会落在 66dp 安全圆之外，被启动器裁掉。
#   正确做法：先算安全半径能容纳的源图占比，再乘一个留白系数（0.92）留点余量。
_SAFE_FRACTION = 66.0 / 108.0          # 0.6111，系统保证可见的直径占比
_WORST_CORNER_RATIO = 156.98 / 128.0   # 1.2264，源图最远角距 ÷ 源图半宽
FOREGROUND_SCALE = _SAFE_FRACTION / _WORST_CORNER_RATIO * 0.92  # ≈ 0.4584

ADAPTIVE_SIZES = {
    "mdpi": 108,
    "hdpi": 162,
    "xhdpi": 216,
    "xxhdpi": 324,
    "xxxhdpi": 432,
}

# 背景色：取自源图「徽章环带内的底色」的众数（该图是圆形徽章，中心是图形本身不是底色）。
# 用纯色而非纯白，可让自适应图标在浅色/深色壁纸下都有对比。
BG_HEX = "#0A2B1B"

ADAPTIVE_ANYDPI_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""

ADAPTIVE_ROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""

BG_COLOR_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">%s</color>
</resources>
""" % BG_HEX


def ensure(d):
    if not os.path.isdir(d):
        os.makedirs(d)


def purge_stale_foreground(res_dir):
    """
    删除 Capacitor 模板自带的、会造成资源歧义的前景图。

    `npx cap add android` 生成的 res/ 里**本来就有**这两样东西：
      · mipmap-<dpi>/ic_launcher_foreground.png   —— 模板默认的自适应前景
      · drawable-v24/ic_launcher_foreground.xml   —— 模板默认的矢量前景

    adaptive-icon XML 里写的是 `@drawable/ic_launcher_foreground`。Android 的资源
    解析会在**所有同名 drawable/ 与 mipmap/ 候选**里按 dpi 择优匹配 —— 模板留下的
    mipmap-<dpi>/ic_launcher_foreground.png 会参与竞争，把我们要用的
    drawable-<dpi>/ic_launcher_foreground.png 挤掉，结果自适应图标链接到模板图，
    启动器仍显示 Capacitor 默认图标（即用户看到的「图标不是我们的 / 图标丢失」）。

    所以必须先把模板残留清干净，再写自己的。返回被删掉的路径列表（便于日志核对）。
    """
    removed = []
    for pat in ("mipmap-*", "drawable-v24", "drawable", "drawable-night-*"):
        for d in glob.glob(os.path.join(res_dir, pat)):
            if not os.path.isdir(d):
                continue
            for ext in (".png", ".webp", ".xml", ".jpg", ".jpeg"):
                p = os.path.join(d, "ic_launcher_foreground" + ext)
                if os.path.isfile(p):
                    os.remove(p)
                    removed.append(p)
    return removed


def center_crop_square(im):
    """把任意长宽比的图裁成正方形（居中），避免非方图被拉伸变形。"""
    w, h = im.size
    if w == h:
        return im
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def make_foreground(src_sq, size):
    """生成自适应前景：透明画布 + 居中等比缩放的图标本体。"""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = max(1, int(round(size * FOREGROUND_SCALE)))
    logo = src_sq.resize((inner, inner), Image.LANCZOS)
    off = (size - inner) // 2
    canvas.paste(logo, (off, off), logo)
    return canvas


def make_legacy(src_sq, size):
    """传统方形图标：图标本体已自带圆角与透明边，直接整体缩放即可。"""
    return src_sq.resize((size, size), Image.LANCZOS)


def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else "ICON_256.PNG"
    res_dir = sys.argv[2] if len(sys.argv) > 2 else "android/app/src/main/res"

    if not os.path.exists(src_path):
        print("找不到图标源文件: " + src_path)
        return 1

    if not os.path.isdir(res_dir):
        print("找不到 res 目录: " + res_dir)
        return 1

    src = Image.open(src_path).convert("RGBA")
    print("图标源: %s  尺寸 %s" % (src_path, src.size))
    src_sq = center_crop_square(src)

    # 0) 先清掉 Capacitor 模板残留的前景图 —— 否则 @drawable/ 会被 mipmap-*/ 抢走，
    #    自适应图标仍指向模板默认图（用户表现为「图标丢失 / 不是我们的图标」）。
    stale = purge_stale_foreground(res_dir)
    if stale:
        print("--- 已清理 Capacitor 模板残留前景图 %d 个 ---" % len(stale))
        for p in stale:
            print("  rm %s" % p)
    else:
        print("--- 无模板残留前景图需要清理 ---")

    written = []

    # 1) 传统 mipmap
    for dpi, size in LEGACY_SIZES.items():
        d = os.path.join(res_dir, "mipmap-" + dpi)
        ensure(d)
        p = os.path.join(d, "ic_launcher.png")
        make_legacy(src_sq, size).save(p, optimize=True)
        written.append(p)
        # 圆形图标（部分启动器/联系人类场景会取这张）
        p2 = os.path.join(d, "ic_launcher_round.png")
        make_legacy(src_sq, size).save(p2, optimize=True)
        written.append(p2)

    # 2) 自适应图标前景：必须写到 drawable-<dpi>/，与 XML 的 @drawable/ 引用对齐。
    #    ⚠️ 不要写进 mipmap-<dpi>/ —— 那样 AAPT2 解析 @drawable/ic_launcher_foreground 会失败，
    #    自适应图标链接不通过 → 桌面无图标。
    for dpi, size in ADAPTIVE_SIZES.items():
        d = os.path.join(res_dir, "drawable-" + dpi)
        ensure(d)
        p = os.path.join(d, "ic_launcher_foreground.png")
        make_foreground(src_sq, size).save(p, optimize=True)
        written.append(p)

    # 3) 自适应图标描述
    anydpi = os.path.join(res_dir, "mipmap-anydpi-v26")
    ensure(anydpi)
    with open(os.path.join(anydpi, "ic_launcher.xml"), "w", encoding="utf-8") as f:
        f.write(ADAPTIVE_ANYDPI_XML)
    with open(os.path.join(anydpi, "ic_launcher_round.xml"), "w", encoding="utf-8") as f:
        f.write(ADAPTIVE_ROUND_XML)
    written.append(os.path.join(anydpi, "ic_launcher.xml"))
    written.append(os.path.join(anydpi, "ic_launcher_round.xml"))

    # 4) 背景色资源
    values = os.path.join(res_dir, "values")
    ensure(values)
    with open(os.path.join(values, "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
        f.write(BG_COLOR_XML)
    written.append(os.path.join(values, "ic_launcher_background.xml"))

    print("--- 已写入 %d 个文件 ---" % len(written))
    for p in written:
        print("  %s  %d B" % (p, os.path.getsize(p)))

    # 5) 自检：把 adaptive-icon XML 里引用的每个资源都在 res/ 下解析一遍，
    #    任何一个解析不到就直接失败退出（否则 CI 会静默出「无图标」的包）。
    errs = []
    for xml_name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        xp = os.path.join(anydpi, xml_name)
        if not os.path.isfile(xp):
            errs.append("缺少 " + xml_name)
            continue
        with open(xp, encoding="utf-8") as f:
            body = f.read()
        for kind, name in re.findall(r"@(drawable|mipmap|color)/([A-Za-z0-9_]+)", body):
            if kind == "color":
                if not os.path.isfile(os.path.join(values, "ic_launcher_background.xml")):
                    errs.append(xml_name + " 引用的 @color/" + name + " 无对应 values 资源")
                continue
            found = False
            for dp in glob.glob(os.path.join(res_dir, kind + "*")):
                for ext in (".png", ".webp", ".xml", ".jpg", ".jpeg"):
                    if os.path.isfile(os.path.join(dp, name + ext)):
                        found = True
                        break
                if found:
                    break
            if not found:
                errs.append(xml_name + " 引用的 @" + kind + "/" + name + " 在 res/ 下找不到")
    if errs:
        print("!!! 资源引用自检失败：")
        for e in errs:
            print("    - " + e)
        return 2

    # 6) 自检：确认没有「同名前景图」散落在 drawable/ 或 mipmap-*/ 里。
    #    只要 mipmap-<dpi>/ 或 drawable-v24/ 下还留着 ic_launcher_foreground，
    #    AAPT2 就可能匹配到它 → 自适应图标指向模板图 → 桌面无自定义图标。
    #    这是真实事故（run #5）的根因，必须有闸门守住。
    leftovers = []
    for pat in ("mipmap-*", "drawable-v24", "drawable-night-*", "drawable"):
        for d in glob.glob(os.path.join(res_dir, pat)):
            if not os.path.isdir(d):
                continue
            for ext in (".png", ".webp", ".xml", ".jpg", ".jpeg"):
                p = os.path.join(d, "ic_launcher_foreground" + ext)
                if os.path.isfile(p):
                    leftovers.append(p)
    if leftovers:
        print("!!! 自检失败：以下位置残留 ic_launcher_foreground，会与 @drawable/ 抢解析：")
        for p in leftovers:
            print("    - " + p)
        return 3
    # 前景图必须只存在于 drawable-<dpi>/
    fg_dirs = sorted(os.path.dirname(p) for p in
                     glob.glob(os.path.join(res_dir, "drawable-*", "ic_launcher_foreground.png")))
    if len(fg_dirs) != len(ADAPTIVE_SIZES):
        print("!!! 自检失败：drawable-<dpi>/ 前景图档数 %d != %d"
              % (len(fg_dirs), len(ADAPTIVE_SIZES)))
        print("    " + ", ".join(fg_dirs))
        return 3

    print("资源引用自检通过：@color/@drawable/@mipmap 全部可解析")
    print("前景图唯一性自检通过：仅存在于 drawable-<dpi>/（%d 档）" % len(fg_dirs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
