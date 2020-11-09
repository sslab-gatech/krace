#include "util/Logger.h"

#include <ctime>
#include <iomanip>
#include <sstream>

#include <llvm/Support/FileSystem.h>

namespace racer {

    // class Logger
    void Logger::vec() {
        assert(cur->is_array());

        cur->emplace_back(json::array());

        cur = &cur->back();
        stk.push(cur);
    }

    void Logger::vec(const string &key) {
        assert(cur->is_object());

        auto res = cur->emplace(key, json::array());
        assert(res.second);

        cur = &res.first.value();
        stk.push(cur);
    }

    void Logger::map() {
        assert(cur->is_array());

        cur->emplace_back(json::object());

        cur = &cur->back();
        stk.push(cur);
    }

    void Logger::map(const string &key) {
        assert(cur->is_object());

        auto res = cur->emplace(key, json::object());
        assert(res.second);

        cur = &res.first.value();
        stk.push(cur);
    }

    template<typename T>
    void Logger::log(const T &msg) {
        assert(cur->is_array());
        cur->emplace_back(msg);
    }

    void Logger::log(const char *msg) {
        assert(cur->is_array());
        cur->emplace_back(msg);
    }

    template<typename T>
    void Logger::log(const string &key, const T &msg) {
        assert(cur->is_object());
        cur->emplace(key, msg);
    }

    void Logger::log(const string &key, const char *msg) {
        assert(cur->is_object());
        cur->emplace(key, msg);
    }

    void Logger::ptr(void *ptr) {
        assert(cur->is_array());
        cur->emplace_back(reinterpret_cast<uintptr_t>(ptr));
    }

    void Logger::ptr(const string &key, void *ptr) {
        assert(cur->is_object());
        cur->emplace(key, reinterpret_cast<uintptr_t>(ptr));
    }

    void Logger::pop() {
        stk.pop();
        cur = stk.top();
    }

    void Logger::add(Logger &other) {
        assert(cur->is_array());
        cur->emplace_back(std::move(other.rec));
    }

    void Logger::add(const string &key, Logger &other) {
        assert(cur->is_object());
        cur->emplace(key, std::move(other.rec));
    }

    bool Logger::isVec() {
        return cur->is_array();
    }

    bool Logger::isMap() {
        return cur->is_object();
    }

    void Logger::dump(raw_ostream &stm, int indent) {
        stm << rec.dump(indent);
    }

    void Logger::dump(const string &fn, int indent) {
        error_code ec;

#if LLVM_VERSION_MAJOR <= 6
#define LLVM_OSTREAM_RW_FLAG (sys::fs::F_RW)
#else
#define LLVM_OSTREAM_RW_FLAG (sys::fs::FA_Read | sys::fs::FA_Write)
#endif

        raw_fd_ostream stm(StringRef(fn), ec, LLVM_OSTREAM_RW_FLAG);
        assert(ec.value() == 0);

        dump(stm, indent);
    }

#define INSTANTIATE_TEMPLATE(type)                  \
    template void Logger::log<type>(const type& msg); \
    template void Logger::log<type>(const string& key, const type& msg);

    INSTANTIATE_TEMPLATE(bool);
    INSTANTIATE_TEMPLATE(int);
    INSTANTIATE_TEMPLATE(unsigned int);
    INSTANTIATE_TEMPLATE(long);
    INSTANTIATE_TEMPLATE(unsigned long);
    INSTANTIATE_TEMPLATE(string);

    // class Status
    raw_ostream &Status::show() {
        time_t t = time(nullptr);
        struct tm *i = localtime(&t);

        stringstream s;
        s << put_time(i, "%H:%M:%S");

        return stm << "[" << s.str() << "] ";
    }

    raw_ostream &Status::cont() {
        return stm;
    }

    raw_ostream &Status::warn() {
        return stm << "[WARNING] ";
    }

    void Status::done() {
        stm << "\n";
        stm.flush();
    }

    // class Dumper
    string Dumper::getValueName(const Value *v) {
        if (!v->hasName()) {
            return to_string(reinterpret_cast<uintptr_t>(v));
        } else {
            return v->getName().str();
        }
    }

    string Dumper::getValueType(const Value *v) {
        if (auto inst = dyn_cast<Instruction>(v)) {
            return string(inst->getOpcodeName());
        } else {
            return string("value " + to_string(v->getValueID()));
        }
    }

    static void printFunction(const Function *f, raw_string_ostream &stm) {
        if (f->isDeclaration()) {
            stm << "declare ";
        } else {
            stm << "define ";
        }

        FunctionType *ft = f->getFunctionType();
        ft->getReturnType()->print(stm);
        stm << " @";

        if (f->hasName()) {
            stm << f->getName();
        } else {
            stm << "<anon>";
        }

        stm << "(";
        for (auto &arg : f->args()) {
            if (arg.getArgNo() != 0) {
                stm << ", ";
            }
            arg.print(stm);
        }
        stm << ")";
    }

    static void printBasicBlock(const BasicBlock *b, raw_string_ostream &stm) {
        const Function *f = b->getParent();

        unsigned bseq = 0, iseq = 0;
        for (const BasicBlock &bb : *f) {
            if (&bb == b) {
                break;
            }
            bseq += 1;
            iseq += bb.size();
        }

        if (b->hasName()) {
            stm << b->getName();
        } else {
            stm << "<label>";
        }
        stm << ": " << bseq << " | " << iseq;
    }

    string Dumper::getValueRepr(const Value *v) {
        string str;
        raw_string_ostream stm(str);

        if (auto *p_func = dyn_cast<Function>(v)) {
            stm << "function: ";
            printFunction(p_func, stm);
        } else if (auto *p_bb = dyn_cast<BasicBlock>(v)) {
            stm << "basic block: ";
            printBasicBlock(p_bb, stm);
        } else {
            v->print(stm);
        }

        stm.flush();
        return str;
    }

    string Dumper::getDebugRepr(const DebugLoc *d) {
        string str;
        raw_string_ostream stm(str);

        d->print(stm);

        stm.flush();
        return str;
    }

    string Dumper::getTypeName(Type *t) {
        return string("type " + to_string(t->getTypeID()));
    }

    string Dumper::getTypeRepr(Type *t) {
        string str;
        raw_string_ostream stm(str);

        t->print(stm);

        stm.flush();
        return str;
    }

    void Dumper::namedValue(Value *v) {
        errs() << "[" << getValueName(v) << "]" << getValueRepr(v) << "\n";
    }

    void Dumper::typedValue(Value *v) {
        errs() << "[" << getValueType(v) << "]" << getValueRepr(v) << "\n";
    }

    void Dumper::ctypeValue(Value *v) {
        errs() << "[" << getTypeRepr(v->getType()) << "]" << getValueRepr(v)
               << "\n";
    }

    void Dumper::namedType(Type *t) {
        errs() << "[" << getTypeName(t) << "]" << getTypeRepr(t) << "\n";
    }

    void Dumper::debugRepr(const DebugLoc *d) {
        errs() << getDebugRepr(d) << "\n";
    }

    // globals
#ifdef RACER_DEBUG
    Logger SLOG;
    Status STAT;
#endif
    Dumper DUMP;

} /* namespace racer */
