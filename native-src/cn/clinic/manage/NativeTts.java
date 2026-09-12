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

    /** 第 34 轮：当前正在念的文本 + 起念时间，用于去重与打断判断 */
    private volatile String curText = null;
    private volatile long curStartAt = 0L;
    /** 同句去重窗口：这段时间内重复请求同一句，直接忽略（避免中途打断造成「忽大忽小」） */
    private static final long DUP_GUARD_MS = 2500L;
    /** 语速/音调只在变化时下发生效，避免每次 speak 都重置音频增益 */
    private float appliedRate = -1f;
    private float appliedPitch = -1f;

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

    /** 从系统可用音色里挑一个中文音色（优先高质量、优先离线）
     *
     *  第 34 轮修正「卡顿不连贯」：原来的评分把「离线」只加了 5 分，
     *  而网络音色能靠 QUALITY_VERY_HIGH(+30) 轻松反超 —— 结果选到网络音色，
     *  信号不好时边下边念，就是「一顿一顿、丢字」。现在改为**离线优先**：
     *  先只看离线音色，一个离线中文音色都没有时，才退回网络音色。 */
    private void pickBestVoice() {
        if (tts == null) return;
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return;
            Set<Voice> voices = tts.getVoices();
            if (voices == null || voices.isEmpty()) return;

            Voice bestOffline = null;   int bestOfflineScore = -1;
            Voice bestAny     = null;   int bestAnyScore     = -1;

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
                int q = v.getQuality();
                if (q >= Voice.QUALITY_VERY_HIGH) s += 30;
                else if (q >= Voice.QUALITY_HIGH) s += 20;

                boolean offline = !v.isNetworkConnectionRequired();
                if (offline) s += 40;   // 第 34 轮：离线硬性优先（原为 +5）

                if (s > bestAnyScore) { bestAnyScore = s; bestAny = v; }
                if (offline && s > bestOfflineScore) { bestOfflineScore = s; bestOffline = v; }
            }

            Voice chosen = (bestOffline != null) ? bestOffline : bestAny;
            int chosenScore = (bestOffline != null) ? bestOfflineScore : bestAnyScore;
            if (chosen != null) {
                tts.setVoice(chosen);
                Log.i(TAG, "选用音色: " + chosen.getName()
                        + " score=" + chosenScore
                        + " offline=" + !chosen.isNetworkConnectionRequired());
            }
        } catch (Exception e) {
            Log.w(TAG, "pickBestVoice 异常", e);
        }
    }

    // ---------------- 供网页调用的接口（方法签名要与 JS 侧 injection 一致） ----------------

    /** 播报。rate/pitch 与网页侧保持一致 */
    public void speak(String text, double rate, double pitch, String lang) {
        if (text == null || text.trim().isEmpty()) return;
        float r = (float) rate;
        float p = (float) pitch;
        if (r <= 0) r = 0.88f;
        if (p <= 0) p = 1.0f;

        /* 第 34 轮：同句去重。一次缴费提示若被触发两次（页面重渲染 / 多端回推），
           第二次 QUEUE_FLUSH 会**从中间截断**第一句 —— 人耳听到的就是
           「前半句正常、后半句突然发轻」，即「声音大小不一」的主因。 */
        long now = System.currentTimeMillis();
        String prev = curText;
        if (prev != null && prev.equals(text) && (now - curStartAt) < DUP_GUARD_MS) {
            Log.i(TAG, "同句在去重窗口内，忽略重复播报");
            return;
        }

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
            /* 第 34 轮：语速/音调**只在变化时**下发。每次 speak 都重设会让引擎
               重新计算音频增益，正是「音量忽大忽小」的另一个来源。 */
            if (Math.abs(rate - appliedRate) > 0.001f) {
                tts.setSpeechRate(rate);
                appliedRate = rate;
            }
            if (Math.abs(pitch - appliedPitch) > 0.001f) {
                tts.setPitch(pitch);
                appliedPitch = pitch;
            }

            Bundle params = new Bundle();
            // 用 QUEUE_FLUSH：新播报直接打断旧的，符合「刷新缴费金额」的场景
            // （同句重复的情况已在 speak() 里被去重拦掉，不会误伤）
            int mode = TextToSpeech.QUEUE_FLUSH;
            String uttId = "clinic_" + System.currentTimeMillis();

            curText = text;
            curStartAt = System.currentTimeMillis();

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
        curText = null;
        curStartAt = 0L;
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
