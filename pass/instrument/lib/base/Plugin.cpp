#include "base/Plugin.h"

namespace racer {

    void Instrumentor::run(const string &mode) {
        // collect functions, blocks, and instructions
        prepare();

        // populate hook points for every block
        for (auto &i : blockHT) {
            getBlockHookPoint(i.first);
        }

        // check if specially handled
        json *special = getSpecialProcedure();
        if (special != nullptr) {
            assert(special->is_string());
            // TODO: handle special procedures by type
            // (there is no special routines for now)
        }

            // check if the instrumentation mode is ignore
        else if (mode == "ignore") {
            /*
             * NOTE: the following instrumentation order has to be honored
             */

            // EXEC
            inst_exec_ignore();
        }

            // the following is the generic instrumentation procedure
        else if (mode == "normal") {
            /*
             * NOTE: the following instrumentation order has to be honored
             */

            // EXEC
            inst_exec_func();

            // COV
            inst_cov_cfg();

            // MEM
            inst_mem_stack();
            inst_mem_access();
        }

            // only ignore or normal mode is allowed
        else {
            llvm_unreachable(("Invalid instrumentation mode: " + mode).c_str());
        }

        // dump the hooking information
        record(SLOG);
    }

    void Instrumentor::prepare() {
        // prepare constants
        uint64_t blockCount = 0;
        uint64_t instCount = 0;

        for (Function &f : module) {
            // ignore functions without body
            if (f.isIntrinsic() || f.isDeclaration()) {
                continue;
            }

            // ignore functions marked as ignored
            if (isFunctionIgnored(&f)) {
                continue;
            }

            // calculate the function hash
            hash_code funcHash = hash_combine(
                    seed, hash_value(f.getName().str())
            );
            funcHT.emplace(&f, funcHash);

            // per-block enumerate
            for (BasicBlock &bb : f) {
                hash_code blockHash = hash_combine(funcHash, blockCount++);
                blockHT.emplace(&bb, blockHash);

                // per-instruction enumerate
                for (Instruction &i : bb) {
                    hash_code instHash = hash_combine(blockHash, instCount++);
                    instHT.emplace(&i, instHash);
                }
            }
        }
    }

    void Instrumentor::inst_exec_ignore() {
        for (auto &i : funcHT) {
            Function *func = i.first;

            // hooks placed at the function start
            Instruction *instInit = getFunctionEntryPoint(func);
            IRBuilder<> builderInit(instInit);

            dart.dart_hook_exec_pause(
                    builderInit,
                    DART_FLAG_NONE, i.second
            );

            // hooks placed at the function end
            vector<Instruction *> exits = getFunctionExitPoints(func);
            for (Instruction *instFini : exits) {
                IRBuilder<> builderFini(instFini);

                dart.dart_hook_exec_resume(
                        builderFini,
                        DART_FLAG_NONE, i.second
                );
            }
        }
    }

    void Instrumentor::inst_exec_func() {
        for (auto &i : funcHT) {
            Function *func = i.first;

            // hooks placed at the function start
            Instruction *instInit = getFunctionEntryPoint(func);
            IRBuilder<> builderInit(instInit);

            dart.dart_hook_exec_func_enter(
                    builderInit,
                    DART_FLAG_NONE, i.second,
                    func
            );

            // hooks placed at the function end
            vector<Instruction *> exits = getFunctionExitPoints(func);
            for (Instruction *instFini : exits) {
                IRBuilder<> builderFini(instFini);

                dart.dart_hook_exec_func_exit(
                        builderFini,
                        DART_FLAG_NONE, i.second,
                        func
                );
            }
        }
    }

    void Instrumentor::inst_cov_cfg() {
        // branch coverage
        for (auto &i : blockHT) {
            IRBuilder<> builder(getBlockHookPoint(i.first));
            dart.dart_hook_cov_cfg(builder, DART_FLAG_NONE, i.second);
        }
    }

    void Instrumentor::_hook_stack_var(
            AllocaInst *svar, bool mask, IRBuilder<> &builder
    ) {
        Value *size = ConstantInt::get(
                Type::getInt64Ty(ctxt),
                oracle.getTypeAllocatedSize(svar->getAllocatedType())
        );

        if (svar->isArrayAllocation()) {
            size = builder.CreateMul(svar->getArraySize(), size);
        }

        if (mask) {
            dart.dart_hook_mem_stack_push(
                    builder, DART_FLAG_NONE, instHT[svar], svar, size
            );
        } else {
            dart.dart_hook_mem_stack_pop(
                    builder, DART_FLAG_NONE, instHT[svar], svar, size
            );
        }
    }

    void Instrumentor::inst_mem_stack() {
        for (auto &i : funcHT) {
            // collect stack variables
            vector<AllocaInst *> vars;
            vector<AllocaInst *> blks;

            for (BasicBlock &bb : *i.first) {
                blks.clear();

                Instruction *firstAlloca = nullptr;
                Instruction *lastAlloca = nullptr;

                for (Instruction &inst : bb) {
                    // should ignore the instrumented instructions
                    if (instHT.find(&inst) == instHT.end()) {
                        continue;
                    }

                    // collect variables
                    if (auto *alloca = dyn_cast<AllocaInst>(&inst)) {
                        if (firstAlloca == nullptr) {
                            firstAlloca = alloca;
                        }
                        blks.emplace_back(alloca);
                        vars.emplace_back(alloca);
                        lastAlloca = alloca;
                    }
                }

                if (lastAlloca == nullptr) {
                    continue;
                }

#ifdef RACER_DEBUG
                // assert that AllocaInst are contiguous in a block
                Instruction *cursor = firstAlloca;
                while (cursor != lastAlloca) {
                    if (!isa<AllocaInst>(cursor)) {
                        STAT.warn()
                                << "non-contiguous alloca in function "
                                << i.first->getName()
                                << ": ["
                                << Dumper::getValueType(cursor)
                                << "] "
                                << Dumper::getValueRepr(cursor);
                        STAT.done();
                    }
                    cursor = cursor->getNextNode();
                }
#endif

                // blacklist after the last alloca
                IRBuilder<> builderInit(lastAlloca->getNextNode());
                for (auto &v : blks) {
                    _hook_stack_var(v, true, builderInit);
                }
            }

            // whitelist them at the function end
            for (Instruction *instFini : getFunctionExitPoints(i.first)) {
                IRBuilder<> builderFini(instFini);
                for (auto &v : vars) {
                    _hook_stack_var(v, false, builderFini);
                }
            }
        }
    }

    void Instrumentor::inst_mem_access() {
        for (auto &i : instHT) {
            Instruction *inst = i.first;

            // ignore instructions that are already hooked by others
            if (ignoredMemAccess.find(inst) != ignoredMemAccess.end()) {
                continue;
            }

            // load and store instructions
            if (auto *i_load = dyn_cast<LoadInst>(inst)) {
                IRBuilder<> builder(i_load);
                dart.dart_hook_mem_read(
                        builder,
                        DART_FLAG_NONE, instHT[i_load],
                        i_load->getPointerOperand(),
                        dart.createDataValue(oracle.getTypeStoreSize(
                                i_load->getType()
                        ))
                );
                continue;
            }

            if (auto *i_store = dyn_cast<StoreInst>(inst)) {
                IRBuilder<> builder(i_store);
                dart.dart_hook_mem_write(
                        builder,
                        DART_FLAG_NONE, instHT[i_store],
                        i_store->getPointerOperand(),
                        dart.createDataValue(oracle.getTypeStoreSize(
                                i_store->getValueOperand()->getType()
                        ))
                );
                continue;
            }

            // memset
            {
                auto it = memsetAPIs.find(inst);
                if (it != memsetAPIs.end()) {
                    auto *call = cast<CallInst>(inst);
                    const MemSetInfo &info = it->second.second->info;
                    flag_t flag =
                            it->second.first->flag | it->second.second->flag;

                    IRBuilder<> builder(call);
                    dart.dart_hook_mem_write(
                            builder,
                            flag, instHT[call],
                            call->getArgOperand(info.argAddr),
                            call->getArgOperand(info.argSize)
                    );
                    continue;
                }
            }

            // memcpy
            {
                auto it = memcpyAPIs.find(inst);
                if (it != memcpyAPIs.end()) {
                    auto *call = cast<CallInst>(inst);
                    const MemCpyInfo &info = it->second.second->info;
                    flag_t flag =
                            it->second.first->flag | it->second.second->flag;

                    IRBuilder<> builder(call);
                    dart.dart_hook_mem_read(
                            builder,
                            flag, instHT[call],
                            call->getArgOperand(info.argSrc),
                            call->getArgOperand(info.argSize)
                    );
                    dart.dart_hook_mem_write(
                            builder,
                            flag, instHT[call],
                            call->getArgOperand(info.argDst),
                            call->getArgOperand(info.argSize)
                    );
                    continue;
                }
            }
        }
    }

    void Instrumentor::record(Logger &L) {
        // record meta information
        L.map("meta");
        L.log("seed", size_t(seed));

        L.vec("apis");
        for (Function &f : module) {
            if (f.isDeclaration() || f.isIntrinsic()) {
                L.log(f.getName().str());
            }
        }
        L.pop();

        L.vec("gvar");
        for (GlobalVariable &g : module.globals()) {
            L.log(Dumper::getValueRepr(&g));
        }
        L.pop();

        L.vec("structs");
        for (StructType *type : module.getIdentifiedStructTypes()) {
            L.log(type->getName().str());
        }
        L.pop();

        L.pop();

        // record functions
        L.map("funcs");

        for (auto &i : funcHT) {
            L.map(i.first->getName().str());

            L.map("meta");
            L.log("hash", size_t(i.second));
            L.pop();

            // record blocks
            L.vec("blocks");
            for (BasicBlock &bb : *i.first) {
                // ignore blocks added for instrumentation
                if (blockHT.find(&bb) == blockHT.end()) {
                    continue;
                }

                L.map();

                L.log("hash", size_t(blockHT[&bb]));

                // record pred and succ
                L.vec("pred");
                pred_iterator pi = pred_begin(&bb), pe = pred_end(&bb);
                for (; pi != pe; ++pi) {
                    L.log(size_t(blockHT[*pi]));
                }
                L.pop();

                L.vec("succ");
                succ_iterator si = succ_begin(&bb), se = succ_end(&bb);
                for (; si != se; ++si) {
                    L.log(size_t(blockHT[*si]));
                }
                L.pop();

                // record instructions
                L.vec("inst");
                for (Instruction &inst : bb) {
                    // ignore insts added for instrumentation
                    if (instHT.find(&inst) == instHT.end()) {
                        continue;
                    }

                    L.map();
                    L.log("hash", size_t(instHT[&inst]));
                    L.log("repr", Dumper::getValueRepr(&inst));
                    L.log("info", Dumper::getDebugRepr(&(inst.getDebugLoc())));
                    L.pop();
                }
                L.pop();

                L.pop();
            }
            L.pop();

            L.pop();
        }

        L.pop();
    }

} /* namespace racer */