# distribution
SPEC_SYSCALL_GROUP_WEIGHT_TOTAL = 10000

# sizes
SPEC_PTR_SIZE = 8
SPEC_PAGE_SIZE = 4096

# path limits
SPEC_LINK_MAX = 127
SPEC_NAME_MAX = 255
SPEC_PATH_MAX = 4096

SPEC_XATTR_NAME_MAX = 255
SPEC_XATTR_SIZE_MAX = 65536
SPEC_XATTR_LIST_MAX = 65536

SPEC_AT_FDCWD = -100
SPEC_FD_LIMIT_MIN = 3
SPEC_FD_LIMIT_MAX = 200

# buffer limits
SPEC_RAND_SIZE_MAX = int(SPEC_PAGE_SIZE * 1.5)
SPEC_RAND_COUNT_MAX = 8
SPEC_RAND_OFFSET_MIN = -SPEC_RAND_SIZE_MAX
SPEC_RAND_OFFSET_MAX = SPEC_RAND_SIZE_MAX * 6
SPEC_RAND_PATH_SEG_MAX = 16

# charset and bufset
SPEC_CHARSET = [chr(i) for i in range(1, 256)]
SPEC_BYTESET = [chr(i).encode('charmap') for i in range(0, 256)]

# integer constants
SPEC_ERR_CODE_MIN = -4096
SPEC_ERR_CODE_MAX = -1

# programming
SPEC_PROG_HEAP_OFFSET = 64

# execution
SPEC_EXEC_TRIAL_PER_SYSCALL = 50
