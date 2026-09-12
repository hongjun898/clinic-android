#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线干跑 patch-manifest.py：造一个仿 Capacitor 的 AndroidManifest.xml，
跑补丁后校验关键声明齐全、XML 仍合法。CI 跑之前先本地确认。"""
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ANDROID = 'http://schemas.android.com/apk/res/android'
CAP_MANIFEST = '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/AppTheme">

        <activity
            android:name="cn.clinic.manage.MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
'''

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, 'patch-manifest.py')

fails = []
def ok(name, cond, extra=''):
    print(('  [OK]   ' if cond else '  [FAIL] ') + name + (('  -> ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)

tmp = tempfile.mkdtemp(prefix='mfst_')
target = os.path.join(tmp, 'AndroidManifest.xml')
with open(target, 'w', encoding='utf-8') as f:
    f.write(CAP_MANIFEST)

print('=== 干跑 patch-manifest.py ===')
r = subprocess.run([sys.executable, PATCH, target], capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print('STDERR:', r.stderr)
ok('脚本退出码为 0', r.returncode == 0, r.returncode)

with open(target, encoding='utf-8') as f:
    out = f.read()

print('=== 断言 ===')
ok('已加入 TTS_SERVICE 查询', 'android.intent.action.TTS_SERVICE' in out)
ok('已加入 <queries> 块', '<queries>' in out)
ok('已加入 FOREGROUND_SERVICE 权限', 'android.permission.FOREGROUND_SERVICE' in out)
ok('已加入 INTERNET 权限', 'android.permission.INTERNET' in out)
ok('已放行明文流量', 'android:usesCleartextTraffic="true"' in out)
ok('保留 allowBackup', 'android:allowBackup="true"' in out)
ok('保留 label', 'android:label="@string/app_name"' in out)
ok('保留 MainActivity', 'cn.clinic.manage.MainActivity' in out)

# XML 合法性（去掉 xmlns 前缀问题：ET 能解析带前缀的属性即可）
try:
    ET.fromstring(out)
    ok('XML 仍然合法', True)
except Exception as e:
    ok('XML 仍然合法', False, e)

# 幂等：再跑一次不应重复插入
r2 = subprocess.run([sys.executable, PATCH, target], capture_output=True, text=True)
with open(target, encoding='utf-8') as f:
    out2 = f.read()
ok('重复执行是幂等的（TTS_SERVICE 只 1 次）', out2.count('TTS_SERVICE') == 1, out2.count('TTS_SERVICE'))
ok('重复执行是幂等的（usesCleartextTraffic 只 1 次）',
   out2.count('usesCleartextTraffic') == 1, out2.count('usesCleartextTraffic'))
ok('重复执行是幂等的（INTERNET 只 1 次）',
   out2.count('android.permission.INTERNET') == 1, out2.count('android.permission.INTERNET'))

print()
if fails:
    print('失败 ' + str(len(fails)) + ' 项：' + ', '.join(fails))
    sys.exit(1)
print('全部通过 ✅')
