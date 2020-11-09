#include "analysis/Probe.h"
#include "apidef.inc"
#include "util/Logger.h"

namespace racer {

    // MEM
    const vector<APIDesc<MemSetInfo>> MEMSET_APIS_AVAILS{
            {
                    "memset",
                    {
                            {
                                    "llvm.memset.p0i8.i32",
                                    DART_FLAG_NONE
                            },
                            {
                                    "llvm.memset.p0i8.i64",
                                    DART_FLAG_NONE
                            }
                    },
                    0, 2,
                    DART_FLAG_NONE
            }
    };

    const vector<APIDesc<MemCpyInfo>> MEMCPY_APIS_AVAILS{
            {
                    "memcpy",
                    {
                            {
                                    "llvm.memcpy.p0i8.p0i8.i32",
                                    DART_FLAG_NONE
                            },
                            {
                                    "llvm.memcpy.p0i8.p0i8.i64",
                                    DART_FLAG_NONE
                            },
                            {
                                    "llvm.memmove.p0i8.p0i8.i32",
                                    DART_FLAG_NONE
                            },
                            {
                                    "llvm.memmove.p0i8.p0i8.i64",
                                    DART_FLAG_NONE
                            }
                    },
                    1, 0, 2,
                    DART_FLAG_NONE
            }
    };

    // probers
    template<typename T>
    void probeAPIs(Module &m,
                   const vector<APIDesc<T>> &in,
                   map<Instruction *, APIPack<T>> &out) {

        for (const auto &desc : in) {
#ifdef RACER_DEBUG
            set<const API *> actual;
#endif
            for (Function &f : m) {
                // ignore functions without body
                if (f.isIntrinsic() || f.isDeclaration()) {
                    continue;
                }

                for (BasicBlock &bb : f) {
                    for (Instruction &i : bb) {
                        if (!isa<CallInst>(i)) {
                            continue;
                        }

                        Function *func = cast<CallInst>(i).getCalledFunction();
                        if (func == nullptr) {
                            continue;
                        }

                        for (const auto &api : desc.apis) {
                            if (func->getName().equals(api.func)) {
#ifdef RACER_DEBUG
                                actual.insert(&api);
#endif
                                out[&i] = make_pair(&api, &desc);
                            }
                        }
                    }
                }
            }

            // logging
#if defined(RACER_DEBUG) && defined(RACER_DEBUG_STATUS)
            STAT.show()
                    << "API probe: " << desc.name
                    << " (" << actual.size() << ") ";

            STAT.cont() << "[";
            for (auto const &i : actual) {
                STAT.cont() << i->func << ",";
            }
            STAT.cont() << "]";

            STAT.done();
#endif
        }
    }

    static bool locEquals(const DebugLoc &dl, const LOC &loc) {
        StringRef fn = cast<DIScope>(dl.getScope())->getFilename();
        if (fn.startswith("./")) {
            fn = fn.substr(2);
        }

        return
                fn.equals(loc.file) &&
                dl.getLine() == loc.line &&
                dl.getCol() == loc.column;
    }

    static bool locIncludes(const DebugLoc &dl, const LOC &loc) {
        if (dl.isImplicitCode()) {
            return false;
        }

        if (locEquals(dl, loc)) {
            return true;
        }

        DILocation *inlined = dl.getInlinedAt();
        if (inlined == nullptr) {
            return false;
        }

        return locIncludes(DebugLoc(inlined), loc);
    }

    static bool dlEquals(const DebugLoc &dl1, const DebugLoc &dl2) {
        StringRef fn1 = cast<DIScope>(dl1.getScope())->getFilename();
        StringRef fn2 = cast<DIScope>(dl2.getScope())->getFilename();

        return
                fn1.equals(fn2) &&
                dl1.getLine() == dl2.getLine() &&
                dl1.getCol() == dl2.getCol();
    }

    static bool dlMultiDef(const DebugLoc &dl1, const DebugLoc &dl2,
                           const LOC &loc) {

        assert((!dl1.isImplicitCode()) && (!dl2.isImplicitCode()));

        if (!dlEquals(dl1, dl2)) {
            return true;
        }

        if (locEquals(dl1, loc)) {
            return false;
        }

        DILocation *in1 = dl1.getInlinedAt();
        DILocation *in2 = dl2.getInlinedAt();
        assert(in1 != nullptr && in2 != nullptr);

        return dlMultiDef(DebugLoc(in1), DebugLoc(in2), loc);
    }

    template<typename T>
    void probeLOCs(Module &m,
                   const vector<LOCDesc<T>> &in,
                   map<Instruction *, LOCPack<T>> &out) {

        for (const auto &desc : in) {
#ifdef RACER_DEBUG
            map<const LOC *, const DebugLoc *> actual;
#endif
            for (Function &f : m) {
                // ignore functions without body
                if (f.isIntrinsic() || f.isDeclaration()) {
                    continue;
                }

                for (BasicBlock &bb : f) {
                    for (Instruction &i : bb) {
                        for (const auto &loc : desc.locs) {
                            // opcode match
                            bool match = (i.getOpcode() == loc.opcode);
                            if (!match) {
                                if (loc.opcode == LOC_OPCODE_CALL_ASM) {
                                    match = (isa<CallInst>(i) &&
                                             cast<CallInst>(i).isInlineAsm());
                                }
                            }

                            // location match
                            if (match && locIncludes(i.getDebugLoc(), loc)) {
#ifdef RACER_DEBUG
                                auto it = actual.find(&loc);
                                if (it == actual.end()) {
                                    actual[&loc] = &i.getDebugLoc();
                                } else {
                                    bool mdefs = dlMultiDef(
                                            *(it->second), i.getDebugLoc(), loc
                                    );
                                    if (mdefs) {
                                        DUMP.debugRepr(it->second);
                                        DUMP.debugRepr(&i.getDebugLoc());
                                        llvm_unreachable("Overlapped location");
                                    }
                                }
#endif
                                out[&i] = make_pair(&loc, &desc);
                            }
                        }
                    }
                }
            }

            // logging
#if defined(RACER_DEBUG) && defined(RACER_DEBUG_STATUS)
            STAT.show()
                    << "LOC probe: " << desc.name
                    << " (" << actual.size() << ") ";

            STAT.cont() << "[";
            for (auto const &i : actual) {
                STAT.cont()
                        << i.first->file << ":"
                        << i.first->line << ":"
                        << i.first->column
                        << ",";
            }
            STAT.cont() << "]";

            STAT.done();
#endif
        }
    }

#define INSTANTIATE_PROBE_TEMPLATE(type) \
template void probeAPIs<type>( \
        Module &m, \
        const vector<APIDesc<type>> &in, \
        map<Instruction *, APIPack<type>> &out); \
        \
template void probeLOCs<type>( \
        Module &m, \
        const vector<LOCDesc<type>> &in, \
        map<Instruction *, LOCPack<type>> &out);

    // MEM
    INSTANTIATE_PROBE_TEMPLATE(MemSetInfo)
    INSTANTIATE_PROBE_TEMPLATE(MemCpyInfo)

} /* namespace racer */
