#include "ltp.h"

LTP_OP_SAFE_LIB_DEC(
        set_fsrole,
        void,
        uid_t, uid, gid_t, gid
) {
    // NOTE: the order is important, re.id has to be set first before fs.id
    _safe_sys(setregid, gid, (gid_t) -1);
    _safe_sys(setreuid, uid, (uid_t) -1);

    _safe_sys(setfsgid, gid);
    _safe_sys(setfsuid, uid);
}