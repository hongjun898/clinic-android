#!/usr/bin/env bash
# ============================================================
#  诊所管理系统 · Android 打包工程 —— 一键推送到 GitHub
#
#  用法（在本文件夹里执行）：
#      bash push-to-github.sh https://github.com/你的用户名/clinic-android.git
#
#  也可以不带参数运行，脚本会提示你粘贴仓库地址。
# ============================================================
set -e

export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"

REPO="$1"

echo "================================================"
echo "  诊所管理系统 · Android 打包工程"
echo "  推送到 GitHub（推送后云端自动开始构建 APK）"
echo "================================================"
echo

# ---------- 0. 前置检查 ----------
if ! command -v git >/dev/null 2>&1; then
  echo "❌ 没找到 git。请先安装 Git for Windows：https://git-scm.com/download/win"
  exit 1
fi

if [ -z "$REPO" ]; then
  echo "请粘贴你的 GitHub 仓库地址（形如 https://github.com/你的用户名/clinic-android.git）"
  echo "然后回车："
  read -r REPO
fi

if [ -z "$REPO" ]; then
  echo "❌ 仓库地址为空，已退出。"
  exit 1
fi

# 规范化：去掉尾部空格
REPO="$(echo "$REPO" | tr -d '[:space:]')"

# 如果用户只给了网页地址，自动补 .git
case "$REPO" in
  *.git) ;;
  http*://github.com/*/*) REPO="${REPO}.git" ;;
esac

echo
echo "→ 目标仓库：$REPO"
echo

# ---------- 1. 同步最新网页 ----------
echo "[1/5] 同步最新网页到 www/ ..."
if [ -f "sync-web.js" ]; then
  # sync-web.js 自带自检，若网页版本不对会拒绝同步
  if ! node sync-web.js; then
    echo "❌ 网页同步失败（自检未通过）。请先在 D:/WinRAR 用 build_release.js 出新正式版，再重试。"
    exit 1
  fi
else
  echo "⚠️  没找到 sync-web.js，跳过同步（将使用 www/ 里的现有文件）"
fi
echo

# ---------- 2. 初始化仓库 ----------
echo "[2/5] 初始化本地仓库 ..."
if [ ! -d ".git" ]; then
  git init -q
  git branch -M main
  echo "    已初始化"
else
  echo "    已存在 .git，沿用（不重新初始化，避免丢历史）"
fi
echo

# ---------- 3. 提交 ----------
echo "[3/5] 提交改动 ..."
git add .
if git diff --cached --quiet; then
  echo "    没有新改动"
else
  git commit -q -m "诊所管理系统 Android 打包工程 $(date '+%Y-%m-%d %H:%M')"
  echo "    已提交"
fi
echo

# ---------- 4. 设置远程 ----------
echo "[4/5] 设置远程仓库 ..."
if git remote get-url origin >/dev/null 2>&1; then
  OLD="$(git remote get-url origin)"
  if [ "$OLD" != "$REPO" ]; then
    git remote set-url origin "$REPO"
    echo "    已从 $OLD 改为 $REPO"
  else
    echo "    origin 已是 $REPO"
  fi
else
  git remote add origin "$REPO"
  echo "    已添加 origin"
fi
echo

# ---------- 5. 推送 ----------
echo "[5/5] 推送（第一次会弹出登录窗口，按提示用浏览器授权）..."
echo
if git push -u origin main; then
  echo
  echo "================================================"
  echo "  ✅ 推送成功！"
  echo "================================================"
  echo
  # 从仓库地址反推 Actions 页面地址
  WEB="$(echo "$REPO" | sed -e 's#\.git$##')"
  echo "接下来："
  echo "  1. 打开  $WEB/actions"
  echo "  2. 会看到「构建 Android APK」正在跑（黄点转圈）"
  echo "  3. 等 3~6 分钟变绿 ✅"
  echo "  4. 点进这条构建记录 → 拉到最下方 Artifacts → 下载"
  echo "     诊所管理系统-Android-APK，解压得到 .apk"
  echo
  echo "如果变红了，把报错内容发我，我来修。"
else
  echo
  echo "❌ 推送失败。常见原因："
  echo "   · 仓库地址写错（应为 https://github.com/用户名/仓库名.git）"
  echo "   · 仓库还没在 GitHub 上创建"
  echo "   · 弹出的登录窗口没完成授权"
  echo "  把这里的报错发我。"
  exit 1
fi
