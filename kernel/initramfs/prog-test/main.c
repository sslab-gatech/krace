#include "common.h"

#ifndef USE_DART
#define USE_DART
#endif
#include "shared.inc"

void racer_test(void) {
    int fd;
    const char *buf_in = "HELLO FROM RACER";
    char buf_out[256] = {0};

    // get mount info
    struct mount_info *info = (struct mount_info *) (
            (char *) g_shmem + sizeof(struct shmem_hdr)
    );

    // set-up
    mount_image(info->mod_main, info->mod_main_num,
                info->mod_deps, info->mod_deps_num,
                info->fs_type, info->mnt_opts,
                LOOP_DEV,
                FS_DISK_IMG, FS_DISK_MNT);

    // test sequence
    SYSRUN_VAL(1, SYS_chdir, FS_DISK_MNT);

    // create directory
    SYSRUN_VAL(2, SYS_mkdir, "dir_foo", 0777);
    fd = SYSRUN_VAL(3, SYS_open, "dir_foo", O_DIRECTORY | O_RDONLY, 0777);
    SYSRUN_VAL(2, SYS_dup2, fd, 199);
    SYSRUN_VAL(1, SYS_close, 199);
    SYSRUN_VAL(1, SYS_close, fd);

    // create file
    fd = SYSRUN_VAL(2, SYS_creat, "file_bar", 0777);
    SYSRUN_VAL(2, SYS_dup2, fd, 198);
    SYSRUN_VAL(1, SYS_close, 198);
    SYSRUN_VAL(1, SYS_close, fd);

    // file io
    fd = SYSRUN_VAL(3, SYS_open, "file_bar", O_RDWR, 0777);
    SYSRUN_VAL(3, SYS_write, fd, buf_in, strlen(buf_in) + 1);
    SYSRUN_VAL(1, SYS_close, fd);

    SYSRUN_VAL(1, SYS_chdir, "/");

    // tear-down
    umount_image(info->mod_names, info->mod_names_num,
                 LOOP_DEV, FS_DISK_IMG,
                 FS_DISK_MNT);
}
