#include "util/Lower.h"

namespace racer {

    void Lowering::checkAssumptions(Module &m) {
        for (Function &f : m) {
            // only leaf intrinsics are allowed and donothing is not allowed
            if (f.isIntrinsic()) {
                assert(Intrinsic::isLeaf(f.getIntrinsicID()));
                assert(f.getIntrinsicID() != Intrinsic::donothing);
            }

            for (BasicBlock &b : f) {
                for (Instruction &i : b) {
                    // kernel should have no InvokeInst
                    assert(!isa<InvokeInst>(i));
                    // kernel should have no ResumeInst
                    assert(!isa<ResumeInst>(i));
                }
            }
        }
    }

    static bool findInSourceLinePerLoc(const char *target,
                                       const string &fn, unsigned ln) {

        std::ifstream file(fn, std::ifstream::in);

        if (ln) {
            for (unsigned i = 0; i < ln - 1; i++) {
                file.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
            }
        }

        string line;
        std::getline(file, line);
        file.close();

        return line.find(target) != string::npos;
    }

    bool Lowering::findInSourceLine(const char *target, const DebugLoc &loc) {
        DILocation *dl = loc.get();

        while (dl != nullptr) {
            if (findInSourceLinePerLoc(
                    target, dl->getFilename().str(), dl->getLine()
            )) {
                return true;
            }

            dl = dl->getInlinedAt();
        }

        return false;
    }

} /* namespace racer */
