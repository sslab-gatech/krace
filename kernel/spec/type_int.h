#ifndef _RACER_SPEC_TYPE_INT_H_
#define _RACER_SPEC_TYPE_INT_H_

#include "common.h"

namespace spec {

template<typename I>
BEAN(RandInt, Rand,
     I, data)
};

template<typename I>
BEAN(TypeInt, Type<RandInt<I>>)

public:
    optional<size_t> size() const override {
        return sizeof(I);
    }

    void mutate(Program &prog) const override {
        prog.lego(*this);
    }
};

} // spec namespace

#endif /* _RACER_SPEC_TYPE_INT_H_ */
