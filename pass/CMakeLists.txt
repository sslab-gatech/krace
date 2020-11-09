cmake_minimum_required(VERSION 3.12)
project(racer)

#  studio
if (DEFINED ENV{IN_RACER_DOCKER})
    set(RACER_STUDIO "dock")
else ()
    set(RACER_STUDIO "host")
endif ()

# paths
get_filename_component(RACER_PATH_BASE
                       ${CMAKE_SOURCE_DIR} DIRECTORY)

set(RACER_PATH_LLVM
    "${RACER_PATH_BASE}/studio/${RACER_STUDIO}/store/llvm")

set(RACER_PATH_MISC_JSON
    "${RACER_PATH_BASE}/misc/json")

# configs
add_compile_definitions(RACER_DEBUG_ALL)

# package: llvm
find_package(LLVM REQUIRED
             PATHS ${RACER_PATH_LLVM} NO_DEFAULT_PATH)

# flags: global
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

# project: codegen
add_custom_target(codegen
                  ALL
                  COMMAND python3 ${CMAKE_SOURCE_DIR}/codegen.py
                  BYPRODUCTS dart/vardef.h
                  COMMENT "Generating code")

# project: instrument
add_subdirectory(instrument)

# project: test (only when set)
if (RACER_UNIT_TESTS)
    enable_testing()
    add_subdirectory(test)
endif ()
