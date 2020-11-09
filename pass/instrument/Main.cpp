#include "base/Plugin.h"
#include "analysis/Oracle.h"
#include "util/Logger.h"
#include "util/Lower.h"

#include <llvm/IR/LegacyPassManager.h>
#include <llvm/Transforms/IPO/PassManagerBuilder.h>

#include <csignal>

namespace racer {

    // pass info
    char Racer::ID = 0;
    static RegisterPass<Racer> X("Racer", "Kernel Race Checker", false, false);

    // options
    cl::opt<string> MODE("racer-mode",
                         cl::Required,
                         cl::desc("<racer mode>"));
    cl::opt<string> INPUT("racer-input",
                          cl::Required,
                          cl::desc("<racer input>"));
    cl::opt<string> OUTPUT("racer-output",
                           cl::Required,
                           cl::desc("<racer output>"));

    static void interruptHandler(int signal) {
#if defined(RACER_DEBUG) && defined(RACER_DEBUG_STATUS)
        STAT.show() << "Terminated with signal: " << signal;
        STAT.done();
#endif

        // directly terminate all threads
        exit(-1);
    }

    // class Racer
    Racer::Racer(
            const string &_mode, const string &_input, const string &_output
    )
            : ModulePass(ID),
              mode(_mode), input(_input), output(_output) {

        // register signal handlers
        signal(SIGINT, interruptHandler);
    }

    Racer::Racer()
            : Racer(MODE.getValue(), INPUT.getValue(), OUTPUT.getValue()) {
    }

    Racer::~Racer() {
#ifdef RACER_DEBUG
        SLOG.dump(output);
#endif
    }

    void Racer::getAnalysisUsage(AnalysisUsage &au) const {
        // conservatively think that we changed everything...
        // so, do nothing here
    }

    bool Racer::runOnModule(Module &m) {
#if defined(RACER_DEBUG) && defined(RACER_DEBUG_STATUS)
        STAT.show() << m.getName();
        STAT.done();
#endif

        // check assumptions
        Lowering::checkAssumptions(m);

        // instrument
        Instrumentor(m, input).run(mode);

        // end of instrumentation
#if defined(RACER_DEBUG) && defined(RACER_DEBUG_STATUS)
        STAT.show() << "Instrumentation finished";
        STAT.done();
#endif

        // mark we have touched things in the module
        return true;
    }

    void Racer::print(raw_ostream &os, const Module *m) const {
        os << "Racer completed on " << m->getName() << "\n";
    }

    // automatically run the pass
    static void registerRacerPass(const PassManagerBuilder &,
                                  legacy::PassManagerBase &PM) {

        PM.add(new Racer());
    }

    static RegisterStandardPasses
            RegisterPassRacer_Ox(PassManagerBuilder::EP_OptimizerLast,
                                 registerRacerPass);
    static RegisterStandardPasses
            RegisterPassRacer_O0(PassManagerBuilder::EP_EnabledOnOptLevel0,
                                 registerRacerPass);

}  /* namespace racer */
