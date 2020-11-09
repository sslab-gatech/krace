#ifndef _RACER_BASE_COMMON_H_
#define _RACER_BASE_COMMON_H_

// c/c++ basics
#include <string>
#include <fstream>

// stl data structs
#include <list>
#include <queue>
#include <set>
#include <stack>
#include <vector>

// llvm pass
#include <llvm/Pass.h>

// llvm traits
#include <llvm/ADT/GraphTraits.h>
#include <llvm/ADT/iterator_range.h>
#include <llvm/ADT/Hashing.h>

// llvm IR basics
#include <llvm/IR/Argument.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CallSite.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DebugInfoMetadata.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/InlineAsm.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/TypeFinder.h>

// llvm analysis
#include <llvm/ADT/SCCIterator.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/CallGraph.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopInfoImpl.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/ScalarEvolutionExpressions.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Support/GenericDomTree.h>

// llvm instrumentation
#include <llvm/IR/IRBuilder.h>

// llvm support
#include <llvm/Support/FormatVariadic.h>
#include <llvm/Support/raw_ostream.h>

// used namespaces
using namespace std;
using namespace llvm;

// json
#include <nlohmann/json.hpp>
using json = nlohmann::json;

// debug config
#ifdef RACER_DEBUG_ALL
#define RACER_DEBUG
#define RACER_DEBUG_STATUS
#endif

// types
typedef uint64_t flag_t;

#endif /* _RACER_BASE_COMMON_H_ */
