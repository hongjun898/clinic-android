package cn.clinic.manage;

import android.os.Build;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

/**
 * 主 Activity（诊所管理系统 · Android 壳）
 *
 * 职责：
 *  1. 调 setMediaPlaybackRequiresUserGesture(false) —— 放行免手势自动播放。
 *     这一步是**配套措施**，不是 TTS 的来源：它只解决「有音频但被自动播放策略拦」，
 *     解决不了「WebView 压根没有 speechSynthesis」。真正提供声音的是 NativeTts。
 *  2. 把原生 TTS 注入到 WebView，网页侧通过 window.NativeTTS 调用。
 *
 * 注入时机很关键：
 *  Capacitor 的 Bridge（含 WebView）是在 super.onCreate() 里建好的，
 *  但 WebView **加载页面**是异步的。如果在 onCreate 里立刻注入，可能：
 *    a) getWebView() 还是 null；
 *    b) 注入发生在页面 JS 开始跑之后 —— 网页启动时探测 window.NativeTTS 会探测不到，
 *       于是错误地回落到（在 WebView 里根本不存在的）speechSynthesis。
 *  本实现用一个短周期轮询（1.5 秒）反复注入来兜底。
 *
 *  ⚠️ 为什么不用 setWebViewClient 的 onPageFinished 注入？
 *    因为 Capacitor 自己在 Bridge 里装了一个 WebViewClient 处理路由/插件回调，
 *    我们一旦调用 setWebViewClient()，就会把 Capacitor 那个顶掉，
 *    结果是 App 启动后白屏或直接崩溃。轮询注入虽然笨，但完全不碰 Capacitor 的组件。
 *  重复注入同一个接口名是安全的（后注入的覆盖前者）。
 */
public class MainActivity extends BridgeActivity {

    private NativeTts nativeTts = null;
    private java.util.Timer injectTimer = null;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // ---- 1. 放行自动播放（免用户手势） ----
        try {
            WebView webView = getWebViewSafe();
            if (webView != null) {
                WebSettings settings = webView.getSettings();
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1) {
                    settings.setMediaPlaybackRequiresUserGesture(false);
                }
                settings.setJavaScriptEnabled(true);
                settings.setDomStorageEnabled(true);
                // 允许混合内容（本系统可能通过 http 访问 NAS 上的服务）
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
                }
            }
        } catch (Exception e) {
            android.util.Log.w("MainActivity", "WebView 设置失败", e);
        }

        // ---- 2. 注入原生 TTS（立即试一次 + 设好页面加载完成后的再注入） ----
        installTtsBridge();
    }

    private WebView getWebViewSafe() {
        try {
            if (getBridge() == null) return null;
            return getBridge().getWebView();
        } catch (Exception e) {
            return null;
        }
    }

    private synchronized void installTtsBridge() {
        try {
            final WebView webView = getWebViewSafe();
            if (webView == null) {
                android.util.Log.w("MainActivity", "拿不到 WebView，无法注入原生 TTS");
                return;
            }

            if (nativeTts == null) {
                nativeTts = new NativeTts(this);
                nativeTts.setFailListener(new NativeTts.FailListener() {
                    @Override
                    public void onFail(String reason) {
                        android.util.Log.w("MainActivity", "原生 TTS 不可用: " + reason);
                    }
                });
            }

            // 反复注入几次。原因：Capacitor 的 WebView 会重建（如配置变更、页面重载），
            // 每次重建后 addJavascriptInterface 的注入都会丢失。
            // 用一个短周期轮询 + 页面状态判断来兜底，比覆盖 WebViewClient 安全
            // （覆盖 setWebViewClient 会顶掉 Capacitor 自己的客户端，导致 App 直接坏掉）。
            if (injectTimer == null) {
                injectTimer = new java.util.Timer();
                injectTimer.scheduleAtFixedRate(new java.util.TimerTask() {
                    @Override
                    public void run() {
                        try {
                            WebView v = getWebViewSafe();
                            if (v != null && nativeTts != null) {
                                injectNow(v);
                            } else if (v == null) {
                                // WebView 还没建好，下一轮再试
                            }
                        } catch (Exception e) {
                            android.util.Log.w("MainActivity", "定时注入失败", e);
                        }
                    }
                }, 0L, 1500L);
            }

            injectNow(webView);
        } catch (Exception e) {
            android.util.Log.e("MainActivity", "注入原生 TTS 失败", e);
        }
    }

    private void injectNow(WebView webView) {
        try {
            if (webView == null || nativeTts == null) return;
            webView.addJavascriptInterface(new TtsJsBridge(nativeTts), NativeTts.JS_NAME);
            android.util.Log.i("MainActivity", "原生 TTS 已注入为 window." + NativeTts.JS_NAME);
        } catch (Exception e) {
            android.util.Log.e("MainActivity", "injectNow 失败", e);
        }
    }

    @Override
    public void onDestroy() {
        // 先停掉定时注入，否则 Activity 销毁后 Timer 线程还在跑，会泄漏 WebView 引用
        try {
            if (injectTimer != null) { injectTimer.cancel(); injectTimer = null; }
        } catch (Exception e) {
            android.util.Log.w("MainActivity", "停止注入定时器异常", e);
        }
        try {
            if (nativeTts != null) { nativeTts.destroy(); nativeTts = null; }
        } catch (Exception e) {
            android.util.Log.w("MainActivity", "释放原生 TTS 异常", e);
        }
        super.onDestroy();
    }

    /**
     * 暴露给 JS 的适配层。
     *
     * JS 侧用法：
     *   window.NativeTTS.speak('请缴费 28 元，谢谢', '0.88', '1.02', 'zh-CN')
     *   window.NativeTTS.stop()
     *   window.NativeTTS.isReady()      -> boolean
     *   window.NativeTTS.engineName()   -> string
     *   window.NativeTTS.voiceName()    -> string
     *
     * 注意：addJavascriptInterface 的方法**只能用基本类型 / String**，
     * 不能直接传 JS 对象；所以这里把参数拍平成独立参数。
     */
    public static class TtsJsBridge {
        private final NativeTts tts;

        TtsJsBridge(NativeTts t) { this.tts = t; }

        @android.webkit.JavascriptInterface
        public void speak(String text, String rate, String pitch, String lang) {
            double r = 0.88, p = 1.02;
            try { if (rate != null && !rate.isEmpty()) r = Double.parseDouble(rate); } catch (Exception ignored) {}
            try { if (pitch != null && !pitch.isEmpty()) p = Double.parseDouble(pitch); } catch (Exception ignored) {}
            tts.speak(text, r, p, (lang == null || lang.isEmpty()) ? "zh-CN" : lang);
        }

        @android.webkit.JavascriptInterface
        public void stop() { tts.stop(); }

        @android.webkit.JavascriptInterface
        public boolean isReady() { return tts.isReady(); }

        @android.webkit.JavascriptInterface
        public boolean isInitFailed() { return tts.isInitFailed(); }

        @android.webkit.JavascriptInterface
        public String engineName() { return tts.engineName(); }

        @android.webkit.JavascriptInterface
        public String voiceName() { return tts.voiceName(); }
    }
}
