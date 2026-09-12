#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI 阶段给 Capacitor 生成的 AndroidManifest.xml 打补丁。

为什么不直接写在 workflow 的 run: | 块里？
  YAML 块标量要求内容有缩进，但 Python 又要求顶层代码顶格 —— 两个要求互相冲突：
    · 内容顶格     → YAML 认为它是新的顶层键，报 "could not find expected ':'"
    · 内容带缩进   → Python 报 IndentationError
  所以抽成独立文件，是最稳的做法。

用法：python3 tools/patch-manifest.py <AndroidManifest.xml 路径>
"""

import sys
import os


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else "android/app/src/main/AndroidManifest.xml"
    if not os.path.exists(p):
        print("找不到文件: " + p)
        return 1

    with open(p, encoding="utf-8") as f:
        s = f.read()

    changed = False

    # 1) Android 11+ 要能「看见」系统 TTS 引擎，必须声明 queries；
    #    否则 TextToSpeech 找不到引擎，表现为「引擎不初始化、没声音」。
    if "android.intent.action.TTS_SERVICE" not in s:
        queries = (
            "    <queries>\n"
            "        <intent>\n"
            '            <action android:name="android.intent.action.TTS_SERVICE" />\n'
            "        </intent>\n"
            "    </queries>\n\n"
        )
        s = s.replace("<application", queries + "<application", 1)
        print("已加入 <queries> TTS_SERVICE")
        changed = True
    else:
        print("<queries> TTS_SERVICE 已存在，跳过")

    # 2) 前台服务权限（部分引擎在后台合成时需要）
    if "android.permission.FOREGROUND_SERVICE" not in s:
        anchor = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        s = s.replace(
            anchor,
            anchor + '\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
            1)
        print("已加入 FOREGROUND_SERVICE 权限")
        changed = True

    # 3) 放行明文 HTTP 流量。
    #    Android 9(API 28) 起默认禁止 App 访问 http:// —— 而本系统的服务端跑在
    #    飞牛 NAS 上通常只有 http（局域网 IP:7989，或未配 HTTPS 的穿透域名）。
    #    不加这一条，App 里所有同步/备份接口都会以 "Cleartext HTTP traffic not permitted"
    #    静默失败，表现为「同步永远连不上」，极难排查。
    if "android:usesCleartextTraffic" not in s:
        anchor = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        s = s.replace(
            anchor,
            anchor + '\n    <uses-permission android:name="android.permission.INTERNET" />',
            1)
        # 在 <application 标签内加属性（Capacitor 生成的 <application 通常带若干属性，
        # 直接在其后追加即可）
        if "<application" in s:
            idx = s.index("<application")
            end = s.index(">", idx)
            s = s[:end] + ' android:usesCleartextTraffic="true"' + s[end:]
        print("已放行明文 HTTP 流量（usesCleartextTraffic）+ INTERNET 权限")
        changed = True

    if changed:
        with open(p, "w", encoding="utf-8") as f:
            f.write(s)
        print("AndroidManifest 已更新")
    else:
        print("无需改动")

    # 打印结果确认
    print("--- 关键声明计数 ---")
    print("TTS_SERVICE          : " + str(s.count("TTS_SERVICE")))
    print("FOREGROUND_SERVICE   : " + str(s.count("FOREGROUND_SERVICE")))
    print("INTERNET             : " + str(s.count("android.permission.INTERNET")))
    print("usesCleartextTraffic : " + str(s.count("usesCleartextTraffic")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
