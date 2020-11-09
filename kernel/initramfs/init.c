#include "common.h"

#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/syscall.h>

// configs

#define IVSHMEM_KMOD                "/mod/drivers/misc/ivshmem.ko"
#define IVSHMEM_PATH                "/dev/uio0"
#define FSSHARE_TAG                 "fsshare"

// global pointer to the ivshmem
void *g_shmem = NULL;

// utils
static inline void mount_pseudofs(char *type, char *dest) {
    int rv = mount("none", dest, type, 0, NULL);
    if (rv < 0) {
        panic(errno, "Failed to mount fs", NULL);
    }
}

static inline void *setup_ivshmem(void) {
    int rv;

    // map ivshmem
    int fd = open(IVSHMEM_PATH, O_RDWR);
    if (fd < 0) {
        panic(errno, "Failed to open ivshmem device", NULL);
    }

    void *ivshmem = mmap(
            0, IVSHMEM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0
    );
    if (ivshmem == (void *) -1) {
        panic(errno, "Failed to mmap ivshmem", NULL);
    }

    // prevent from getting swapped out
    rv = mlockall(MCL_CURRENT | MCL_FUTURE);
    if (rv) {
        panic(errno, "Failed to mlockall", NULL);
    }

    return ivshmem;
}

static inline void clean_ivshmem(void *ivshmem) {
    int rv;

    rv = munlockall();
    if (rv) {
        panic(errno, "Failed to munlockall", NULL);
    }

    rv = munmap(ivshmem, IVSHMEM_SIZE);
    if (rv) {
        panic(errno, "Failed to munmap ivshmem", NULL);
    }
}

static inline void setup_fsshare(void) {
    int rv;

    // prepare the mount point
    rv = mkdir(FSSHARE_MNT, 0777);
    if (rv == -1) {
        panic(errno, "Failed to create host point", NULL);
    }

    // do the actual mount
    rv = mount(
            FSSHARE_TAG, FSSHARE_MNT,
            "9p", 0,
            "trans=virtio,version=9p2000.L"
    );
    if (rv == -1) {
        panic(errno, "Failed to mount fsshare", NULL);
    }
}

static inline void clean_fsshare(void) {
    int rv;

    // do force umount
    rv = umount2(FSSHARE_MNT, 0);
    if (rv) {
        panic(errno, "Failed to umount fsshare", NULL);
    }
}

int main(void) {
    // warm the system
#ifdef RACER_DEBUG
    warn("Starting the guest system", NULL);
#endif

    // modules
    load_module(IVSHMEM_KMOD);

    // fs
    mount_pseudofs("devtmpfs", "/dev");

    // set-up
    g_shmem = setup_ivshmem();
    setup_fsshare();

    // prepare variables
    struct shmem_hdr *hdr = (struct shmem_hdr *) g_shmem;

    // mark that we have not started executing
    hdr->status = 0;

    // fork and wait
    pid_t child = fork();
    if (child < 0) {
        panic(errno, "Failed to spwan child process", NULL);
    }

    if (child) {
        // in parent, wait for termination
        int status;
        if (waitpid(child, &status, WUNTRACED) != child) {
            panic(errno, "Failed to wait for child termination", NULL);
        }

        if (!(WIFEXITED(status) || WIFSIGNALED(status))) {
            panic(errno, "Child stopped for no valid reason", NULL);
        }
    } else {
        // in child, choose action based on command
        switch (hdr->command) {
            case 't':
                racer_test();
                break;
            case 'p':
                racer_prep();
                break;
            case 'c':
                racer_cont();
                break;
            case 'f':
                racer_fuzz();
                break;
            default:
                warn("Unknown command, exiting...", NULL);
                break;
        }
    }

    // mark that we have done with the execution
    hdr->status = 1;

    // tear-down
    clean_fsshare();
    clean_ivshmem(g_shmem);

    // halt the system
#ifdef RACER_DEBUG
    warn("Stopping the guest system", NULL);
#endif

    reboot(RB_POWER_OFF);

    // should not even reach here
    return 1;
}
