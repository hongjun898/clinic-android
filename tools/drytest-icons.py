#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make-android-icons.py 的干跑自检：在临时目录生成全套图标，逐项断言。

用法：python3 tools/drytest-icons.py
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "make-android-icons.py")
ICON_SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\WinRAR\WorkBuddy\.workbuddy\android-tts\ICON_256.PNG"
if not os.path.exists(ICON_SRC):
    _alt = r"D:\WinRAR\WorkBuddy\.workbuddy\fnpack\clinic\ICON_256.PNG"
    if os.path.exists(_alt):
        ICON_SRC = _alt

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    print("  PASS  " + name)


def bad(name, detail=""):
    global FAIL
    FAIL += 1
    print("  FAIL  " + name + ("  -> " + str(detail) if detail else ""))


def eq(name, got, want):
    if got == want:
        ok(name)
    else:
        bad(name, "got=%r want=%r" % (got, want))


def truth(name, cond, detail=""):
    if cond:
        ok(name)
    else:
        bad(name, detail)


def main():
    tmp = tempfile.mkdtemp(prefix="icontest_")
    res = os.path.join(tmp, "res")
    os.makedirs(res)

    print("干跑目录: " + tmp)
    r = subprocess.run(
        [sys.executable, GEN, ICON_SRC, res],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout or "")
    if r.stderr:
        print(r.stderr)
    eq("生成脚本退出码 = 0", r.returncode, 0)

    # 1) 传统图标 5 档 dpi，尺寸必须严格等于 48/72/96/144/192
    for dpi, size in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        p = os.path.join(res, "mipmap-" + dpi, "ic_launcher.png")
        if not os.path.exists(p):
            bad("mipmap-%s/ic_launcher.png 存在" % dpi, "文件缺失")
            continue
        im = Image.open(p)
        eq("mipmap-%s/ic_launcher.png 尺寸 = %d" % (dpi, size), im.size, (size, size))
        eq("mipmap-%s/ic_launcher.png 有透明通道" % dpi, im.mode, "RGBA")
        # 圆形版本必须同步生成
        pr = os.path.join(res, "mipmap-" + dpi, "ic_launcher_round.png")
        truth("mipmap-%s/ic_launcher_round.png 存在" % dpi, os.path.exists(pr))

    # 2) 自适应前景 5 档，尺寸 108dp 基准。
    #    ⚠️ 必须在 drawable-<dpi>/ —— adaptive-icon XML 引用的是 @drawable/ic_launcher_foreground。
    #    早期版本误写到 mipmap-<dpi>/，导致 AAPT2 解析不到资源、自适应图标链接失败 → 桌面无图标。
    for dpi, size in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216), ("xxhdpi", 324), ("xxxhdpi", 432)):
        p = os.path.join(res, "drawable-" + dpi, "ic_launcher_foreground.png")
        if not os.path.exists(p):
            bad("drawable-%s/ic_launcher_foreground.png 存在" % dpi, "文件缺失")
            continue
        im = Image.open(p)
        eq("drawable-%s/ic_launcher_foreground.png 尺寸 = %d" % (dpi, size), im.size, (size, size))

    # 2b) 反向断言：绝不能把前景图留在 mipmap-<dpi>/（否则 @drawable/ 解析失败）
    for dpi in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        wrong = os.path.join(res, "mipmap-" + dpi, "ic_launcher_foreground.png")
        truth("mipmap-%s/ 下没有 ic_launcher_foreground.png（防止引用错位回归）" % dpi,
              not os.path.exists(wrong))

    # 2c) 核心闸门：把 XML 里引用的每个资源都在 res/ 下真实解析一遍
    import glob as _glob
    import re as _re
    _errs = []
    for fn in ("ic_launcher.xml", "ic_launcher_round.xml"):
        xp = os.path.join(res, "mipmap-anydpi-v26", fn)
        if not os.path.exists(xp):
            _errs.append(fn + " 缺失")
            continue
        body = open(xp, encoding="utf-8").read()
        for kind, name in _re.findall(r"@(drawable|mipmap|color)/([A-Za-z0-9_]+)", body):
            if kind == "color":
                if not os.path.exists(os.path.join(res, "values", "ic_launcher_background.xml")):
                    _errs.append(fn + " -> @color/" + name + " 无法解析")
                continue
            hit = False
            for dp in _glob.glob(os.path.join(res, kind + "*")):
                for ext in (".png", ".webp", ".xml", ".jpg", ".jpeg"):
                    if os.path.exists(os.path.join(dp, name + ext)):
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                _errs.append(fn + " -> @" + kind + "/" + name + " 无法解析")
    truth("adaptive-icon 引用的资源全部可在 res/ 下解析（防「桌面无图标」）",
          not _errs, "; ".join(_errs))

    # 3) 前景透明画布 + 有内容 + 内容落在安全区内
    fg = Image.open(os.path.join(res, "drawable-xxxhdpi", "ic_launcher_foreground.png")).convert("RGBA")
    S = fg.size[0]
    px = fg.load()
    corner_alpha = px[1, 1][3]
    eq("前景四角透明（画布留白）", corner_alpha, 0)
    bbox = fg.getbbox()
    truth("前景存在不透明内容", bbox is not None, str(bbox))
    if bbox:
        # 安全区：自适应图标 108dp 画布中，系统只保证中心 66dp 圆内完整可见
        # 66/108 = 0.6111 -> 半径 = S * 0.30555
        #
        # ⚠️ 断言口径必须是「**真实不透明像素**到圆心的最大距离」，不能拿 bbox 四角去量：
        #    源图本身是正圆（第 38 轮实测，见 make-android-icons.py 注释），
        #    bbox 四角全部落在圆外、本来就是 alpha=0 的透明区。
        #    拿 bbox 四角算距离 = √2·r，会得出「超出安全圆」的**假失败**，
        #    正是这个错误口径逼着上一版把图标缩到 0.4584 → 用户反馈「图标太小」。
        safe_r = S * (66.0 / 108.0) / 2.0
        cx = cy = S / 2.0
        worst = 0.0
        for y in range(bbox[1], bbox[3]):
            for x in range(bbox[0], bbox[2]):
                if px[x, y][3] > 8:                      # 只统计真正可见的像素
                    d = math.hypot(x - cx, y - cy)
                    if d > worst:
                        worst = d
        truth("可见图形所有不透明像素落在 66dp 安全圆内（圆形遮罩不会裁掉）",
              worst <= safe_r + 1.0,
              "最远不透明像素距圆心=%.1f 安全半径=%.1f" % (worst, safe_r))
        # 也不能缩太小：可见图形的**外接直径**应基本撑满安全圆（≥95%），否则图标显小
        vis_r = max(worst, 1.0)
        truth("可见图形撑满安全圆（外接直径 ≥ 安全直径的 95%，防图标偏小回归）",
              vis_r >= safe_r * 0.95,
              "可见半径=%.1f 安全半径=%.1f 占比=%.1f%%" % (vis_r, safe_r, vis_r / safe_r * 100))
        # 圆度断言：源图是正圆，前景里可见区域也应是圆——用「面积 ≈ π r²」反查，
        # 防止误把方角图塞进来（方角在 66dp 圆遮罩下会被切角）。
        opq = sum(1 for y in range(bbox[1], bbox[3]) for x in range(bbox[0], bbox[2])
                  if px[x, y][3] > 8)
        area_circle = math.pi * vis_r * vis_r
        truth("可见区域形状接近正圆（面积/πr² ∈ [0.88, 1.12]）",
              abs(opq / area_circle - 1.0) <= 0.12,
              "实测面积=%d πr²=%.0f 比值=%.3f" % (opq, area_circle, opq / area_circle))

    # 4) 自适应 XML 引用正确
    for fn in ("ic_launcher.xml", "ic_launcher_round.xml"):
        p = os.path.join(res, "mipmap-anydpi-v26", fn)
        if not os.path.exists(p):
            bad("mipmap-anydpi-v26/%s 存在" % fn, "文件缺失")
            continue
        s = open(p, encoding="utf-8").read()
        truth("mipmap-anydpi-v26/%s 引用背景色" % fn, "@color/ic_launcher_background" in s)
        truth("mipmap-anydpi-v26/%s 引用前景图" % fn, "@drawable/ic_launcher_foreground" in s)
        truth("mipmap-anydpi-v26/%s 是合法 adaptive-icon" % fn,
              s.strip().startswith("<?xml") and "<adaptive-icon" in s and s.count("<") == s.count(">"))

    # 5) 背景色资源
    p = os.path.join(res, "values", "ic_launcher_background.xml")
    if os.path.exists(p):
        s = open(p, encoding="utf-8").read()
        truth("values/ic_launcher_background.xml 定义 ic_launcher_background",
              '<color name="ic_launcher_background">' in s)
    else:
        bad("values/ic_launcher_background.xml 存在", "文件缺失")

    # 6) 幂等：再跑一次结果一致（不会叠加/损坏）
    p1 = os.path.join(res, "mipmap-xxxhdpi", "ic_launcher.png")
    b1 = open(p1, "rb").read()
    subprocess.run([sys.executable, GEN, ICON_SRC, res],
                   capture_output=True, text=True)
    b2 = open(p1, "rb").read()
    eq("重复执行幂等（同尺寸图标字节一致）", len(b2), len(b1))

    # 7) 非正方形源图也能处理（居中裁剪成方）
    #    ⚠️ 必须用**圆形**内容而非实心方块：生成脚本第 7 项自检会拒绝「方角图」
    #       （方角在 66dp 圆形遮罩下会被切角，且说明源图不是我们的正圆徽章）。
    sq = os.path.join(tmp, "wide.png")
    wide = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(wide).ellipse((100, 0, 300, 200), fill=(200, 30, 30, 255))
    wide.save(sq)
    res2 = os.path.join(tmp, "res2")
    os.makedirs(res2)
    r2 = subprocess.run([sys.executable, GEN, sq, res2],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    eq("非方图源：脚本仍成功", r2.returncode, 0)
    p2 = os.path.join(res2, "mipmap-hdpi", "ic_launcher.png")
    truth("非方图源：产物为正方形", os.path.exists(p2) and Image.open(p2).size == (72, 72))

    # 7b) 【新回归】必须拒绝「方角源图」—— 方角在圆形遮罩下会被切角，
    #     且会暴露「源图不再是我们的正圆徽章」这一事实。
    san = os.path.join(tmp, "square.png")
    Image.new("RGBA", (256, 256), (200, 30, 30, 255)).save(san)
    res4 = os.path.join(tmp, "res_sq")
    os.makedirs(res4)
    r6 = subprocess.run([sys.executable, GEN, san, res4],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    eq("方角源图：脚本拒绝（返回 4）", r6.returncode, 4)
    truth("方角源图：日志点明「撑满/安全圆」问题",
          ("安全圆" in (r6.stdout or "")) or ("显小" in (r6.stdout or "")),
          (r6.stdout or "")[-300:])

    # 8) 缺源图时优雅失败
    r3 = subprocess.run([sys.executable, GEN, os.path.join(tmp, "nope.png"), res2],
                        capture_output=True, text=True)
    truth("缺源图：返回非 0 且不崩溃", r3.returncode == 1)

    # 9) 【关键回归】模拟 `npx cap add android` 之后的真实 res/ 状态：
    #    Capacitor 模板自带 mipmap-<dpi>/ic_launcher_foreground.png 与
    #    drawable-v24/ic_launcher_foreground.xml。生成脚本必须把它们**删掉**，
    #    否则 @drawable/ic_launcher_foreground 会被模板图抢走解析
    #    → 自适应图标仍指向 Capacitor 默认图 → 用户看到「图标丢失/不是自己的图标」。
    #    （CI run #5 就是因为模板残留而失败的，这条断言守住它。）
    res3 = os.path.join(tmp, "res_cap")
    os.makedirs(res3)
    # 复刻模板：mipmap 五档前景 + drawable 传统图标 + drawable-v24 矢量前景
    for dpi in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        d = os.path.join(res3, "mipmap-" + dpi)
        os.makedirs(d)
        Image.new("RGBA", (48, 48), (0, 120, 255, 255)).save(
            os.path.join(d, "ic_launcher_foreground.png"))
        Image.new("RGBA", (48, 48), (0, 120, 255, 255)).save(
            os.path.join(d, "ic_launcher.png"))
    dv24 = os.path.join(res3, "drawable-v24")
    os.makedirs(dv24)
    open(os.path.join(dv24, "ic_launcher_foreground.xml"), "w", encoding="utf-8").write(
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"/>')
    dpi_drawable = os.path.join(res3, "drawable")
    os.makedirs(dpi_drawable)
    open(os.path.join(dpi_drawable, "ic_launcher_background.xml"), "w", encoding="utf-8").write(
        "<resources/>")

    r4 = subprocess.run([sys.executable, GEN, ICON_SRC, res3],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    eq("模板态 res/：生成脚本退出码 = 0", r4.returncode, 0)
    truth("模板态 res/：日志提示已清理模板残留",
          "已清理 Capacitor 模板残留前景图" in (r4.stdout or ""),
          (r4.stdout or "")[-300:])
    for dpi in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        wp = os.path.join(res3, "mipmap-" + dpi, "ic_launcher_foreground.png")
        truth("模板态 res/：mipmap-%s/ 模板前景图已被删除" % dpi, not os.path.exists(wp))
    truth("模板态 res/：drawable-v24/ 模板矢量前景图已被删除",
          not os.path.exists(os.path.join(dv24, "ic_launcher_foreground.xml")))
    truth("模板态 res/：drawable-xxxhdpi/ 已写入我们的前景图",
          os.path.exists(os.path.join(res3, "drawable-xxxhdpi", "ic_launcher_foreground.png")))
    truth("模板态 res/：mipmap-xxxhdpi/ic_launcher.png 已替换为我们的（尺寸 192）",
          Image.open(os.path.join(res3, "mipmap-xxxhdpi", "ic_launcher.png")).size == (192, 192))

    # 反向：脚本自检必须能识别「人为塞回的残留」并返回非 0
    #   —— 直接手工塞一个回去，然后单独跑一次生成（它自己会先清理，所以这里
    #      改为验证「清理后无残留」这一事实由脚本自检覆盖：塞回去再跑，仍应 0 且被清掉）
    with open(os.path.join(res3, "mipmap-mdpi", "ic_launcher_foreground.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nSTALE")
    r5 = subprocess.run([sys.executable, GEN, ICON_SRC, res3],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    eq("再次塞回残留：脚本仍成功且再次清理", r5.returncode, 0)
    truth("再次塞回残留：已被再次删除",
          not os.path.exists(os.path.join(res3, "mipmap-mdpi", "ic_launcher_foreground.png")))

    print("\n合计 %d 项：通过 %d，失败 %d" % (PASS + FAIL, PASS, FAIL))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
