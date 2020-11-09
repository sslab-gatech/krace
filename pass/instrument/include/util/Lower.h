#ifndef _RACER_UTIL_LOWER_H_
#define _RACER_UTIL_LOWER_H_

#include "base/Common.h"

namespace racer {

    class Lowering {
    public:
        // checks
        static void checkAssumptions(Module &m);

        // load file
        static bool findInSourceLine(const char *target, const DebugLoc &loc);
    };

} /* namespace racer */

#endif /* _RACER_UTIL_LOWER_H_ */
