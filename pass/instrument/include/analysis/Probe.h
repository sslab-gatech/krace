#ifndef _RACER_ANALYSIS_PROBE_H_
#define _RACER_ANALYSIS_PROBE_H_

#include "base/Common.h"

namespace racer {

    // basic structs
    struct API {
        string func;
        flag_t flag;
    };

    template<typename T>
    struct APIDesc {
        string name;
        vector<API> apis;
        T info;
        flag_t flag;
    };

    struct LOC {
        string file;
        unsigned line;
        unsigned column;
        unsigned opcode;
        flag_t flag;
    };

#define LOC_OPCODE_CALL_ASM     Instruction::Call + 0x1000

    template<typename T>
    struct LOCDesc {
        string name;
        vector<LOC> locs;
        T info;
        flag_t flag;
    };

    // MEM
    struct MemSetInfo {
        int argAddr;
        int argSize;
    };

    struct MemCpyInfo {
        int argSrc;
        int argDst;
        int argSize;
    };

    extern const vector<APIDesc<MemSetInfo>> MEMSET_APIS_AVAILS;
    extern const vector<APIDesc<MemCpyInfo>> MEMCPY_APIS_AVAILS;

    // probing utilities
    template<typename T>
    using APIPack = pair<const API *, const APIDesc<T> *>;

    template<typename T>
    void probeAPIs(Module &m,
                   const vector<APIDesc<T>> &in,
                   map<Instruction *, APIPack<T>> &out);

    template<typename T>
    using LOCPack = pair<const LOC *, const LOCDesc<T> *>;

    template<typename T>
    void probeLOCs(Module &m,
                   const vector<LOCDesc<T>> &in,
                   map<Instruction *, LOCPack<T>> &out);

} /* namespace racer */

#endif /* _RACER_ANALYSIS_PROBE_H_ */
