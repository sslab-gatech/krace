#ifndef _RACER_LTP_SAFE_OP_USER_H_
#define _RACER_LTP_SAFE_OP_USER_H_

#include "ltp_common.h"

LTP_OP_SAFE_SYS_DEF(
        setfsuid,
        ({
            syscall(SYS_setfsuid, uid);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "setfsuid(%d) failed",
                        uid);
            }
        }),
        void,
        uid_t, uid
)

LTP_OP_SAFE_SYS_DEF(
        setfsgid,
        ({
            syscall(SYS_setfsgid, gid);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "setfsgid(%d) failed",
                        gid);
            }
        }),
        void,
        gid_t, gid
)

LTP_OP_SAFE_SYS_DEF(
        setreuid,
        ({
            syscall(SYS_setreuid, ruid, euid);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "setreuid(%d, %d) failed",
                        ruid, euid);
            }
        }),
        void,
        uid_t, ruid, uid_t, euid
)

LTP_OP_SAFE_SYS_DEF(
        setregid,
        ({
            syscall(SYS_setregid, rgid, egid);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "setregid(%d, %d) failed",
                        rgid, egid);
            }
        }),
        void,
        gid_t, rgid, gid_t, egid
)

/*
 * Safe function to temporarily change uid/gid for filesystems operations
 */
LTP_OP_SAFE_LIB_DEC(
        set_fsrole,
        void,
        uid_t, uid, gid_t, gid
);

#endif /* _RACER_LTP_SAFE_OP_USER_H_ */
