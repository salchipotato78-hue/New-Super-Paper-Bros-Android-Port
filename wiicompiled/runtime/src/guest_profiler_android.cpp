// SPM Android: the sampling profiler for the game thread (the Windows one is guest_profiler.cpp).
//
// Activation: SPM_PROFILE=<start s>:<length s> in the environment, or a profile.txt with the same text in the app's
// data folder. The clock starts at the first presented frame. Samples are taken from ITIMER_PROF, so they count CPU
// time only: a frame that waits for vblank adds nothing, and the report measures exactly the game-thread work that
// limits the frame rate. Each sample is the interrupted program counter, mapped to the translated guest function it
// falls in, or to exe+RVA (runtime code) or [module] (system code).
#include "abi_bridge.h"
#include "guest_profiler.h"
#include "runtime_config.h"
#include "runtime_log.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <dlfcn.h>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/syscall.h>
#include <sys/time.h>
#include <thread>
#include <ucontext.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

extern "C" {
extern const uint32_t kGuestMapSymbolCount;
extern const uint32_t kGuestMapSymbolAddresses[];
extern const char* const kGuestMapSymbolNames[];
}

namespace GuestProfiler {
namespace {

constexpr uint32_t kMaxSamples = 1u << 20;  // ~17 minutes at 1 kHz; more than the window ever needs

uintptr_t* g_samples = nullptr;
std::atomic<uint32_t> g_sampleCount{0};
std::atomic<pid_t> g_gameTid{0};
std::atomic<bool> g_sampling{false};
std::atomic<bool> g_done{false};

// Runs in signal context: only atomics and a store into a preallocated array.
void OnSigprof(int, siginfo_t*, void* context) {
    if (!g_sampling.load(std::memory_order_relaxed)) {
        return;
    }
    if (static_cast<pid_t>(syscall(SYS_gettid)) != g_gameTid.load(std::memory_order_relaxed)) {
        return;  // only the game thread is sampled; the others are not what limits the frame rate
    }
    const auto* uc = static_cast<const ucontext_t*>(context);
    uintptr_t pc = 0;
#if defined(__aarch64__)
    pc = static_cast<uintptr_t>(uc->uc_mcontext.pc);
#elif defined(__arm__)
    pc = static_cast<uintptr_t>(uc->uc_mcontext.arm_pc);
#endif
    const uint32_t i = g_sampleCount.fetch_add(1, std::memory_order_relaxed);
    if (i < kMaxSamples && g_samples != nullptr) {
        g_samples[i] = pc;
    }
}

struct Entry {
    uintptr_t host;
    uint32_t guest;
};

const char* GuestName(uint32_t address) {
    const uint32_t* begin = kGuestMapSymbolAddresses;
    const uint32_t* end = kGuestMapSymbolAddresses + kGuestMapSymbolCount;
    const uint32_t* it = std::lower_bound(begin, end, address);
    return it != end && *it == address ? kGuestMapSymbolNames[it - begin] : "";
}

// The shared object holding the runtime and the translated code, from /proc/self/maps: its lowest and highest address.
bool ExecutableRange(uintptr_t inside, uintptr_t& lo, uintptr_t& hi) {
    Dl_info info{};
    if (!dladdr(reinterpret_cast<void*>(inside), &info) || info.dli_fname == nullptr) {
        return false;
    }
    const std::string path = info.dli_fname;
    std::ifstream maps("/proc/self/maps");
    std::string line;
    bool found = false;
    lo = ~uintptr_t{0};
    hi = 0;
    while (std::getline(maps, line)) {
        if (line.size() < path.size() || line.compare(line.size() - path.size(), path.size(), path) != 0) {
            continue;
        }
        uintptr_t start = 0, end = 0;
        if (std::sscanf(line.c_str(), "%lx-%lx", &start, &end) == 2) {
            lo = std::min(lo, start);
            hi = std::max(hi, end);
            found = true;
        }
    }
    return found;
}

std::string ModuleName(uintptr_t pc) {
    Dl_info info{};
    if (dladdr(reinterpret_cast<void*>(pc), &info) && info.dli_fname != nullptr) {
        const char* slash = std::strrchr(info.dli_fname, '/');
        return std::string("[") + (slash ? slash + 1 : info.dli_fname) + "]";
    }
    return "[?]";
}

void Report(std::vector<uintptr_t> samples) {
    // Every translated function's host entry point, sorted, to find which one a sample falls in. Same guest ranges
    // as the Windows profiler (SPM main.dol text and the relF text).
    std::vector<Entry> entries;
    for (const auto& [lo, hi] : {std::pair{0x80004000u, 0x80319180u}, std::pair{0x80BF691Cu, 0x80C5A648u}}) {
        for (uint32_t address = lo; address < hi; address += 4) {
            if (const TranslatedFunctionInfo* info = TranslatedFunctionRegistry::FindByAddressPtr(address);
                info != nullptr && info->entryPoint != nullptr && info->address == address) {
                entries.push_back({reinterpret_cast<uintptr_t>(info->entryPoint), address});
            }
        }
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& a, const Entry& b) { return a.host < b.host; });

    uintptr_t exeBase = 0, exeEnd = 0;
    const bool haveExe = ExecutableRange(reinterpret_cast<uintptr_t>(&Report), exeBase, exeEnd);

    std::unordered_map<uintptr_t, uint32_t> counts;
    for (const uintptr_t pc : samples) {
        ++counts[pc];
    }

    const auto total = static_cast<uint32_t>(samples.size());
    std::unordered_map<std::string, uint32_t> byName;
    for (const auto& [pc, count] : counts) {
        std::string key;
        if (haveExe && pc >= exeBase && pc < exeEnd) {
            auto it = std::upper_bound(entries.begin(), entries.end(), pc,
                                       [](uintptr_t value, const Entry& e) { return value < e.host; });
            if (it != entries.begin() && it != entries.end()) {
                --it;
                char text[160];
                std::snprintf(text, sizeof(text), "%08X %s", it->guest, GuestName(it->guest));
                key = text;
            } else {
                char text[48];
                std::snprintf(text, sizeof(text), "exe+%lX (runtime code)", static_cast<unsigned long>(pc - exeBase));
                key = text;
            }
        } else {
            key = ModuleName(pc);
        }
        byName[key] += count;
    }

    std::vector<std::pair<std::string, uint32_t>> sorted(byName.begin(), byName.end());
    std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
    RT_LOGF(RT_TAG_RUNTIME, "profile: %u samples (game thread CPU), %zu translated functions\n", total,
            entries.size());
    for (size_t i = 0; i < sorted.size() && i < 60; ++i) {
        RT_LOGF(RT_TAG_RUNTIME, "profile: %5.1f%%  %s\n", total ? 100.0 * sorted[i].second / total : 0.0,
                sorted[i].first.c_str());
    }
}

// SPM_PROFILE from the environment, else profile.txt in the app data folder. Empty when there is none.
std::string ProfileSetting() {
    if (const char* env = std::getenv("SPM_PROFILE"); env && *env) {
        return env;
    }
    std::ifstream file(RuntimeConfigFile::ApplicationDataDirectory() / "profile.txt");
    std::string value;
    if (file) {
        std::getline(file, value);
    }
    return value;
}

}  // namespace

// Called from the game thread at each presented frame (guest_profiler.cpp dispatches here on Android).
void AndroidOnFramePresented() {
    static bool parsed = false;
    static bool active = false;
    static double startS = 0, lengthS = 0;
    static std::chrono::steady_clock::time_point firstFrame{};
    static pid_t gameTid = 0;
    if (!parsed) {
        parsed = true;
        firstFrame = std::chrono::steady_clock::now();
        gameTid = static_cast<pid_t>(syscall(SYS_gettid));
        const std::string setting = ProfileSetting();
        if (std::sscanf(setting.c_str(), "%lf:%lf", &startS, &lengthS) == 2 && lengthS > 0) {
            active = true;
            g_gameTid.store(gameTid, std::memory_order_relaxed);
            RT_LOGF(RT_TAG_RUNTIME, "profile: will sample the game thread from %.0f s for %.0f s\n", startS, lengthS);
        }
    }
    if (!active || g_done.load(std::memory_order_relaxed)) {
        return;
    }

    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - firstFrame).count();
    if (!g_sampling.load(std::memory_order_relaxed) && elapsed >= startS) {
        g_samples = new uintptr_t[kMaxSamples];
        struct sigaction action {};
        action.sa_sigaction = &OnSigprof;
        action.sa_flags = SA_SIGINFO | SA_RESTART;
        sigemptyset(&action.sa_mask);
        sigaction(SIGPROF, &action, nullptr);
        itimerval timer{};
        timer.it_interval.tv_usec = 1000;  // 1 kHz of CPU time
        timer.it_value.tv_usec = 1000;
        g_sampling.store(true, std::memory_order_relaxed);
        setitimer(ITIMER_PROF, &timer, nullptr);
        RT_LOGF(RT_TAG_RUNTIME, "profile: sampling started\n");
        return;
    }
    if (g_sampling.load(std::memory_order_relaxed) && elapsed >= startS + lengthS) {
        itimerval off{};
        setitimer(ITIMER_PROF, &off, nullptr);
        g_sampling.store(false, std::memory_order_relaxed);
        g_done.store(true, std::memory_order_relaxed);
        const uint32_t taken = std::min(g_sampleCount.load(std::memory_order_relaxed), kMaxSamples);
        std::vector<uintptr_t> samples(g_samples, g_samples + taken);
        delete[] g_samples;
        g_samples = nullptr;
        // The report walks every translated function: run it off the game thread.
        std::thread(Report, std::move(samples)).detach();
    }
}

}  // namespace GuestProfiler
