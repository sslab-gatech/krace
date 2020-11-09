#include "ltp.h"

static void print_result(_LTP_OP_ARGS_DEF_,
                         int rv,
                         const char *fmt, va_list va) {

    // string for res
    const char *res;
    switch (LTP_RV_GET_RES(rv)) {
        case TPASS:
            res = "PASS";
            break;
        case TWARN:
            res = "WARN";
            break;
        case TFAIL:
            res = "FAIL";
            break;
        case TBROK:
            res = "BROK";
            break;
        case TCONF:
            res = "CONF";
            break;
        default:
            fprintf(stderr,
                    "[ABRT] " _LTP_OP_ARGS_FMT_ " - invalid result: %d\n",
                    _LTP_OP_ARGS_USE_, rv);
            abort();
    }

    // string for err
    int eno = LTP_RV_GET_ERR(rv);
    const char *err = eno ? strerror(eno) : "OK";

    // string for message
    char *msg;
    if (vasprintf(&msg, fmt, va) < 0) {
        fprintf(stderr,
                "[ABRT] " _LTP_OP_ARGS_FMT_ " - unable to build message: %d\n",
                _LTP_OP_ARGS_USE_, errno);
        abort();
    }

    // construct the message
    char buf[1024];
    if (snprintf(buf, sizeof(buf),
                 "[%s] " _LTP_OP_ARGS_FMT_ " (%d) - %s: %s\n",
                 res, _LTP_OP_ARGS_USE_, eno, err, msg) < 0) {

        fprintf(stderr,
                "[ABRT] " _LTP_OP_ARGS_FMT_ " - unable to build result: %d\n",
                _LTP_OP_ARGS_USE_, errno);
        abort();
    }

    // output
    fputs(buf, stderr);

    // clean up
    free(msg);
}

void _ltp_ret(_LTP_OP_ARGS_DEF_,
              int rv,
              const char *fmt, ...) {

    // show results
    va_list va;

    va_start(va, fmt);
    print_result(_LTP_OP_ARGS_USE_, rv, fmt, va);
    va_end(va);

    // finish
    exit((rv & ~(0x1)) ? EXIT_FAILURE : EXIT_SUCCESS);
}