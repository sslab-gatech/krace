#include "common.h"

#ifdef USE_DART
#undef USE_DART
#endif
#include "shared.inc"

void racer_prep(void) {
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
#ifdef RACER_DEBUG
    warn("Disk image mounted", NULL);
#endif

    // prep bytecode interpreter
    char *prep_method = (char *) info + sizeof(struct mount_info);

    if (strcmp(prep_method, "000") == 0) {
        // method empty
#ifdef RACER_DEBUG
        warn("Preparing using method: empty - ", prep_method, NULL);
#endif
    }
        // must be one of the designated method
    else {
        panic(0, "Invalid prep method", NULL);
    }

    // tear-down
    umount_image(info->mod_names, info->mod_names_num,
                 LOOP_DEV, FS_DISK_IMG,
                 FS_DISK_MNT);
#ifdef RACER_DEBUG
    warn("Disk image umounted", NULL);
#endif
}
