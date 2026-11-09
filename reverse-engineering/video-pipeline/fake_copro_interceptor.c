#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <stdint.h>

static int g_fake_copro_fd = -1;
static int (*real_open)(const char *pathname, int flags, ...) = NULL;
static int (*real_openat)(int dirfd, const char *pathname, int flags, ...) = NULL;
static int (*real_close)(int fd) = NULL;
static int (*real_ioctl)(int fd, unsigned long request, ...) = NULL;
static ssize_t (*real_read)(int fd, void *buf, size_t count) = NULL;
static ssize_t (*real_write)(int fd, const void *buf, size_t count) = NULL;

static void hex_dump(const char *label, const unsigned char *buf, size_t len) {
    printf("[COPRO_DUMP] %s (%zu bytes):\n  ", label, len);
    for (size_t i = 0; i < len; i++) {
        printf("%02X ", buf[i]);
        if ((i + 1) % 16 == 0 && (i + 1) < len) {
            printf("\n  ");
        }
    }
    printf("\n  ASCII: ");
    for (size_t i = 0; i < len; i++) {
        char c = (buf[i] >= 32 && buf[i] <= 126) ? (char)buf[i] : '.';
        putchar(c);
    }
    printf("\n");
    fflush(stdout);
}

static void init_hooks(void) {
    static int initialized = 0;
    if (initialized) return;
    initialized = 1;

    real_open = dlsym(RTLD_NEXT, "open");
    real_openat = dlsym(RTLD_NEXT, "openat");
    real_close = dlsym(RTLD_NEXT, "close");
    real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    real_read = dlsym(RTLD_NEXT, "read");
    real_write = dlsym(RTLD_NEXT, "write");

    fprintf(stderr, "[INTERCEPTOR] Interceptor library initialized successfully.\n");
}

int open(const char *pathname, int flags, ...) {
    init_hooks();
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
    }

    if (pathname && (strstr(pathname, "copro_comms") != NULL || strstr(pathname, "allegroIP") != NULL)) {
        fprintf(stderr, "[INTERCEPTOR] Intercepted open(\"%s\", 0x%x)\n", pathname, flags);
        // Open a dummy pipe or /dev/null
        int fd = real_open("/dev/null", O_RDWR);
        if (strstr(pathname, "copro_comms") != NULL) {
            g_fake_copro_fd = fd;
        }
        return fd;
    }

    return real_open(pathname, flags, mode);
}

int openat(int dirfd, const char *pathname, int flags, ...) {
    init_hooks();
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
    }

    if (pathname && (strstr(pathname, "copro_comms") != NULL || strstr(pathname, "allegroIP") != NULL)) {
        fprintf(stderr, "[INTERCEPTOR] Intercepted openat(\"%s\", 0x%x)\n", pathname, flags);
        int fd = real_open("/dev/null", O_RDWR);
        if (strstr(pathname, "copro_comms") != NULL) {
            g_fake_copro_fd = fd;
        }
        return fd;
    }

    return real_openat(dirfd, pathname, flags, mode);
}

int close(int fd) {
    init_hooks();
    if (fd == g_fake_copro_fd) {
        fprintf(stderr, "[INTERCEPTOR] Intercepted close(fake_copro_fd=%d)\n", fd);
        g_fake_copro_fd = -1;
    }
    return real_close(fd);
}

int ioctl(int fd, unsigned long request, ...) {
    init_hooks();
    va_list args;
    va_start(args, request);
    void *argp = va_arg(args, void *);
    va_end(args);

    if (fd == g_fake_copro_fd || g_fake_copro_fd != -1) {
        fprintf(stderr, "[INTERCEPTOR] ioctl(fd=%d, req=0x%08lX, argp=%p)\n", fd, request, argp);

        // FIONREAD
        if (request == 0x5421) {
            if (argp) {
                *(int *)argp = 0; // 0 bytes available
            }
            return 0;
        }

        // 36-byte IPI read (receive from R5)
        if ((request & 0xFFFF) == 0x2000 && (request & 0x80000000)) {
            // Return EAGAIN (no messages currently queued from R5)
            errno = EAGAIN;
            return -1;
        }

        // 36-byte IPI write / exchange (send to R5)
        if ((request & 0xFFFF) == 0x2001 || (request & 0xFFFF) == 0x2000) {
            unsigned char *pkt = (unsigned char *)argp;
            if (pkt) {
                hex_dump("IPI Outgoing Message from video_pipeline", pkt, 36);
                uint32_t *words = (uint32_t *)pkt;
                printf("[INTERCEPTOR] IPI Packet Words:\n");
                for (int i = 0; i < 9; i++) {
                    printf("  Word[%d] = 0x%08X (%u)\n", i, words[i], words[i]);
                }
            }
            return 0;
        }

        return 0;
    }

    return real_ioctl(fd, request, argp);
}

ssize_t write(int fd, const void *buf, size_t count) {
    init_hooks();
    if (fd == g_fake_copro_fd) {
        hex_dump("Direct Write to copro", (const unsigned char *)buf, count);
        return count;
    }
    return real_write(fd, buf, count);
}

ssize_t read(int fd, void *buf, size_t count) {
    init_hooks();
    if (fd == g_fake_copro_fd) {
        fprintf(stderr, "[INTERCEPTOR] Read requested on copro (count=%zu)\n", count);
        return 0; // EOF or no data
    }
    return real_read(fd, buf, count);
}
