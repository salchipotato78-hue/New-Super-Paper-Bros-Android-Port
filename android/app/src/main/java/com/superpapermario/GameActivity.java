package com.superpapermario;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.view.Choreographer;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Bundle;
import android.os.Process;
import android.view.Gravity;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.IOException;

import org.libsdl.app.SDLActivity;

/**
 * Hosts libmain.so (the Super Paper Mario runtime) through SDL's Android activity and draws the
 * touch remote on top of it.
 */
public class GameActivity extends SDLActivity {

    // libmain.so holds the runtime and the JNI functions below. Load it before any native call.
    static {
        System.loadLibrary("main");
    }

    // [video] aspect_mode in Config.toml (runtime/include/display_settings.h).
    static final int ASPECT_4X3 = 0;
    static final int ASPECT_16X9 = 1;
    static final int ASPECT_FILL = 2;   // ultrawide: fills the screen, the game is not stretched

    // Implemented in runtime/src/android/android_bridge.cpp.
    public static native void nativeSetTouchState(int buttons, boolean shake, float tilt);
    public static native void nativeApplyDisplaySettings(int aspect, float renderScale, boolean showFps);
    public static native void nativeReportThermalHeadroom(float headroom);
    public static native void nativeSetDisplayClock(long vblankNanos, double hz);
    public static native void nativeApplyGraphicsSettings(boolean interp120, boolean vsync, boolean disableCopyFilter);
    public static native int nativeGraphicsSettings();
    public static native int nativeGameLanguage();
    public static native void nativeSetGameLanguage(String code);
    public static native void nativeSetTouchPointer(float x, float y, int width, int height, boolean down);

    /**
     * SDLActivity loads only "SDL3" by default. SDL3 is linked statically into libmain.so, so the
     * runtime library is the only one to load.
     */
    @Override
    protected String[] getLibraries() {
        return new String[] {"main"};
    }

    private TouchOverlay overlay;
    private int aspect = ASPECT_FILL;
    private float renderScale;   // 0 = match the screen
    private boolean showFps;
    // Graphics menu: the runtime keeps these in Config.toml; read back once the native library is loaded.
    private boolean interp120;
    private boolean vsync = true;
    private boolean disableCopyFilter = true;

    /** Opens the picker for the game data (SetupActivity) and ends this game process. */
    public void chooseGameData() {
        Intent setup = new Intent(this, SetupActivity.class);
        setup.putExtra(SetupActivity.EXTRA_CHOOSE, true);
        setup.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(setup);
        finish();
        Process.killProcess(Process.myPid());
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        if (!SetupActivity.dataReady(this)) {
            startActivity(new Intent(this, SetupActivity.class));
            finish();
            return;
        }
        SetupActivity.touchStartMarker(this);

        // Ultrawide without stretching is the default. Written once, so the runtime reads it at boot too.
        if (setting("video", "aspect_mode") == null) {
            writeSetting("aspect_mode", String.valueOf(ASPECT_FILL));
        }
        aspect = readInt("video", "aspect_mode", ASPECT_FILL);
        renderScale = readFloat("video", "resolution_multiplier", 0f);
        showFps = readBool("video", "show_fps", false);

        super.onCreate(savedInstanceState);

        // After super.onCreate(): the decor view is attached only once SDLActivity sets up the content.
        hideSystemBars();
        nativeApplyDisplaySettings(aspect, renderScale, showFps);
        int graphics = nativeGraphicsSettings();
        interp120 = (graphics & 1) != 0;
        vsync = (graphics & 2) != 0;
        disableCopyFilter = (graphics & 4) != 0;

        overlay = new TouchOverlay(this);
        addContentView(overlay, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        addContentView(overlay.createPanel(), new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.CENTER_HORIZONTAL));
    }

    /** The next format in the menu: fill, 16:9, 4:3 and back. */
    int nextAspect() {
        if (aspect == ASPECT_FILL) {
            return ASPECT_16X9;
        }
        if (aspect == ASPECT_16X9) {
            return ASPECT_4X3;
        }
        return ASPECT_FILL;
    }

    /** Changes the picture format now (where the runtime allows it) and saves it for the next start. */
    void setAspect(int mode) {
        aspect = mode;
        writeSetting("aspect_mode", String.valueOf(mode));
        nativeApplyDisplaySettings(aspect, renderScale, showFps);
        if (mode == ASPECT_4X3) {
            Toast.makeText(this, "4:3 se aplica al reiniciar el juego", Toast.LENGTH_LONG).show();
        }
    }

    int aspect() {
        return aspect;
    }

    /** Applies and saves the Graphics menu (120 fps interpolation, V-Sync, copy filter). */
    void setGraphics(boolean interp, boolean sync, boolean noCopyFilter) {
        interp120 = interp;
        vsync = sync;
        disableCopyFilter = noCopyFilter;
        nativeApplyGraphicsSettings(interp120, vsync, disableCopyFilter);
    }

    // Game language (PAL disc only; the USA disc has English only). Codes in the order of the SC codes 1..5.
    static final String[] LANG_CODES = {"en", "de", "fr", "es", "it"};
    static final String[] LANG_NAMES = {"English", "Deutsch", "Français", "Español", "Italiano"};

    /** Index into LANG_CODES of the language the game uses now. */
    int gameLanguage() {
        return Math.max(0, Math.min(LANG_CODES.length - 1, nativeGameLanguage() - 1));
    }

    /** Next language in the menu; saved now, applied at the next start. */
    void cycleGameLanguage() {
        int next = (gameLanguage() + 1) % LANG_CODES.length;
        nativeSetGameLanguage(LANG_CODES[next]);
        Toast.makeText(this, "Idioma del juego: se aplica al reiniciar", Toast.LENGTH_LONG).show();
    }

    boolean interp120() { return interp120; }
    boolean vsync() { return vsync; }
    boolean disableCopyFilter() { return disableCopyFilter; }

    private String setting(String section, String key) {
        try {
            return DataImporter.readSetting(SetupActivity.configFile(this), section, key);
        } catch (IOException e) {
            return null;
        }
    }

    private void writeSetting(String key, String value) {
        try {
            DataImporter.writeSetting(SetupActivity.configFile(this), "video", key, value);
        } catch (IOException e) {
            Toast.makeText(this, "No se pudo guardar: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private int readInt(String section, String key, int def) {
        String v = setting(section, key);
        if (v == null) {
            return def;
        }
        try {
            return Integer.parseInt(v.trim());
        } catch (NumberFormatException e) {
            return def;
        }
    }

    private float readFloat(String section, String key, float def) {
        String v = setting(section, key);
        if (v == null) {
            return def;
        }
        try {
            return Float.parseFloat(v.trim());
        } catch (NumberFormatException e) {
            return def;
        }
    }

    private boolean readBool(String section, String key, boolean def) {
        String v = setting(section, key);
        return v == null ? def : v.trim().equals("true");
    }

    // The game clock follows the screen: every display frame's vblank time goes to the runtime (Choreographer), so
    // frames are timed to the real vblanks instead of a free-running 60 Hz timer. Stopped while the app is paused.
    private Choreographer.FrameCallback displayClock;
    private boolean displayClockOn;
    // True while a frame callback is queued. Keeps a quick pause and resume from queuing a second chain, which would
    // call nativeSetDisplayClock twice per frame.
    private boolean displayClockPending;

    private void startDisplayClock() {
        displayClockOn = true;
        if (displayClock == null) {
            displayClock = new Choreographer.FrameCallback() {
                @Override
                public void doFrame(long frameTimeNanos) {
                    displayClockPending = false;
                    if (!displayClockOn) {
                        return;
                    }
                    double hz = getWindowManager().getDefaultDisplay().getRefreshRate();
                    nativeSetDisplayClock(frameTimeNanos, hz);
                    displayClockPending = true;
                    Choreographer.getInstance().postFrameCallback(this);
                }
            };
        }
        if (!displayClockPending) {
            displayClockPending = true;
            Choreographer.getInstance().postFrameCallback(displayClock);
        }
    }

    private void stopDisplayClock() {
        displayClockOn = false;
    }

    // Thermal headroom (Android 12+) forwarded to the runtime about once a second: when the phone is close to
    // throttling, the runtime renders fewer pixels instead of letting the frame rate fall (runtime/src/thermal_quality.cpp).
    private static final long THERMAL_POLL_MS = 1000;
    private final Handler thermalHandler = new Handler(Looper.getMainLooper());
    private final Runnable thermalPoll = new Runnable() {
        @Override
        public void run() {
            if (Build.VERSION.SDK_INT >= 31) {
                PowerManager power = (PowerManager) getSystemService(Context.POWER_SERVICE);
                // NaN when the device cannot forecast; the runtime then leaves the quality alone.
                nativeReportThermalHeadroom(power.getThermalHeadroom(10));
            }
            thermalHandler.postDelayed(this, THERMAL_POLL_MS);
        }
    };

    @Override
    protected void onResume() {
        super.onResume();
        startDisplayClock();
        thermalHandler.removeCallbacks(thermalPoll);
        thermalHandler.post(thermalPoll);
    }

    @Override
    protected void onPause() {
        // Never leave a button held while the game is in the background.
        if (overlay != null) {
            overlay.releaseAll();
        }
        thermalHandler.removeCallbacks(thermalPoll);
        stopDisplayClock();
        super.onPause();
    }

    /** Full-screen game: hides the status bar and the navigation buttons until the player swipes. */
    private void hideSystemBars() {
        View decor = getWindow().getDecorView();
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController controller = decor.getWindowInsetsController();
            if (controller != null) {
                controller.hide(WindowInsets.Type.systemBars());
                controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_BARS_BY_SWIPE);
            }
        } else {
            decor.setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }
}
