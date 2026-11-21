plugins {
    id("com.android.application")
}

// The region this APK is built for. CI sets these from the disc (see tools/android/build-region.py).
// Defaults: the USA disc, R8PE01 revision 0.
val spmGameId = System.getenv("SPM_GAME_ID") ?: "R8PE01"
val spmGameRevision = System.getenv("SPM_GAME_REVISION") ?: "0"
val spmDolSha = System.getenv("SPM_DOL_SHA") ?: "0d7487bc387ee1e905be335acc1e25300eb28bb8949667f753f038dbd9cf53b3"
// The runtime to build: USA (wiicompiled/runtime) or the PAL copy made for Europe (wiicompiled/pal/runtime).
val spmRuntimeCmake = System.getenv("SPM_RUNTIME_CMAKE") ?: "../../wiicompiled/runtime/CMakeLists.txt"
// Release signing. CI restores the keystore from the secret SPM_KEYSTORE_BASE64 to SPM_KEYSTORE_PATH, so every build
// has the same key and can update the one before it. Without it the APK is signed with the debug key.
val releaseKeystore = System.getenv("SPM_KEYSTORE_PATH")?.takeIf { it.isNotEmpty() }
// Profile-guided optimization (see runtime/CMakeLists.txt): "generate" builds an instrumented, debuggable APK that
// writes its profile to the app's files/pgo folder; "use" builds with SPM_PGO_PROFILE (a merged .profdata). Empty or
// "none" is the normal build.
val spmPgo = System.getenv("SPM_PGO")?.takeIf { it.isNotEmpty() && it != "none" } ?: ""
val spmPgoProfile = System.getenv("SPM_PGO_PROFILE") ?: ""

android {
    namespace = "com.superpapermario"
    compileSdk = 35
    // The NDK the runtime is tested with (tools/android/pipeline.py: "r29 tested").
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "com.superpapermario"
        resValue("string", "spm_game_id", spmGameId)
        resValue("string", "spm_game_revision", spmGameRevision)
        resValue("string", "spm_dol_sha", spmDolSha)
        // memfd_create (guest RAM) is in bionic from Android 11 on.
        minSdk = 30
        targetSdk = 35
        // One increasing number per CI run (SPM_VERSION_CODE = the run number), so an update always installs over the
        // previous build. Without it every build has the same code and Android may refuse a downgrade-looking install.
        versionCode = (System.getenv("SPM_VERSION_CODE") ?: "1").toInt()
        versionName = "1.0.${System.getenv("SPM_VERSION_CODE") ?: "0"}"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
        externalNativeBuild {
            cmake {
                // The same options as tools/android/pipeline.py (configure), plus the JNI package of this app.
                arguments += listOf(
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DBUILD_SHARED_LIBS=OFF",
                    "-DANDROID_STL=c++_static",
                    "-DMKW_ANDROID_ARCH=armv8-a",
                    "-DMKW_BUILD_LIBRETRO=OFF",
                    "-DSDL_AUDIO=ON",
                    "-DSDL_OPENGL=OFF",
                    "-DSDL_OPENGLES=OFF",
                    "-DAURORA_DAWN_PROVIDER=package",
                    "-DAURORA_DAWN_LINKAGE=static",
                    "-DAURORA_ENABLE_CARD=OFF",
                    "-DMKW_ANDROID_JNI_PACKAGE=com_superpapermario",
                    "-DMKW_TRANSLATED_COMPILE_JOBS=" + (System.getenv("SPM_JOBS") ?: "4"),
                )
                if (spmPgo.isNotEmpty()) {
                    arguments += "-DMKW_PGO=$spmPgo"
                    if (spmPgo == "use") {
                        arguments += "-DMKW_PGO_PROFILE=$spmPgoProfile"
                    }
                }
                if (System.getenv("SPM_CCACHE") == "1") {
                    arguments += listOf(
                        "-DCMAKE_C_COMPILER_LAUNCHER=ccache",
                        "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache",
                    )
                }
            }
        }
    }

    externalNativeBuild {
        cmake {
            // The runtime (and Aurora) build from the repo's wiicompiled/runtime folder.
            path = file(spmRuntimeCmake)
            version = "3.31.6"
        }
    }

    sourceSets {
        getByName("main") {
            // Runtime support files: DSP ROM, pipeline cache, Wii bootstrap NAND and the CA bundle.
            assets.srcDirs("../../wiicompiled/runtime/assets")
        }
    }

    lint {
        checkReleaseBuilds = false
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // A generate build must be debuggable so the profile can be pulled with run-as.
            isDebuggable = spmPgo == "generate"
            signingConfig = if (releaseKeystore != null) {
                signingConfigs.getByName("spm")
            } else {
                logger.warn("SPM_KEYSTORE_PATH no está definido: se firma con la clave debug, que no puede actualizar una instalación firmada con otra clave.")
                signingConfigs.getByName("debug")
            }
        }
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("spm") {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("SPM_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("SPM_KEY_ALIAS")
                keyPassword = System.getenv("SPM_KEY_PASSWORD")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
