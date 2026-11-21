// android_bridge.cpp - JNI entry points the Android app (com.wither.nsmbw) calls into libmain.so.
#if defined(__ANDROID__)

// The Java package of the app that hosts libmain.so. Each Android app passes its own through
// -DMKW_ANDROID_JNI_PACKAGE=<package with dots as underscores> (see runtime/CMakeLists.txt).
#ifndef MKW_ANDROID_JNI_PACKAGE
#define MKW_ANDROID_JNI_PACKAGE com_wither_nsmbw
#endif
#define MKW_JNI_NAME_(pkg, method) Java_##pkg##_GameActivity_##method
#define MKW_JNI_NAME(pkg, method) MKW_JNI_NAME_(pkg, method)
#define MKW_JNI(method) MKW_JNI_NAME(MKW_ANDROID_JNI_PACKAGE, method)

#include "display_settings.h"
#include "graphics_info.h"
#include "runtime_config.h"
#include "settings_overlay.h"
#include "virtual_remote.h"

#include "netplay/net_socket.h"
#include "netplay_session.h"
#include "netplay_start.h"
#include "netplay_ui.h"

#include <SDL3/SDL_system.h>
#include <jni.h>

#include <chrono>
#include <cstdint>
#include <string>
#include <thread>

namespace AndroidBridge {

// Network play: ask the activity to start the game again in a fresh process (GameActivity
// .restartForSession), then park this thread until Android ends the process.
bool RestartGame() {
    auto* env = static_cast<JNIEnv*>(SDL_GetAndroidJNIEnv());
    auto activity = static_cast<jobject>(SDL_GetAndroidActivity());
    if (env == nullptr || activity == nullptr) {
        return false;
    }
    jclass type = env->GetObjectClass(activity);
    jmethodID restart = type != nullptr ? env->GetMethodID(type, "restartForSession", "()V") : nullptr;
    if (restart == nullptr) {
        env->ExceptionClear();
        return false;
    }
    env->CallVoidMethod(activity, restart);
    env->DeleteLocalRef(activity);
    for (;;) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
}

} // namespace AndroidBridge

extern "C" {

// GameActivity.nativeSetTouchState: the on-screen remote (VirtualRemote::TouchButton bits) and the
// phone's motion (shake, tilt -1..1) for player 1. Called from the UI thread on every change.
JNIEXPORT void JNICALL MKW_JNI(nativeSetTouchState)(
    JNIEnv*, jclass, jint buttons, jboolean shake, jfloat tilt)
{
    VirtualRemote::SetTouchState(static_cast<uint32_t>(buttons), shake == JNI_TRUE, tilt);
}

// GameActivity.nativeSetTouchPointer: the finger on the screen, in window pixels, with the size of the window.
// While it is down the Wii pointer aims at it and holding it is A (the touch counterpart of the mouse).
JNIEXPORT void JNICALL MKW_JNI(nativeSetTouchPointer)(JNIEnv*, jclass, jfloat x, jfloat y, jint width, jint height,
                                                      jboolean down)
{
    VirtualRemote::SetTouchPointer(x, y, static_cast<int>(width), static_cast<int>(height), down == JNI_TRUE);
}

// GameActivity.nativeApplyDisplaySettings: the Display menu. The aspect (0 original 4:3, 1 16:9,
// 2 fill the screen) and the render scale (480 lines per 1x) apply at the next frame; 4:3 versus a
// widescreen mode only at the next start, since the game reads it at boot.
JNIEXPORT void JNICALL MKW_JNI(nativeApplyDisplaySettings)(
    JNIEnv*, jclass, jint aspect, jfloat renderScale, jboolean showFps)
{
    // Through the settings overlay, so the game's own settings window shows the same choice. A scale
    // of 0 is "match the screen".
    settings_overlay::SetAspect(aspect < 0 || aspect > 3 ? DisplaySettings::kAspectFill : static_cast<int32_t>(aspect));
    settings_overlay::SetRenderScale(renderScale >= 0.0f ? renderScale : 1.0f);
    settings_overlay::SetShowFps(showFps == JNI_TRUE);
}

// GameActivity.nativeApplyGraphicsSettings: the Graphics menu (the same settings as the PC settings window).
JNIEXPORT void JNICALL MKW_JNI(nativeApplyGraphicsSettings)(
    JNIEnv*, jclass, jboolean interp120, jboolean vsync, jboolean disableCopyFilter)
{
    settings_overlay::SetFrameInterpolation120(interp120 == JNI_TRUE);
    settings_overlay::SetVSync(vsync == JNI_TRUE);
    settings_overlay::SetDisableCopyFilter(disableCopyFilter == JNI_TRUE);
}

// GameActivity.nativeGraphicsSettings: bit 0 = 120 fps interpolation, bit 1 = V-Sync, bit 2 = copy filter disabled.
JNIEXPORT jint JNICALL MKW_JNI(nativeGraphicsSettings)(JNIEnv*, jclass)
{
    return (settings_overlay::FrameInterpolation120() ? 1 : 0) | (settings_overlay::VSync() ? 2 : 0) |
           (settings_overlay::DisableCopyFilter() ? 4 : 0);
}

// GameActivity.nativeGameLanguage: the game's language as the SC code (1 en, 2 de, 3 fr, 4 es, 5 it). The PAL
// disc loads its msg/ folder from it at boot.
JNIEXPORT jint JNICALL MKW_JNI(nativeGameLanguage)(JNIEnv*, jclass)
{
    return static_cast<jint>(RuntimeConfigFile::Language());
}

// GameActivity.nativeSetGameLanguage: "en", "de", "fr", "es" or "it", saved to Config.toml [game] language.
// Takes effect at the next start, when the game reads its messages.
JNIEXPORT void JNICALL MKW_JNI(nativeSetGameLanguage)(JNIEnv* env, jclass, jstring code)
{
    if (code == nullptr) {
        return;
    }
    const char* utf8 = env->GetStringUTFChars(code, nullptr);
    if (utf8 != nullptr) {
        RuntimeConfigFile::SetLanguage(utf8);
        env->ReleaseStringUTFChars(code, utf8);
    }
}

// GameActivity.nativeGraphicsInfo: the GPU the game is drawing with and whether the GPU
// compatibility fixes are on, as "<name>\n<1|0>"; empty until the renderer has started.
JNIEXPORT jstring JNICALL MKW_JNI(nativeGraphicsInfo)(JNIEnv* env, jclass)
{
    const std::string name = GraphicsInfo::Name();
    if (name.empty()) {
        return env->NewStringUTF("");
    }
    const std::string info = name + "\n" + (GraphicsInfo::CompatActive() ? "1" : "0");
    return env->NewStringUTF(info.c_str());
}

// GameActivity.nativeSetDeviceName: what this phone is called in room lists.
JNIEXPORT void JNICALL MKW_JNI(nativeSetDeviceName)(JNIEnv* env, jclass, jstring name)
{
    if (name == nullptr) {
        return;
    }
    const char* utf8 = env->GetStringUTFChars(name, nullptr);
    if (utf8 != nullptr) {
        Netplay::SetDeviceName(utf8);
        env->ReleaseStringUTFChars(name, utf8);
    }
}

// GameActivity.nativeSessionActive: whether this run is a LAN session (the menu offers to leave it).
JNIEXPORT jboolean JNICALL MKW_JNI(nativeSessionActive)(JNIEnv*, jclass)
{
    return NetplaySession::Active() ? JNI_TRUE : JNI_FALSE;
}

// GameActivity.nativePrepareToLeave: the menu's "Leave LAN game", before the app restarts the game.
JNIEXPORT void JNICALL MKW_JNI(nativePrepareToLeave)(JNIEnv*, jclass)
{
    NetplayStart::PrepareToLeave();
}

// GameActivity.nativeTap: a tap on the game's menus, as fractions of the screen (netplay_ui.h).
JNIEXPORT void JNICALL MKW_JNI(nativeTap)(JNIEnv*, jclass, jfloat x, jfloat y)
{
    NetplayUi::Tap(x, y);
}

// GameActivity.nativeTakeSettings: {render scale, show FPS 1/0, aspect, spinning coins 1/0, frame graph 1/0} when the game's settings
// window changed them since the last call, else null; the app saves them for the next start.
JNIEXPORT jfloatArray JNICALL MKW_JNI(nativeTakeSettings)(JNIEnv* env, jclass)
{
    float scale = 1.0f;
    bool showFps = false;
    int aspect = DisplaySettings::kAspectFill;
    bool spinningCoins = true;
    bool frameGraph = false;
    if (!NetplayUi::TakeSettingsChange(scale, showFps, aspect, spinningCoins, frameGraph)) {
        return nullptr;
    }
    jfloatArray result = env->NewFloatArray(5);
    const jfloat values[5] = {scale, showFps ? 1.0f : 0.0f, static_cast<jfloat>(aspect), spinningCoins ? 1.0f : 0.0f,
                              frameGraph ? 1.0f : 0.0f};
    env->SetFloatArrayRegion(result, 0, 5, values);
    return result;
}

// GameActivity.nativeTapScreen: whether a menu that taps drive is up (the app hides its remote).
JNIEXPORT jboolean JNICALL MKW_JNI(nativeTapScreen)(JNIEnv*, jclass)
{
    return NetplayUi::TapScreenUp() ? JNI_TRUE : JNI_FALSE;
}

} // extern "C"

#endif // __ANDROID__
