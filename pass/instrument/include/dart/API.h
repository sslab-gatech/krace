#ifndef _RACER_DART_API_H_
#define _RACER_DART_API_H_

#include "base/Common.h"
#include "apidef.inc"

namespace racer {

    class DartAPI {
    public:
        explicit DartAPI(Module &module)
                : ctxt(module.getContext()),
                // dart types
                  void_t(Type::getVoidTy(ctxt)),
                  info_64_t(Type::getInt64Ty(ctxt)),
                  hval_64_t(Type::getInt64Ty(ctxt)),
                  data_64_t(Type::getInt64Ty(ctxt)),
                // dart functions
#define DART_FUNC DART_FUNC_API_CONSTRUCT
#include "apidef.inc"
#undef DART_FUNC
                  end_of_fields(true) {
        }

        ~DartAPI() = default;

    protected:
        Value *prepIntOrPtr(IRBuilder<> &builder, Value *val) {
            Type *ty = val->getType();

            if (ty->isPointerTy()) {
                return builder.CreatePtrToInt(val, data_64_t);
            }

            assert(ty->isIntegerTy());
            unsigned bits = ty->getPrimitiveSizeInBits();

            if (bits < data_64_t->getPrimitiveSizeInBits()) {
                return builder.CreateZExt(val, data_64_t);
            }

            assert(bits == data_64_t->getPrimitiveSizeInBits());
            return val;
        }

        vector<Value *> prepDartArgs(IRBuilder<> &builder,
                                     flag_t flag, const hash_code &hval,
                                     initializer_list<Value *> data) {

            vector<Value *> vec;

            vec.push_back(ConstantInt::get(info_64_t, flag));
            vec.push_back(ConstantInt::get(hval_64_t, size_t(hval)));

            for (Value *v : data) {
                if (v != nullptr) {
                    vec.push_back(prepIntOrPtr(builder, v));
                }
            }

            return vec;
        }

    public:
        Value *createDataValue(int v) {
            return ConstantInt::get(data_64_t, v);
        }

        Value *createDataValue(unsigned int v) {
            return ConstantInt::get(data_64_t, v);
        }

        Value *createDataValue(long v) {
            return ConstantInt::get(data_64_t, v);
        }

        Value *createDataValue(unsigned long v) {
            return ConstantInt::get(data_64_t, v);
        }

    public:
        // dart hooks
#define DART_FUNC DART_FUNC_API_HOOK
#include "apidef.inc"
#undef DART_FUNC

    protected:
        // context
        LLVMContext &ctxt;

        // dart types
        Type *void_t;
        Type *info_64_t;
        Type *hval_64_t;
        Type *data_64_t;

        // dart functions
#define DART_FUNC DART_FUNC_API_DECLARE
#include "apidef.inc"
#undef DART_FUNC

        // dummy
        bool end_of_fields;
    };

} /* namespace racer */

#endif /* _RACER_DART_API_H_ */
