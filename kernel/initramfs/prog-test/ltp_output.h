#ifndef _RACER_LTP_OUTPUT_H_
#define _RACER_LTP_OUTPUT_H_

#include "ltp_common.h"

// ltp result flags
#define TPASS 0x0   // test passed
#define TWARN 0x1   // test warned, passed with concerns
#define TFAIL 0x2   // test failed, assertion not true
#define TBROK 0x4   // test broken, prerequisites not met or failed
#define TCONF 0x8   // test ignore, configuration not appropriate

// ltp result interpretation
#define _LTP_RES_MASK           0x0F

#define LTP_RV_GET_RES(rv)      ((rv) & _LTP_RES_MASK)
#define LTP_RV_GET_ERR(rv)      ((rv) >> 4)
#define LTP_RV_MERGE(res, err)  (((int) (-(err))) << 4 | (res))

// ltp result to string
static inline char *ltp_rv_get_res_str(int rv) {
    switch (LTP_RV_GET_RES(rv)) {
        case TPASS:
            return "PASS";
        case TWARN:
            return "WARN";
        case TFAIL:
            return "FAIL";
        case TBROK:
            return "BROK";
        case TCONF:
            return "CONF";
        default:
            return "ABRT";
    }
}

// ltp finish with result
void _ltp_ret(_LTP_OP_ARGS_DEF_,
              int rv,
              const char *fmt, ...);

#define ltp_ret(rv, fmt, ...) \
        _ltp_ret(_LTP_OP_ARGS_USE_, (rv), (fmt), ##__VA_ARGS__)

#endif /* _RACER_LTP_OUTPUT_H_ */
