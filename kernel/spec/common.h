#ifndef _RACER_SPEC_COMMON_H_
#define _RACER_SPEC_COMMON_H_

// c headers
#include <cstdint>

// std
#include <functional>
#include <string>
#include <tuple>
#include <vector>
#include <unordered_map>
#include <optional>

// debug
#ifdef RACER_DEBUG
#include <cassert>
#endif

// utils
#include "generated/vardef.h"

// scoping
using namespace std;
using bytes = vector<byte>;

namespace spec {

    // forward declarations
    class Bean;

    class Program;

    // type traits
    template<typename T>
    struct copyable_type : true_type {
        static_assert(is_copy_assignable_v<T> && is_copy_constructible_v<T>);
    };

    /** random type is not allowed by default */
    template<typename T, typename Enabled = void>
    struct is_allowed_attr_type
            : false_type {
    };

    /** primitive types (i.e., numerical, string, and bytes) are allowed */
    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_integral_v<T> ||
                    is_same_v<string, T> ||
                    is_same_v<bytes, T>
            >
    > : copyable_type<T> {
    };

    /** Bean types are allowed */
    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_base_of_v<Bean, T>
            >
    > : copyable_type<T> {
    };

    /** optional types allowed only if its value_type is allowed */
    template<typename T_Optional>
    struct is_allowed_attr_type_optional
            : false_type {
    };

    template<typename U>
    struct is_allowed_attr_type_optional<optional<U>>
            : is_allowed_attr_type<U> {
    };

    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_allowed_attr_type_optional<T>::value
            >
    > : copyable_type<T> {
    };

    /** tuple types allowed only if all member types are allowed */
    template<typename T_Tuple>
    struct is_allowed_attr_type_tuple
            : false_type {
    };

    template<typename... Us>
    struct is_allowed_attr_type_tuple<tuple<Us...>>
            : conjunction<is_allowed_attr_type<Us>...> {
    };

    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_allowed_attr_type_tuple<T>::value
            >
    > : copyable_type<T> {
    };

    /** vector types allowed only if the value type is allowed */
    template<typename T_Vector>
    struct is_allowed_attr_type_vector
            : false_type {
    };

    template<typename U>
    struct is_allowed_attr_type_vector<vector<U>>
            : is_allowed_attr_type<U> {
    };

    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_allowed_attr_type_vector<T>::value
            >
    > : copyable_type<T> {
    };

    /** map types allowed only if both the key and value types are allowed */
    template<typename T_Map>
    struct is_allowed_attr_type_map
            : false_type {
    };

    template<typename K, typename V>
    struct is_allowed_attr_type_map<unordered_map<K, V>>
            : conjunction<is_allowed_attr_type<K>, is_allowed_attr_type<V>> {
    };

    template<typename T>
    struct is_allowed_attr_type<T,
            enable_if_t<
                    is_allowed_attr_type_map<T>::value
            >
    > : copyable_type<T> {
    };

    // foundations
    template<typename T>
    class Attr {
        static_assert(is_allowed_attr_type<T>::value);

    private:
        optional<T> _attr = {};

    public:
        explicit operator const T &() const {
#ifdef RACER_DEBUG
            assert(_attr.has_value());
#endif
            return _attr.value();
        }

        Attr &operator=(const T &other) {
            // is_allowed_attr_type_v<T> makes sure that _attr can be copy assigned
            _attr = other;
            return *this;
        }
    };

    class Bean {
    protected:
        // attribute validation
        bool _check = false;

    public:
        virtual void validate() {
#ifdef RACER_DEBUG
            assert(!_check);
#endif
            _check = true;
        }

        virtual void _validate() {
            // by default, do nothing
        }
    };

#define _BEAN_ATTR_DEF(type, name) \
protected: \
    Attr<type> _##name; \
public: \
    /* attribute setter */ \
    void name(const type &other) { \
        this->_##name = other; \
        this->_check = false; \
    } \
    /* attribute getter */ \
    const type &name() const { \
        return static_cast<const type&>(this->_##name); \
    }

#define _BEAN_ATTR_SET(type, name) \
    name(other.name()); \

#define BEAN(name, base, ...) \
    class name: public base { \
    public: \
        /* allow default and copy constructors only */ \
        name(): base() {} \
        name(const name &other): base(other) { \
            VARDEF2(_BEAN_ATTR_SET, , ##__VA_ARGS__) \
        } \
    protected: \
        /* define attributes according to the list */ \
        VARDEF2(_BEAN_ATTR_DEF, , ##__VA_ARGS__) \
    public: \
        /* attribute validation */ \
        void validate() override { \
            base::validate(); \
            name::_validate(); \
        }


// basic types
    BEAN(Rand, Bean,
         bytes, blob)
        /**
         *  Essentially a typed dict, holds the mutation result from a Type object.
         */
    };

    template<typename R>
    BEAN(Type, Bean)
        /**
         *  A semantic type, guiding the mutation of one data point in the program.
         *  i.e., each Type object represents one possible mutation point.
         */
    public:
        using rand_type = R;
        static_assert(is_base_of_v<Rand, R>);

    public:
        // size in memory
        virtual optional<size_t> size() const = 0;

        // mutating the data point (evolve with strict semantics)
        virtual void mutate(Program &prog) const = 0;

        /*
        // puzzling the data point (evolve with loose semantics)
        virtual void puzzle(Program &prog) const = 0;

        // updating the data point after mutation happens elsewhere
        virtual void update(Program &prog) const = 0;

        // handling the returned information from the kernel
        virtual void handle(Program &prog) const = 0;
         */
    };

    template<typename T_Send, typename T_Recv = void>
    BEAN(Field, Bean,
         string, name,
         size_t, size,
         T_Send, type_send,
         optional<T_Recv>, type_recv)
        /**
         * A wrapper over Type to hold extra information representing a field
         * in a composite type (array, struct, union, etc).
         *
         * If `kind_recv` is also set, it means that this field also receives
         * information from the kernel which may be used in some way.
         */

    protected:
        static_assert(is_base_of_v<Type, T_Send>);
        static_assert(is_void_v<T_Recv> || is_base_of_v<Type, T_Recv>);
    };

    template<typename T_Send>
    BEAN(Arg, Bean,
         string, name,
         T_Send, type_send)
        /**
         * A wrapper over Type to hold extra information representing an argument
         * in a syscall.
         *
         * Unlike Field, an Arg does not have `type_recv` as there is no way to
         * pass information back from kernel with Arg.
         */

    protected:
        static_assert(is_base_of_v<Type, T_Send>);
    };

    template<typename T_Recv>
    BEAN(Ret, Bean,
         T_Recv, type_recv)
        /**
         * A wrapper over Type to hold extra information representing a return
         * value from a syscall.
         *
         * Unlike Field, a Ret does not have `type_send` as there is no way to
         * pass information into kernel with Ret.
         */

    protected:
        static_assert(is_base_of_v<Type, T_Recv>);
    };

    template<typename T_Retv, typename... T_Args>
    BEAN(Syscall, Bean,
         optional<Syscall>, parent,
         string, name,
         T_Retv, retv,
         tuple<T_Args...>, args)
    };

    // generated program
    template<typename T>
    struct Lego {
    public:
        using R = typename T::rand_type;
        static_assert(is_base_of_v<Type<R>, T>);

    protected:
        //optional<reference_wrapper<R>> _rand = {};

        /*
    public:
        bool hasRand() {
            return _rand.has_value();
        }

        R &getRand() {
            return _rand.value();
        }
         */
    };

    class Program {
        /**
         *  The synthesized program.
         *
         *  The program is represented by three regions:
         *      - code region: holding immutable data and list of syscalls
         *      - data region: holding mutable data chunks
         *      - exec region: holding the runtime states of the execution
         */

        // type-to-rand mapping
    private:
        template<typename T>
        static unordered_map<
                const Program *,
                unordered_map<reference_wrapper<T>, Lego<T>>
        > _lego;

    public:
        template<typename T>
        Lego<T> &lego(const T &type) {
            return _lego<T>[this][cref(type)];
        }

        template<typename T>
        const Lego<T> &lego(const T &type) const {
            return _lego<T>[this][cref(type)];
        }
    };

    template<typename T>
    unordered_map<
            const Program *,
            unordered_map<reference_wrapper<T>, Lego<T>>
    > Program::_lego;

}; // spec namespace

#endif /* _RACER_SPEC_COMMON_H_ */
