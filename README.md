# 门诊管理 · Android 打包工程（Capacitor + 原生 TTS 桥接）

把网页版诊所管理系统打包成 **Android 安装包（APK）**，应用名显示为「**门诊管理**」，并解决一个关键问题：

> **Android 的网页组件（WebView）不支持网页语音合成**，所以任何「把网页装进 App」的壳
> （WebToApp / Cordova / Capacitor 都一样）在里面按「语音播报」都没有声音。
> 本工程通过**原生 TTS 桥接**绕开这个限制：调用 Android 系统的语音引擎播报。

---

## 一、先搞清楚两件事的关系（重要）

你提到的两个东西解决的是**不同**的问题，缺一不可，但主次不同：

| | 作用 | 缺了会怎样 |
|---|---|---|
| **原生 TTS 桥接**（`NativeTts.java`） | 把文字交给 Android 系统的 `TextToSpeech` 播报 | **压根没有声音** |
| **`setMediaPlaybackRequiresUserGesture(false)`**（`MainActivity.java`） | 放行「免用户手势自动播放」 | 桥接通了，也可能被自动播放策略拦掉 |

**注意**：`setMediaPlaybackRequiresUserGesture(false)` 本身**不能**补上缺失的语音合成能力。
它只是个「允许放声音」的开关——WebView 里 `speechSynthesis` 依然是 `undefined`。
真正提供声音的是原生桥接。两者配合才完整。

---

## 二、网页侧怎么配合的

网页里加了一层「原生优先、自动回落」的分流（`诊所管理系统-预览.html` 语音模块）：

```
点「语音播报」
   ├─ 有 window.NativeTTS  →  走原生（Android 系统 TTS）★ App 内走这条
   └─ 没有                →  走原有 speechSynthesis（浏览器里走这条）
```

所以**同一份网页文件**：
- 在手机/电脑**浏览器**里打开 → 用浏览器自己的语音，行为跟以前完全一样
- 在**这个 APK** 里打开 → 自动识别到原生通道，用系统 TTS 播报

网页侧无需为 App 单独维护一份。

---

## 三、怎么构建 APK（不需要在电脑上装 Android 开发环境）

构建在 GitHub 的服务器上完成，你的电脑什么都不用装。

### 第 1 步：注册 / 登录 GitHub

打开 https://github.com ，没有账号就注册一个（免费）。

### 第 2 步：新建一个仓库

1. 右上角 **+** → **New repository**
2. **Repository name** 填：`clinic-android`（随便起，好记就行）
3. 选 **Public**（公开；免费账号也能跑 Actions。介意的话选 Private 也行，Actions 同样能用）
4. **不要**勾选 "Add a README file"
5. 点 **Create repository**

### 第 3 步：把本工程传上去

**最简单的办法（推荐）**：在本文件夹（`android-tts`）里打开命令行，执行这一条：

```bash
bash push-to-github.sh https://github.com/你的用户名/clinic-android.git
```

脚本会自动同步最新网页 → 初始化仓库 → 提交 → 设置远程 → 推送，并在最后告诉你下一步该点哪里。

<details>
<summary>也可以手动执行这几条命令</summary>

```bash
git init
git add .
git commit -m "门诊管理 Android 打包工程"
git branch -M main
git remote add origin https://github.com/<你的用户名>/clinic-android.git
git push -u origin main
```
</details>

第一次 `git push` 会弹出登录窗口，按提示用浏览器授权即可。

### 第 4 步：等构建完成

推送完成后：
1. 打开你的仓库页面 → 上方 **Actions** 标签
2. 会看到一条「构建 Android APK」正在跑（黄色圆点转圈）
3. 等 3~6 分钟，变成**绿色对勾**就成功了

> 如果显示红色叉：点进去看哪一步报错，把报错贴给我，我来修。

### 第 5 步：下载 APK

1. 点进那条成功的构建记录
2. 拉到页面最下方 **Artifacts** 区域
3. 点 **门诊管理-Android-APK** 下载
4. 得到一个 zip，解压后里面是 `门诊管理-Android.apk`

### 第 6 步：装到手机上

1. 把 APK 传到手机（微信文件传输助手 / 数据线 / 网盘都行）
2. 手机上点开安装，系统会提示「允许安装未知来源应用」→ 允许
3. 装好后桌面上会出现「**门诊管理**」图标（图标与服务端/网页同一张）

---

## 四、装好后的表现

| 场景 | 表现 |
|---|---|
| 点「语音播报」 | 用**系统 TTS** 播报，声音由手机自带的语音引擎（如 Google 语音服务、厂商语音）发出 |
| 设置页「语音自检」 | 显示「✓ 正在使用系统原生语音播报（引擎名）」，而不是之前的「不支持」警告 |
| 关掉缴费提示 | 播报立即停止 |
| 没装中文语音数据 | 会提示去系统设置安装；多数国产手机自带中文引擎，通常无需额外操作 |

**如果没声音，按顺序排查：**
1. 手机「设置 → 无障碍 / 语言与输入 → 文字转语音」里，确认有可用的 TTS 引擎且已安装**中文**语音数据
2. 确认手机媒体音量没静音
3. 到 App 的「系统设置」页看语音自检那一行的提示

---

## 五、以后改了网页，怎么重新打包

网页改动在 `D:/WinRAR/诊所管理系统-预览.html` 里做完、出正式版后，把新文件同步过来：

```bash
# 在 .workbuddy/android-tts 目录下
node sync-web.js
git add .
git commit -m "更新网页"
git push
```

推送后 GitHub 会自动重新构建，去 Actions 页面取新 APK 即可。

---

## 六、工程结构

```
android-tts/
├── .github/workflows/build-apk.yml   GitHub 云端构建流程
├── capacitor.config.json             Capacitor 配置（appName = 门诊管理）
├── package.json                      依赖声明
├── ICON_256.PNG                  ★ 应用图标源（与网页 favicon / fnOS 服务端同一张）
├── push-to-github.sh             ★ 一键推送到 GitHub（推荐用这个）
├── sync-web.js                       把网页版同步到 www/
├── check-java.sh                 ★ 本地 Java 编译自检（可选）
├── www/index.html                    网页本体（构建时打包进 APK）
├── native-src/cn/clinic/manage/
│   ├── MainActivity.java             放行自动播放 + 注入原生 TTS
│   └── NativeTts.java            ★ 原生 TTS 桥接核心（包住系统 TextToSpeech）
├── tools/
│   ├── make-android-icons.py     ★ 由 ICON_256.PNG 生成 Android 全套 mipmap
│   ├── drytest-icons.py              图标生成干跑自检（36 项断言）
│   ├── patch-manifest.py             给 AndroidManifest 打补丁（TTS/权限/明文流量）
│   └── drytest-manifest.py           Manifest 补丁干跑自检（12 项断言）
├── .javacheck/                       本地编译自检用的最小 stub（不影响云端构建）
└── README.md                         本文件
```

---

## 六·一、应用图标怎么统一的

**一张图，四端共用**（网页 favicon、侧边栏品牌位、fnOS 服务端、Android 桌面图标）：

```
fnpack/clinic/ICON_256.PNG (256×256, 96317 B, md5 f1750ad3…)
   │
   ├─→ 网页 <link rel="icon"> + <link rel="apple-touch-icon">  (base64 内嵌)
   ├─→ 网页侧边栏 .brand-icon                                   (base64 内嵌)
   ├─→ fnOS 服务端  app/ui/images/icon_256.png
   └─→ Android 桌面图标（CI 里由 tools/make-android-icons.py 现生成）
         ├─ mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png    48/72/96/144/192
         ├─ mipmap-*/ic_launcher_round.png                              同上
         ├─ mipmap-*/ic_launcher_foreground.png                         108/162/216/324/432
         ├─ mipmap-anydpi-v26/ic_launcher{,_round}.xml                  自适应图标描述
         └─ values/ic_launcher_background.xml                           背景色 #0A2B1B
```

> **为什么图标必须在 CI 里生成**：`npx cap add android` 用的是 Capacitor 的默认模板图标
> （蓝底 Capacitor 标志），会覆盖 `res/mipmap-*`；而 `capacitor.config.json` 里**没有图标字段**，
> Capacitor 只认 appId / appName / webDir。所以图标只能在 `cap add android` **之后**注入。

> **自适应图标的前景缩放是算出来的，不是拍脑袋定的**：Android 8+ 的系统只保证
> 中心 66dp 圆内完整可见（66/108 = 0.6111），而本图标是近乎满幅的圆角方块
> （最远角距 = 源图半宽的 1.226 倍）。若按「占画布 61%」直接缩放，四角会被启动器裁掉。
> 正确算法：`占比 = (66/108) ÷ 1.2264 × 0.92 ≈ 0.4584`。`drytest-icons.py` 里有对应断言把关。

---

## 七、已完成的验证（推之前就跑过了）

| 验证项 | 方式 | 结果 |
|---|---|---|
| 两个 Java 文件能编译 | 真实 `javac 17.0.20.1` + 最小 stub | ✅ **0 error**，产出 7 个 class |
| 网页侧原生/网页分流 | 19 项自动化断言 | ✅ **19 / 19** |
| `www/index.html` 与正式版一致 | MD5 | ✅ 完全相同（每次出包后由 `sync-web.js` 保证） |
| 工作流结构完整 | YAML 解析 + 步骤齐备性检查 | ✅ 16 步齐备、顺序正确 |
| 工作流内嵌脚本缩进 | heredoc 顶格检查 | ✅ 正确（不会 `IndentationError`） |
| `package.json` / `capacitor.config.json` | JSON 解析 | ✅ 合法 |
| 图标生成（含 66dp 安全圆） | `drytest-icons.py` | ✅ **36 / 36** |
| APK 图标统一 + 应用名「门诊管理」 | `verify_round35.js` | ✅ **49 / 49** |
| Manifest 补丁 | `drytest-manifest.py` | ✅ **12 / 12** |
| 客户端全量回归 | `run_all_verify.js`（21 个脚本） | ✅ **1288 / 1288，0 失败** |

> 说明：Java 编译用的是「最小 stub + 真实 javac」——stub 只顶替 Android/Capacitor 的 API 签名，
> 因此能抓出**语法错误、拼错的常量、类型不匹配、符号找不到**，效果与云端一致。
> 云端用的是**真实 Android SDK**，会额外多验一层资源与 Manifest 合并（那是 stub 覆盖不到的部分）。

---

## 八、技术备注

- **为什么 `addJavascriptInterface` 的参数要拍平成字符串**：Android 的 JS 桥只能传基本类型，
  不能传 JS 对象。所以网页侧调用是 `NativeTTS.speak(文本, '0.82', '1', 'zh-CN')`，
  四个独立参数，而不是一个配置对象。
- **为什么 `NativeTts` 要缓存播报请求**：`TextToSpeech` 的初始化是**异步**的，
  在 `onInit` 回调成功之前调用 `speak` 会被静默丢弃——这是原生 TTS 最常见的「没声音」原因。
  本实现把就绪前的请求缓存下来，初始化完成后立刻补播。
- **为什么 `AndroidManifest` 要加 `<queries>`**：Android 11+ 应用默认「看不见」其他应用，
  不声明 `TTS_SERVICE` 查询，`TextToSpeech` 会找不到引擎。
- **为什么注入原生桥接用「定时轮询」而不是 `onPageFinished`**：Capacitor 自己在 Bridge 里
  装了一个 `WebViewClient` 处理路由与插件回调。我们若调用 `setWebViewClient()` 去挂自己的
  `onPageFinished`，就会把 Capacitor 那个顶掉，结果是 App 白屏或直接崩溃。
  改用 1.5 秒周期的重复注入（`addJavascriptInterface` 同名覆盖是安全的），完全不碰 Capacitor 的组件。
- **产物是 Debug APK**：用于自用安装。若要上架应用商店，需要改签名配置出 Release 版。
- **iOS 不需要这套桥接**：iOS 的 `WKWebView` **支持** `SpeechSynthesis`，
  当前网页代码在 iOS 上会走原有的网页语音通道，行为正常。
