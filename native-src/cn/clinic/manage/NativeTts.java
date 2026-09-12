package cn.clinic.manage;

import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.util.Log;

import java.util.Locale;
import java.util.Set;

/**
 * 原生 TTS 桥接（诊所管理系统 · Android 壳专用）
 *
 * 为什么需要它：Android WebView 从 Chromium 层面就不实现 Web Speech 的合成端，
 * 网页里的 window.speechSynthesis 在 App 内**永远是 undefined**。
 * 所以由原生侧包一层 Android 系统 TextToSpeech，注入给网页调用。
 *
 * 注入的接口（网页侧 window.NativeTTS）：
 *   speak(text, {rate, pitch, lang})  播报
 *   stop()                            停止
 *   isReady()                         引擎是否就绪
 *   engineName()                      当前引擎名（设置页展示用）
 *   voiceName()                       当前音色名（设置页展示用）
 *
 * 注意 TextToSpeech 的初始化是**异步**的：构造后要等 onInit 回调，
 * 在 init 之前调用 speak 会被静默丢弃（这是原生 TTS 最常见的「没声音」原因）。
 * 本类用 pendingText 把「就绪前的播报请求」缓存下来，init 成功后立刻补播。
 */
public class NativeTts {

    private static final String TAG = "NativeTts";
    /** 网页侧通过 Capacitor 的 addJavascriptInterface 拿到的全局对象名 */
    public static final String JS_NAME = "NativeTTS";

    private final Context context;

    private TextToSpeech tts = null;
    private volatile boolean ready = false;
    private volatile boolean initFailed = false;

    /** ready 之前收到的播报请求（只保留最后一条，避免堆积） */
    private String pendingText = null;
    private float pendingRate = 0.88f;
    private float pendingPitch = 1.02f;
    private String pendingLang = "zh-CN";

    /** 引擎不可用时的回调（交给网页提示用户去系统设置装语音数据） */
    public interface FailListener { void onFail(String reason); }
    private FailListener failListener = null;

    public NativeTts(Context ctx) {
        this.context = ctx.getApplicationContext();
        init();
    }

    public void setFailListener(FailListener l) { this.failListener = l; }

    private void init() {
        try {
            tts = new TextToSpeech(context, new TextToSpeech.OnInitListener() {
                @Override
                public void onInit(int status) {
                    if (status != TextToSpeech.SUCCESS) {
                        initFailed = true;
                        Log.w(TAG, "TextToSpeech 初始化失败, status=" + status);
                        if (failListener != null) failListener.onFail("init_failed");
                        return;
                    }
                    applyLanguage();
                    pickBestVoice();
                    ready = true;
                    Log.i(TAG, "TextToSpeech 就绪: engine=" + engineName() + ", voice=" + voiceName());

                    // 补播「就绪前」的请求
                    String t = pendingText;
                    if (t != null) {
                        pendingText = null;
                        speakNow(t, pendingRate, pendingPitch);
                    }
                }
            });
        } catch (Exception e) {
            initFailed = true;
            Log.e(TAG, "TextToSpeech 构造异常", e);
            if (failListener != null) failListener.onFail("init_exception");
        }
    }

    /** 设置中文（优先中国大陆简体） */
    private void applyLanguage() {
        if (tts == null) return;
        try {
            int r = tts.setLanguage(Locale.SIMPLIFIED_CHINESE);
            if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "简体中文不可用，尝试 CHINA");
                r = tts.setLanguage(Locale.CHINA);
                if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                    Log.w(TAG, "中文语音数据缺失，需在系统设置中安装");
                    if (failListener != null) failListener.onFail("no_zh_data");
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "setLanguage 异常", e);
        }
    }

    /** 从系统可用音色里挑一个中文音色（优先 high quality，其次名字含 zh/Chinese） */
    private void pickBestVoice() {
        if (tts == null) return;
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return;
            Set<Voice> voices = tts.getVoices();
            if (voices == null || voices.isEmpty()) return;

            Voice best = null;
            int bestScore = -1;
            for (Voice v : voices) {
                if (v == null) continue;
                Locale loc = v.getLocale();
                if (loc == null) continue;
                String lg = loc.toString().replace('_', '-').toLowerCase(Locale.ROOT);
                String nm = String.valueOf(v.getName()).toLowerCase(Locale.ROOT);

                int s = 0;
                if (lg.startsWith("zh-cn") || lg.startsWith("zh-hans")) s += 100;
                else if (lg.startsWith("zh")) s += 70;
                else continue;   // 只要中文

                if (nm.contains("chinese") || nm.contains("mandarin") || nm.contains("普通话")) s += 20;
                // 高质量音色优先
                int q = v.getQuality();
                if (q >= Voice.QUALITY_VERY_HIGH) s += 30;
                else if (q >= Voice.QUALITY_HIGH) s += 20;
                // 网络音色通常更自然，但离线更可靠；这里给 network 少量加分
                if (!v.isNetworkConnectionRequired()) s += 5;

                // 排除明显是「成人/儿童」等特殊角色的杂音色（保守：不排除，只是不额外加分）

                if (s > bestScore) { bestScore = s; best = v; }
            }
            if (best != null) {
                tts.setVoice(best);
                Log.i(TAG, "选用音色: " + best.getName() + " score=" + bestScore);
            }
        } catch (Exception e) {
            Log.w(TAG, "pickBestVoice 异常", e);
        }
    }

    // ---------------- 供网页调用的接口（方法签名要与 JS 侧 injection 一致） ----------------

    /** 播报。rate/pitch 与网页侧保持一致（0.88 / 1.02） */
    public void speak(String text, double rate, double pitch, String lang) {
        if (text == null || text.trim().isEmpty()) return;
        float r = (float) rate;
        float p = (float) pitch;
        if (r <= 0) r = 0.88f;
        if (p <= 0) p = 1.02f;

        if (!ready) {
            // 引擎还没就绪：缓存请求，init 成功后补播
            pendingText = text;
            pendingRate = r;
            pendingPitch = p;
            if (lang != null) pendingLang = lang;
            Log.i(TAG, "引擎未就绪，缓存播报请求: " + text);
            return;
        }
        speakNow(text, r, p);
    }

    private void speakNow(String text, float rate, float pitch) {
        if (tts == null) return;
        try {
            tts.setSpeechRate(rate);
            tts.setPitch(pitch);

            Bundle params = new Bundle();
            // 用 QUEUE_FLUSH：新播报直接打断旧的，符合「刷新缴费金额」的场景
            int mode = TextToSpeech.QUEUE_FLUSH;
            String uttId = "clinic_" + System.currentTimeMillis();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                tts.speak(text, mode, params, uttId);
            } else {
                // 老版本 API
                tts.speak(text, mode, null);
            }
        } catch (Exception e) {
            Log.e(TAG, "speak 异常", e);
        }
    }

    /** 停止播报 */
    public void stop() {
        pendingText = null;
        try { if (tts != null) tts.stop(); } catch (Exception e) { Log.w(TAG, "stop 异常", e); }
    }

    /** 引擎是否就绪 */
    public boolean isReady() { return ready; }

    /** 初始化是否已失败（网页可据此提前提示） */
    public boolean isInitFailed() { return initFailed; }

    /** 当前 TTS 引擎名（设置页展示用） */
    public String engineName() {
        try {
            if (tts == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.ICE_CREAM_SANDWICH) return "";
            String e = tts.getDefaultEngine();
            return e == null ? "" : e;
        } catch (Exception e) { return ""; }
    }

    /** 当前音色名（设置页展示用） */
    public String voiceName() {
        try {
            if (tts == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return "";
            Voice v = tts.getVoice();
            if (v == null) return "";
            Locale l = v.getLocale();
            return v.getName() + (l == null ? "" : " (" + l.toString() + ")");
        } catch (Exception e) { return ""; }
    }

    /** 释放资源（Activity destroy 时调用） */
    public void destroy() {
        ready = false;
        try {
            if (tts != null) { tts.stop(); tts.shutdown(); }
        } catch (Exception e) { Log.w(TAG, "destroy 异常", e); }
        tts = null;
    }
}
