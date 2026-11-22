#ifndef VOYNICH_L0_LUT_H
#define VOYNICH_L0_LUT_H

/*
 * L0-ISM Deterministic Zero-Heap C99 ROM Look-Up Table
 * Target: Safety-critical embedded execution (O(1) bounded lookup, SIL-4 fail-safe).
 * Synchronized with Layer 1 Exact LUT in voynich_ivtff_auditor.py.
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* 19-state discrete symmetric axis S = {-9, ..., 0, ..., +9} and absorbing barrier code */
#define L0_STATE_MIN       (-9)
#define L0_STATE_FULCRUM   (0)
#define L0_STATE_MAX       (+9)
#define L0_HARD_STOP_CODE  (-999)

typedef enum {
    NODE_PRIMARY_COOLING,
    NODE_HYPOCAUST_3WAY_VALVE,
    NODE_CALIBRATION_HUB,
    NODE_THERMAL_PUMP,
    NODE_REFLUX_CONDENSER,
    NODE_CONDENSATE_TRAP,
    NODE_LEVEL_SIGHT_GLASS,
    NODE_FLOAT_AIR_VENT,
    NODE_FURNACE_AIR_DAMPER,
    NODE_CHECK_VALVE,
    NODE_HYDRAULIC_ACCUM,
    NODE_CHEM_BUFFER_DOSER,
    NODE_BAIN_MARIE_JACKET,
    NODE_PHASE_SEPARATOR,
    NODE_OVERFLOW_HEADER,
    NODE_THERMAL_EXP_BELLOWS,
    NODE_TRICKLE_COOLER,
    NODE_STATIC_MIXER,
    NODE_SAFETY_RELIEF_VALVE,
    NODE_EMERGENCY_SHUTDOWN
} HardwareNode_t;

typedef enum {
    CMD_SET_WATER_GRADIENT,
    CMD_SET_STEAM_GRADIENT,
    CMD_CALIBRATE_ZERO,
    CMD_APPLY_RESO,
    CMD_CONFIRM_SAT,
    CMD_DRAIN_CONDENSATE,
    CMD_READ_LEVEL,
    CMD_BLEED_AIR,
    CMD_SET_DAMPER_GRADIENT,
    CMD_CLOSE_CHECK_VALVE,
    CMD_DOSE_BUFFER,
    CMD_HOLD_BATH_TEMP,
    CMD_FLUSH_SEDIMENT,
    CMD_BUFFER_PRESSURE,
    CMD_ABSORB_ELONGATION,
    CMD_EVAP_COOLING,
    CMD_EQUALIZE_STRATA,
    CMD_PREPARE_CRIT_RELIEF,
    CMD_HARD_STOP
} ControlCommand_t;

typedef struct {
    const char*      eva_word;
    HardwareNode_t   target_node;
    ControlCommand_t command;
    int16_t          state_delta;        /* Quantized offset [-9, +9] or -999 HARD_STOP */
    uint8_t          valve_position_pct; /* Actuator position 0-100% */
} VoynichLUT_Entry_t;

static const VoynichLUT_Entry_t VOYNICH_FULL_LUT[] = {
    /* Primary liquid cooling manifold (k-core) */
    {"qokain",   NODE_PRIMARY_COOLING,      CMD_SET_WATER_GRADIENT,  +1, 11},
    {"qokaiin",  NODE_PRIMARY_COOLING,      CMD_SET_WATER_GRADIENT,  +2, 22},
    {"qokaiiin", NODE_PRIMARY_COOLING,      CMD_SET_WATER_GRADIENT,  +3, 33},
    {"qokedy",   NODE_PRIMARY_COOLING,      CMD_APPLY_RESO,           0, 25},
    {"qokeedy",  NODE_PRIMARY_COOLING,      CMD_APPLY_RESO,           0, 50},

    /* Hypocaustum 3-way steam/air diverter (k -> t core switch) */
    {"qotain",   NODE_HYPOCAUST_3WAY_VALVE, CMD_SET_STEAM_GRADIENT,  +1, 11},
    {"qotaiin",  NODE_HYPOCAUST_3WAY_VALVE, CMD_SET_STEAM_GRADIENT,  +2, 22},
    {"qotaiiin", NODE_HYPOCAUST_3WAY_VALVE, CMD_SET_STEAM_GRADIENT,  +3, 33},

    /* Calibration, thermal resonance, and SAT balance confirmation */
    {"qoko",     NODE_CALIBRATION_HUB,      CMD_CALIBRATE_ZERO,       0,  0},
    {"oteedy",   NODE_THERMAL_PUMP,         CMD_APPLY_RESO,           0, 50},
    {"qoteedy",  NODE_THERMAL_PUMP,         CMD_APPLY_RESO,           0, 50},
    {"ol",       NODE_CALIBRATION_HUB,      CMD_CONFIRM_SAT,          0,  0},
    {"or",       NODE_REFLUX_CONDENSER,     CMD_CONFIRM_SAT,          0, 15},
    {"ar",       NODE_CONDENSATE_TRAP,      CMD_DRAIN_CONDENSATE,     0, 10},

    /* Sight glass level gauges and float-type air vents */
    {"dain",     NODE_LEVEL_SIGHT_GLASS,    CMD_READ_LEVEL,           0,  0},
    {"daiin",    NODE_LEVEL_SIGHT_GLASS,    CMD_READ_LEVEL,           0,  0},
    {"al",       NODE_FLOAT_AIR_VENT,       CMD_BLEED_AIR,            0,  0},
    {"sol",      NODE_FLOAT_AIR_VENT,       CMD_BLEED_AIR,            0,  0},

    /* Hypocaust furnace damper, check valves, and hydraulic accumulator */
    {"daim",     NODE_FURNACE_AIR_DAMPER,   CMD_SET_DAMPER_GRADIENT, -1, 40},
    {"dair",     NODE_FURNACE_AIR_DAMPER,   CMD_SET_DAMPER_GRADIENT, +1, 60},
    {"shol",     NODE_CHECK_VALVE,          CMD_CLOSE_CHECK_VALVE,    0,  0},
    {"shor",     NODE_CHECK_VALVE,          CMD_CLOSE_CHECK_VALVE,    0,  0},
    {"kedy",     NODE_HYDRAULIC_ACCUM,      CMD_APPLY_RESO,          +1, 75},
    {"shedy",    NODE_HYDRAULIC_ACCUM,      CMD_APPLY_RESO,           0, 75},

    /* Chemical anti-scale dosing, bain-marie jacket, and sediment flush */
    {"chey",     NODE_CHEM_BUFFER_DOSER,    CMD_DOSE_BUFFER,          0, 10},
    {"qochey",   NODE_CHEM_BUFFER_DOSER,    CMD_DOSE_BUFFER,          0, 20},
    {"chol",     NODE_BAIN_MARIE_JACKET,    CMD_HOLD_BATH_TEMP,       0, 50},
    {"qochol",   NODE_BAIN_MARIE_JACKET,    CMD_HOLD_BATH_TEMP,       0, 50},
    {"qokey",    NODE_PHASE_SEPARATOR,      CMD_FLUSH_SEDIMENT,       0,  0},
    {"am",       NODE_PHASE_SEPARATOR,      CMD_FLUSH_SEDIMENT,       0,  0},

    /* Header tank, thermal expansion bellows, trickle cooler, and swirl mixer */
    {"otain",    NODE_OVERFLOW_HEADER,      CMD_BUFFER_PRESSURE,      0, 20},
    {"otaiin",   NODE_OVERFLOW_HEADER,      CMD_BUFFER_PRESSURE,      0, 40},
    {"ckhaiin",  NODE_THERMAL_EXP_BELLOWS,  CMD_ABSORB_ELONGATION,    0,  0},
    {"shain",    NODE_TRICKLE_COOLER,       CMD_EVAP_COOLING,        -1, 30},
    {"shaiin",   NODE_TRICKLE_COOLER,       CMD_EVAP_COOLING,        -2, 60},
    {"cthy",     NODE_STATIC_MIXER,         CMD_EQUALIZE_STRATA,      0,  0},
    {"ckhy",     NODE_STATIC_MIXER,         CMD_EQUALIZE_STRATA,      0,  0},

    /* Safety relief arming and +/-9 barrier interdiction */
    {"fachys",   NODE_SAFETY_RELIEF_VALVE,  CMD_PREPARE_CRIT_RELIEF, +8, 90},
    {"qokaiiii", NODE_EMERGENCY_SHUTDOWN,   CMD_HARD_STOP, L0_HARD_STOP_CODE, 0}
};

/* Deterministic O(1) static ROM lookup with fail-safe HARD_STOP on unknown tokens */
static inline VoynichLUT_Entry_t voynich_decode_frame(const char* eva_word) {
    const size_t n = sizeof(VOYNICH_FULL_LUT) / sizeof(VOYNICH_FULL_LUT[0]);
    if (eva_word != NULL) {
        for (size_t i = 0; i < n; ++i) {
            if (strcmp(eva_word, VOYNICH_FULL_LUT[i].eva_word) == 0) {
                return VOYNICH_FULL_LUT[i];
            }
        }
    }
    VoynichLUT_Entry_t fail_safe = {
        "UNKNOWN", NODE_EMERGENCY_SHUTDOWN, CMD_HARD_STOP, L0_HARD_STOP_CODE, 0
    };
    return fail_safe;
}

#endif /* VOYNICH_L0_LUT_H */
