#ifndef _RACER_UTIL_LOGGER_H_
#define _RACER_UTIL_LOGGER_H_

#include "base/Common.h"

namespace racer {

    class Logger {
    public:
        Logger()
                : rec(json::object()), cur(&rec) {
            stk.push(cur);
        }

        ~Logger() = default;

        // level + 1
        void vec();
        void vec(const string &key);

        void map();
        void map(const string &key);

        // stay on same level
        template<typename T>
        void log(const T &msg);
        void log(const char *msg);

        template<typename T>
        void log(const string &key, const T &msg);
        void log(const string &key, const char *msg);

        // record pointer
        void ptr(void *ptr);
        void ptr(const string &key, void *ptr);

        // level - 1
        void pop();

        // move data
        void add(Logger &other);
        void add(const string &key, Logger &other);

        // test
        bool isVec();
        bool isMap();

        // dump to file
        void dump(raw_ostream &stm, int indent = 2);
        void dump(const string &fn, int indent = 2);

    protected:
        json rec;
        json *cur;
        stack<json *> stk;
    };

    class Status {
    public:
        Status()
                : stm(errs()) {
        }

        ~Status() {
            stm.flush();
        }

    public:
        raw_ostream &show();
        raw_ostream &cont();
        raw_ostream &warn();
        void done();

    protected:
        raw_ostream &stm;
    };

    class Dumper {
    public:
        // llvm value
        static string getValueName(const Value *v);
        static string getValueType(const Value *v);
        static string getValueRepr(const Value *v);
        static string getDebugRepr(const DebugLoc *d);

        // llvm type
        static string getTypeName(Type *t);
        static string getTypeRepr(Type *t);

        // constructor / destructor
        Dumper() = default;
        ~Dumper() = default;

        // llvm value
        void namedValue(Value *v);
        void typedValue(Value *v);
        void ctypeValue(Value *v);

        // llvm type
        void namedType(Type *t);

        // llvm debug info
        void debugRepr(const DebugLoc *d);
    };

// globals
#ifdef RACER_DEBUG
    extern Logger SLOG;
    extern Status STAT;
#endif
    extern Dumper DUMP;

}

#endif /* _RACER_UTIL_LOGGER_H_ */
