#ifndef _RACER_BASE_PLUGIN_H_
#define _RACER_BASE_PLUGIN_H_

#include "base/Common.h"
#include "analysis/Oracle.h"
#include "analysis/Probe.h"
#include "dart/API.h"
#include "util/Logger.h"

// main namespace
namespace racer {

    // pass
    class Racer : public ModulePass {
    public:
        Racer(const string &_mode, const string &_input, const string &_output);
        Racer();
        ~Racer() override;

    public:
        void getAnalysisUsage(AnalysisUsage &au) const override;
        bool runOnModule(Module &m) override;
        void print(raw_ostream &os, const Module *m) const override;

    public:
        static char ID;

    protected:
        string mode;
        string input;
        string output;
    };

    // exception
    struct RacerError : public runtime_error {
        explicit RacerError(std::string const &m)
                : std::runtime_error(m) {
        }
    };

    class Instrumentor {
    public:
        Instrumentor(Module &_module, const string &_input)
                : module(_module),
                  ctxt(module.getContext()),
                  oracle(module),
                  dart(module),
                  seed(hash_value(module.getName().str())) {

            // build function oracles
            for (Function &f : module) {
                if (f.isIntrinsic() || f.isDeclaration()) {
                    continue;
                }

                auto fo = new FuncOracle(
                        f, oracle.getDataLayout(), oracle.getTargetLibraryInfo()
                );
                oracle.addOracle(&f, fo);
            }

            // load compile info database
            std::ifstream i(_input.c_str(), std::ifstream::in);
            i >> compileDB;

            // probe APIS and LOCs
            probeAPIs(module, MEMSET_APIS_AVAILS, memsetAPIs);
            probeAPIs(module, MEMCPY_APIS_AVAILS, memcpyAPIs);
        }

        ~Instrumentor() = default;

    public:
        void run(const string &mode);

    protected:
        // steps in instrumentation
        void prepare();

        // utils
        void _hook_stack_var(AllocaInst *svar, bool mask, IRBuilder<> &builder);

        // EXEC
        void inst_exec_ignore();
        void inst_exec_func();

        // COV
        void inst_cov_cfg();

        // MEM
        void inst_mem_stack();
        void inst_mem_access();

        // record
        void record(Logger &L);

    protected:
        // compile info database queries
        json *getSpecialProcedure() {
            for (auto &i : compileDB["special"].items()) {
                if (module.getName().endswith(i.key())) {
                    return &(i.value());
                }
            }
            return nullptr;
        }

        bool isFunctionIgnored(Function *f) {
            auto it = compileDB["ignored"].find(f->getName().str());
            return (it != compileDB["ignored"].end()) &&
                   (it.value().get<bool>());
        }

    protected:
        // utils
        bool isBlockHookMark(Instruction *i) {
            // HACK: abuse the donothing intrinsic as the hook mark
            // (see getBlockHookPoint)
            if (!isa<CallInst>(i)) {
                return false;
            }

            Function *f = cast<CallInst>(i)->getCalledFunction();
            if (f == nullptr || !f->isIntrinsic()) {
                return false;
            }

            return f->getIntrinsicID() == Intrinsic::donothing;
        }

        Instruction *getHookedInst(Instruction *i) {
            // follow through and find the first original instruction
            BasicBlock *bb = i->getParent();

            Instruction *c = i;
            while (instHT.find(c) == instHT.end()) {
                c = c->getNextNode();
                assert(c != nullptr && c->getParent() == bb);
            }

            return c;
        }

        Instruction *getBlockHookPoint(BasicBlock *b) {
            Instruction *i = b->getFirstNonPHI();
            assert(i != nullptr && i->getParent() == b);

            // first time hooking this basic block, establish the mark
            if (instHT.find(i) != instHT.end()) {
                IRBuilder<> builder(i);
                return builder.CreateIntrinsic(Intrinsic::donothing, {}, {});
            }

            // someone should already placed the mark
            while (!isBlockHookMark(i)) {
                assert(instHT.find(i) == instHT.end());
                i = i->getNextNode();
                assert(i != nullptr && i->getParent() == b);
            }

            return i;
        }

        Instruction *getFunctionEntryPoint(Function *f) {
            /*
             * NOTE: for instrumentations added from entry point,
             *       the instruction order follows the instrumentation order.
             */
            return getBlockHookPoint(&f->getEntryBlock());
        }

        vector<Instruction *> getFunctionExitPoints(Function *f) {
            /*
             * NOTE: for instrumentations added from exit points,
             *       the instruction order reverses the instrumentation order.
             */

            vector<Instruction *> vec;
            for (BasicBlock &b : *f) {
                Instruction *term = b.getTerminator();
                if (term != nullptr && isa<ReturnInst>(term)) {
                    assert(instHT.find(term) != instHT.end());

                    Instruction *cur = term, *pre = cur->getPrevNode();
                    assert(pre != nullptr && pre->getParent() == &b);

                    while (instHT.find(pre) == instHT.end()) {
                        // should not go beyond the mark
                        if (isBlockHookMark(pre)) {
                            break;
                        }

                        cur = pre;
                        pre = cur->getPrevNode();
                        assert(pre != nullptr && pre->getParent() == &b);
                    }

                    vec.push_back(cur);
                }
            }

            assert(!vec.empty());
            return vec;
        }

    protected:
        // context
        Module &module;
        LLVMContext &ctxt;

        // derived
        ModuleOracle oracle;
        json compileDB;

        // dart
        DartAPI dart;

        // seed for instrumentation
        hash_code seed;

        map<Function *, hash_code> funcHT;  // instrumentable functions
        map<BasicBlock *, hash_code> blockHT;  // instrumentable basic blocks
        map<Instruction *, hash_code> instHT;  // instrumentable instructions

        // marked instructions
        set<Instruction *> ignoredMemAccess;

        // APIs and LOCs
        map<Instruction *, APIPack<MemSetInfo>> memsetAPIs;
        map<Instruction *, APIPack<MemCpyInfo>> memcpyAPIs;
    };

} /* namespace racer */

#endif /* _RACER_BASE_PLUGIN_H_ */
