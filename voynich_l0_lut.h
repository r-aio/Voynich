#ifndef VOYNICH_L0_LUT_H
#define VOYNICH_L0_LUT_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define L0_HARD_STOP_CODE (-999)

typedef enum {
    NODE_mCDU_PRIMARY_VALVE,
    NODE_HYPOCAUST_3WAY_VALVE,
    NODE_CALIBRATION_HUB,
    NODE_THERMAL_PUMP,
    NODE_REFLUX_CONDENSER,
    NODE_FURNACE_AIR_DAMPER,
    NODE_CHECK_VALVE,
    NODE_HYDRAULIC_ACCUM,
    NODE_CHEM_BUFFER_DOSER,
    NODE_PHASE_SEPARATOR,
    NODE_SAFETY_RELIEF_VALVE,
    NODE_SYSTEM_MASTER_KEY,
    NODE_EMERGENCY_SHUTDOWN
} HardwareNode_t;

typedef struct {
    const char*    eva_word;
    HardwareNode_t target_node;
    int16_t        state_delta;
    uint8_t        valve_position_pct;
} VoynichLUT_Entry_t;

static const VoynichLUT_Entry_t VOYNICH_FULL_LUT[] = {
    {"qokain",   NODE_mCDU_PRIMARY_VALVE,     1,  11},
    {"qokaiin",  NODE_mCDU_PRIMARY_VALVE,     2,  22},
    {"qokaiiin", NODE_mCDU_PRIMARY_VALVE,     3,  33},
    {"qotain",   NODE_HYPOCAUST_3WAY_VALVE,   1,  11},
    {"qotaiin",  NODE_HYPOCAUST_3WAY_VALVE,   2,  22},
    {"qotaiiin", NODE_HYPOCAUST_3WAY_VALVE,   3,  33},
    {"qoko",     NODE_CALIBRATION_HUB,        0,   0},
    {"tede",     NODE_THERMAL_PUMP,           0,  50},
    {"ol",       NODE_CALIBRATION_HUB,        0,   0},
    {"or",       NODE_REFLUX_CONDENSER,       0,  15},
    {"daim",     NODE_FURNACE_AIR_DAMPER,    -1,  40},
    {"dair",     NODE_FURNACE_AIR_DAMPER,     1,  60},
    {"shol",     NODE_CHECK_VALVE,            0,   0},
    {"kedy",     NODE_HYDRAULIC_ACCUM,        1,  75},
    {"chey",     NODE_CHEM_BUFFER_DOSER,      0,  10},
    {"qokey",    NODE_PHASE_SEPARATOR,        0,   0},
    {"fachys",   NODE_SAFETY_RELIEF_VALVE,    8,  90},
    {"qokaiiii", NODE_EMERGENCY_SHUTDOWN, L0_HARD_STOP_CODE, 0},
    {"soix",     NODE_SYSTEM_MASTER_KEY,      0, 100}
};

static inline VoynichLUT_Entry_t voynich_decode_frame(const char* eva_word) {
    const size_t n = sizeof(VOYNICH_FULL_LUT) / sizeof(VOYNICH_FULL_LUT[0]);
    if (eva_word != NULL) {
        for (size_t i = 0; i < n; ++i) {
            if (strcmp(eva_word, VOYNICH_FULL_LUT[i].eva_word) == 0) {
                return VOYNICH_FULL_LUT[i];
            }
        }
    }
    VoynichLUT_Entry_t fail_safe = {"UNKNOWN", NODE_EMERGENCY_SHUTDOWN, L0_HARD_STOP_CODE, 0};
    return fail_safe;
}

#endif /* VOYNICH_L0_LUT_H */
