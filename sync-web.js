#!/usr/bin/env node
/**
 * 把网页正式版同步到 Capacitor 工程的 www/index.html
 *
 * 用法：node sync-web.js
 * 前置：先在 .workbuddy 下跑 `VER=v2.x node build_release.js` 生成正式版
 *
 * 为什么需要这一步：网页的真源是 D:/WinRAR/诊所管理系统-预览.html（改这里），
 * 出正式版后由本脚本复制到 App 工程的 www/，避免两边手工拷贝漏掉。
 */
const fs = require('fs');
const path = require('path');

const SRC = process.env.SRC || 'D:/WinRAR/诊所管理系统.html';
const DST = path.join(__dirname, 'www', 'index.html');

function main() {
  if (!fs.existsSync(SRC)) {
    console.error('找不到正式版文件：' + SRC);
    console.error('请先在 .workbuddy 目录下执行：VER=v2.17 node build_release.js');
    process.exit(1);
  }

  const buf = fs.readFileSync(SRC);
  const text = buf.toString('utf8');

  // 基本自检：确认这是带原生桥接的版本，避免把旧文件同步进来
  const checks = [
    ['原生 TTS 探测函数', 'function nativeTts(){'],
    ['原生优先调用', "nat.speak(whole, String(TTS_RATE), String(TTS_PITCH), 'zh-CN');"],
    ['整句一次合成', "const whole=segs.join('');"],
    ['TTS 语速常量（第 34 轮）', 'TTS_RATE=0.82'],
    ['播报去重窗口（第 34 轮）', 'TTS_SPEAK_GUARD_MS'],
    ['服务端地址可配置（第 33 轮）', 'SYNC_SERVER_KEY'],
    ['Capacitor 壳判定（第 34 轮）', 'function isCapacitorShell(){'],
  ];
  let bad = 0;
  for (const [name, needle] of checks) {
    const hit = text.indexOf(needle) >= 0;
    console.log('  ' + (hit ? 'OK  ' : '缺失 ') + name);
    if (!hit) bad++;
  }
  if (bad) {
    console.error('\n源文件缺少原生桥接相关代码，已中止（避免把旧版本打进 APK）');
    process.exit(2);
  }

  fs.mkdirSync(path.dirname(DST), { recursive: true });
  fs.writeFileSync(DST, buf);
  console.log('\n已同步 -> ' + DST);
  console.log('大小: ' + buf.length + ' 字节');
}

main();
