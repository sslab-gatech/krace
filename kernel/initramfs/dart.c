#include "common.h"

// syscall constants
#define SYS_DART                        500

#define CMD_DART_LAUNCH                 1
#define CMD_DART_FINISH                 2
#define CMD_DART_CTXT_SYSCALL_START     3
#define CMD_DART_CTXT_SYSCALL_EXIT      4

// wrappers
void dart_launch(void) {
    syscall(SYS_DART, CMD_DART_LAUNCH, NULL);
}

void dart_finish(void) {
    syscall(SYS_DART, CMD_DART_FINISH, NULL);
}

void dart_ctxt_syscall_enter(unsigned long sysno) {
    syscall(SYS_DART, CMD_DART_CTXT_SYSCALL_START, sysno);
}

void dart_ctxt_syscall_exit(unsigned long sysno) {
    syscall(SYS_DART, CMD_DART_CTXT_SYSCALL_EXIT, sysno);
}
