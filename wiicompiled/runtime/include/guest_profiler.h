#pragma once

// NSMBW_PROFILE=<start s>:<length s>: sample the game thread and log where its time goes, by
// translated guest function (guest_profiler.cpp on Windows, guest_profiler_android.cpp on Android).
namespace GuestProfiler {
// From the thread that presents frames, at each present: the first call starts the sampler.
void OnFramePresented();
#if defined(__ANDROID__)
// Android sampler (guest_profiler_android.cpp); OnFramePresented forwards to it.
void AndroidOnFramePresented();
#endif
} // namespace GuestProfiler
