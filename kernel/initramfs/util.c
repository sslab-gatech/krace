#include "common.h"

static void append_to_buf_v(char *buf, size_t size, va_list ap) {
    const char *ptr;
    size_t cur_size, rem_size, seg_size;

    cur_size = strlen(buf);
    if (cur_size >= size)
        return;

    rem_size = size - cur_size;

    for (ptr = va_arg(ap, const char *); ptr; ptr = va_arg(ap, const char *)) {
        strncat(buf, ptr, rem_size - 1);

        seg_size = strlen(ptr);

        /* Make sure it's NUL-terminated. */
        if (seg_size >= rem_size - 1) {
            buf[size - 1] = '\0';
            break;
        }

        rem_size -= seg_size;
    }
}

void app_buf(char *buf, size_t size, ...) {
    va_list ap;

    va_start(ap, size);
    append_to_buf_v(buf, size, ap);
    va_end(ap);
}

void set_buf(char *buf, size_t size, ...) {
    va_list ap;

    va_start(ap, size);
    memset(buf, 0, size);
    append_to_buf_v(buf, size, ap);
    va_end(ap);
}