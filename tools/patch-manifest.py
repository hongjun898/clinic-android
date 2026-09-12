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
    return 0


if __name__ == "__main__":
    sys.exit(main())
