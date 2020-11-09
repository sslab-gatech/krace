#ifndef _RACER_ANALYSIS_ORACLE_H_
#define _RACER_ANALYSIS_ORACLE_H_

#include "base/Common.h"

namespace racer {

    class FuncOracle {
    public:
        FuncOracle(Function &f, const DataLayout &dl, TargetLibraryInfo &tli)
                : ac(f), dt(f), li(dt), se(f, tli, ac, dt, li) {
            dt.verify();
            li.verify(dt);
        }

        ~FuncOracle() = default;

    public:
        // dominance
        bool dominates(BasicBlock *dom, BasicBlock *bb) {
            return dt.dominates(dom, bb);
        }

        BasicBlock *getIDom(BasicBlock *bb);

        // loop
        Loop *getOuterLoopInScope(Loop *scope, BasicBlock *bb);

        Loop *getInnerLoop(BasicBlock *bb) {
            return li.getLoopFor(bb);
        }

        Loop *getOuterLoop(BasicBlock *bb) {
            return getOuterLoopInScope(nullptr, bb);
        }

        // scala evolution
        SCEV *getSCEV(Value *v) {
            assert(se.isSCEVable(v->getType()));
            return const_cast<SCEV *>(se.getSCEV(v));
        }

    protected:
        // basics
        AssumptionCache ac;

        // analysis
        DominatorTree dt;
        LoopInfo li;
        ScalarEvolution se;
    };

    class ModuleOracle {
    public:
        explicit ModuleOracle(Module &m)
                : dl(m.getDataLayout()),
                  tli(TargetLibraryInfoImpl(
                          Triple(Twine(m.getTargetTriple())))) {

            // platform checks
            assert(dl.getPointerSizeInBits() == BITS * 8);
            assert(dl.isLittleEndian());

            // llvm checks
            assert(sizeof(hash_code) == 8);
        }

        ~ModuleOracle() = default;

    public:
        // data layout
        const DataLayout &getDataLayout() {
            return dl;
        }

        TargetLibraryInfo &getTargetLibraryInfo() {
            return tli;
        }

        unsigned getBits() {
            return BITS;
        }

        unsigned getPointerSize() {
            return dl.getPointerSize();
        }

        unsigned getPointerWidth() {
            return dl.getPointerSizeInBits();
        }

        unsigned getTypeAllocatedSize(Type *ty) {
            return (unsigned) dl.getTypeAllocSize(ty);
        }

        unsigned getTypeAllocatedWidth(Type *ty) {
            return (unsigned) dl.getTypeAllocSizeInBits(ty);
        }

        unsigned getTypeStoreSize(Type *ty) {
            return dl.getTypeStoreSize(ty);
        }

        unsigned getTypeStoreWidth(Type *ty) {
            return dl.getTypeStoreSizeInBits(ty);
        }

        bool isReintPointerType(Type *ty) {
            return ty->isPointerTy() ||
                   (ty->isIntegerTy() &&
                    ty->getIntegerBitWidth() == getPointerWidth());
        }

        // function oracles
        void addOracle(Function *f, FuncOracle *fo) {
            fos[f] = fo;
        }

        FuncOracle &getOracle(Function *f) {
            return *fos[f];
        }

        FuncOracle &getOracle(BasicBlock *b) {
            return getOracle(b->getParent());
        }

        FuncOracle &getOracle(Instruction *i) {
            return getOracle(i->getParent());
        }

        unsigned long numOracles() {
            return fos.size();
        }

    protected:
        // info provider
        const DataLayout &dl;
        TargetLibraryInfo tli;

        // function oracles
        map<Function *, FuncOracle *> fos;

        // consts
        const unsigned BITS = 8;
    };

} /* namespace racer */

#endif /* _RACER_ANALYSIS_ORACLE_H_ */
