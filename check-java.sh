#!/usr/bin/env bash
# Java 语法编译检查（不需要 Android SDK）
#
# 用最小 stub 顶替 Android / Capacitor 的 API，只验证我们写的两个文件
# 语法正确、符号引用存在、类型匹配。能提前抓出云端构建会报的编译错。
#
# 用法：bash check-java.sh <JDK目录>

set -e
export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"

JDK="${1:-}"
if [ -z "$JDK" ]; then
  echo "用法：bash check-java.sh <JDK目录>"
  exit 1
fi
JAVAC="$JDK/bin/javac.exe"
[ -f "$JAVAC" ] || JAVAC="$JDK/bin/javac"
if [ ! -f "$JAVAC" ]; then
  echo "找不到 javac：$JAVAC"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
STUBS="$ROOT/.javacheck/stubs"
SRC1="$ROOT/native-src/cn/clinic/manage/NativeTts.java"
SRC2="$ROOT/native-src/cn/clinic/manage/MainActivity.java"
OUT="$ROOT/.javacheck/out"

# ⚠️ 关键：Git Bash 会把 /D:/xxx 这种路径交给 javac 时转成 \d\WinRAR\...
#    （MSYS 的路径自动转换规则误判），导致 javac 报「找不到文件」。
#    统一转成 Windows 反斜杠路径再传给 javac，绕开转换器。
winpath() {
  local p="$1"
  # 已经是 /d/xxx 形式 -> D:/xxx
  if echo "$p" | grep -qE '^/[a-zA-Z]/'; then
    p="$(echo "$p" | sed -E 's#^/([a-zA-Z])/#\U\1:/#')"
  fi
  # 正斜杠转反斜杠
  echo "$p" | sed 's#/#\\#g'
}

W_STUBS="$(winpath "$STUBS")"
W_SRC1="$(winpath "$SRC1")"
W_SRC2="$(winpath "$SRC2")"
W_OUT="$(winpath "$OUT")"
W_LIST="$(winpath "$ROOT/.javacheck/stub-list.txt")"
W_LOG="$(winpath "$ROOT/.javacheck/compile.log")"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "=== 使用的 javac ==="
"$JAVAC" -version
echo "ROOT=$ROOT"

echo
echo "=== 生成 stub 文件清单 ==="
find "$STUBS" -name "*.java" | while read -r f; do winpath "$f"; done > "$ROOT/.javacheck/stub-list.txt"
echo "共 $(wc -l < "$ROOT/.javacheck/stub-list.txt") 个 stub"

echo
echo "=== 编译 stub ==="
"$JAVAC" -nowarn -encoding UTF-8 -d "$W_OUT" "@$W_LIST" 2>&1 | head -40

echo
echo "=== 编译本工程的两个 Java 文件 ==="
set +e
"$JAVAC" \
  -nowarn \
  -encoding UTF-8 \
  -source 17 -target 17 \
  -cp "$W_OUT" \
  -d "$W_OUT" \
  "$W_SRC1" "$W_SRC2" 2>&1 | tee "$ROOT/.javacheck/compile.log"
RC=${PIPESTATUS[0]}
set -e

echo
if [ "$RC" -eq 0 ]; then
  echo "✅ Java 编译检查通过（0 error）"
  echo "--- 生成的 class ---"
  find "$OUT/cn" -name "*.class" 2>/dev/null | sed "s|$OUT/||"
else
  echo "❌ Java 编译失败，错误如下："
  grep -E "error:|错误:" "$ROOT/.javacheck/compile.log" | head -40
fi
exit $RC
