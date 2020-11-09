# sources
set(RACER_INSTRUMENT_SOURCES
    lib/util/Logger.cpp
    lib/util/Lower.cpp
    lib/analysis/Oracle.cpp
    lib/analysis/Probe.cpp
    lib/dart/API.cpp
    lib/base/Plugin.cpp
    Main.cpp)

# RacerInstrument: target
add_library(RacerInstrument MODULE
            ${RACER_INSTRUMENT_SOURCES})

add_dependencies(RacerInstrument codegen)

# RacerInstrument: definitions
target_compile_definitions(RacerInstrument PRIVATE
                           ${LLVM_DEFINITIONS})

# RacerInstrument: includes
target_include_directories(RacerInstrument PRIVATE
                           ${LLVM_INCLUDE_DIRS}
                           ${RACER_PATH_MISC_JSON}/single_include
                           ${CMAKE_SOURCE_DIR}/instrument/include
                           ${CMAKE_SOURCE_DIR}/dart)

# RacerInstrument: compile flags
target_compile_options(RacerInstrument PRIVATE
                       "-O3"
                       "-fexceptions")

# RacerInstrument: link flags
if (CMAKE_BUILD_TYPE_REPR STREQUAL "RELEASE")
    set_target_properties(RacerInstrument
                          PROPERTIES INTERPROCEDURAL_OPTIMIZATION TRUE)
endif ()

# RacerInstrument: install
install(TARGETS RacerInstrument DESTINATION lib)
