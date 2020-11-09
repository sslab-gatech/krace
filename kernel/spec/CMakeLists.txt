cmake_minimum_required(VERSION 3.14)
project(racer-spec)

# compile and link
set(CMAKE_CXX_STANDARD 17)

# debug
add_compile_definitions(RACER_DEBUG)

# code generation
add_custom_target(codegen
                  ALL
                  COMMAND python3 ${CMAKE_SOURCE_DIR}/codegen.py
                  BYPRODUCTS generated/vardef.h
                  COMMENT "Generating vardef.h")

# sources
add_executable(spec
               main.cpp)

add_dependencies(spec codegen)

target_compile_options(spec PUBLIC
                       -Wall -Wextra)
