cmake_minimum_required(VERSION 3.14)
project(initramfs C)

#  studio
if (DEFINED ENV{IN_RACER_DOCKER})
    set(RACER_STUDIO "dock")
else ()
    set(RACER_STUDIO "host")
endif ()

# paths
get_filename_component(RACER_PATH_KERNEL
                       ${CMAKE_SOURCE_DIR} DIRECTORY)

get_filename_component(RACER_PATH_BASE
                       ${RACER_PATH_KERNEL} DIRECTORY)

set(LINUX_NAME
    ${LINUX_FLAVOR}-${LINUX_INTENT})

set(RACER_PATH_LINUX
    "${RACER_PATH_BASE}/studio/${RACER_STUDIO}/store/linux-${LINUX_NAME}")

set(RACER_PATH_DART
    "${RACER_PATH_BASE}/pass/dart")

# global level flags
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED TRUE)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wall -Wextra")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fno-inline-small-functions")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fno-caller-saves")

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

include_directories(
        ${CMAKE_SOURCE_DIR}
        ${RACER_PATH_LINUX}/include
        ${RACER_PATH_DART}
)

# debug
add_compile_definitions(RACER_DEBUG)

# misc
set(CMAKE_VERBOSE_MAKEFILE ON)

# the init program
add_executable(init
               # the init program
               init.c dart.c log.c util.c strace.c
               # ltp
               prog-test/main.c
               prog-test/ltp_output.c
               prog-test/ltp_safe_op_user.c
               prog-test/ltp_safe_op_file.c
               # fs preparation
               prog-prep/main.c
               # fs continued execution
               prog-cont/main.c
               # fs fuzzing
               prog-fuzz/main.c)
target_link_libraries(init PUBLIC Threads::Threads)
target_link_libraries(init PUBLIC "-static")

# install
install(TARGETS init DESTINATION bin)