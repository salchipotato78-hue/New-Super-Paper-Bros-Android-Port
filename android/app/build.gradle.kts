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
        versionCode = 1
        versionName = "1.0.0"

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
            // Personal builds: signed with the debug key so the APK installs directly.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
