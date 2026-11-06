// Y306: set Orbbec Gemini 335Lg to hardware triggering mode (30/10 Hz FSYNC)
// Build: g++ -O2 -std=c++17 y306_orb_trigger.cpp -I/opt/orbbec-sdk/include \
//        -L/opt/orbbec-sdk/lib -lOrbbecSDK -Wl,-rpath,/opt/orbbec-sdk/lib -o y306_orb_trigger
#include <libobsensor/ObSensor.hpp>
#include <cstdio>
#include <cstring>
#include <cstdlib>

int main(int argc, char **argv)
{
    int frames_per_trigger = 1;
    bool apply = true;
    bool verbose = true;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames-per-trigger") && i + 1 < argc) frames_per_trigger = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--dry-run")) apply = false;
        else if (!strcmp(argv[i], "--quiet")) verbose = false;
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            printf("usage: %s [--frames-per-trigger N] [--dry-run] [--quiet]\n", argv[0]);
            return 0;
        }
    }
    try {
        ob::Context ctx;
        auto list = ctx.queryDeviceList();
        if (!list || list->getCount() == 0) {
            fprintf(stderr, "no Orbbec device found\n");
            return 2;
        }
        int rc = 0;
        for (uint32_t i = 0; i < list->getCount(); i++) {
            auto dev = list->getDevice(i);
            auto info = dev->getDeviceInfo();
            auto cfg = dev->getMultiDeviceSyncConfig();
            if (verbose)
                printf("%s sn=%s syncMode=0x%x framesPerTrigger=%d triggerOut=%d\n",
                       info->getName(), info->getSerialNumber(),
                       (unsigned)cfg.syncMode, cfg.framesPerTrigger, (int)cfg.triggerOutEnable);
            if (!apply) continue;
            cfg.syncMode = OB_MULTI_DEVICE_SYNC_MODE_HARDWARE_TRIGGERING;
            cfg.framesPerTrigger = frames_per_trigger;
            dev->setMultiDeviceSyncConfig(cfg);
            auto chk = dev->getMultiDeviceSyncConfig();
            if (verbose)
                printf("  -> set syncMode=0x%x framesPerTrigger=%d\n",
                       (unsigned)chk.syncMode, chk.framesPerTrigger);
            if (chk.syncMode != OB_MULTI_DEVICE_SYNC_MODE_HARDWARE_TRIGGERING ||
                chk.framesPerTrigger != frames_per_trigger) {
                fprintf(stderr, "  !! verification failed\n");
                rc = 3;
            }
        }
        return rc;
    } catch (ob::Error &e) {
        fprintf(stderr, "orbbec error: %s\n", e.getMessage());
        return 1;
    } catch (std::exception &e) {
        fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }
}
