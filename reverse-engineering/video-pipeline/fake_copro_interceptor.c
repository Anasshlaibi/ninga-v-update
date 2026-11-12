#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

#include "../../recording-engine/atomos_copro_abi.h"

/*
 * fake_copro_interceptor.c — AtomOS /dev/copro_comms* LD_PRELOAD Snooper,
 * Forwarder & Offline Mock
 *
 * Modes (controlled via environment variables):
 *   - Default (live hardware passthrough snooping): forwards open/openat/close/ioctl
 *     directly to libc and /dev/copro_comms*, logging decoded 36-byte
 *     atomos_copro_msg frames (RX/TX/PREPARE_DMABUF) plus DMA-Heap / Custom-CMA /
 *     Allegro VCU ioctl traffic on stderr.
 *   - COPRO_FWD_SOCK=<unix_path>: when set on live RX (GET_MESSAGE rc == 0),
 *     forwards the 36-byte atomos_copro_msg + SCM_RIGHTS dma_fd (if >= 0) over a
 *     non-blocking AF_UNIX SOCK_SEQPACKET socket (e.g. to vraw_daemon --fwd-sock).
 *     Kernel dma_buf refcount stays elevated until both video_pipeline and the
 *     receiver close their FDs (preventing premature flags=0xC0 release to R5).
 *   - COPRO_MOCK=1 (offline QEMU emulation): stubs /dev/copro_comms* and
 *     /dev/allegroIP opens to /dev/null, returns EAGAIN on RX (25 ms sleep),
 *     and dumps outgoing TX packets without needing real hardware.
 *   - COPRO_LOG_EAGAIN=1: include empty EAGAIN RX polls in stderr logs.
 *   - COPRO_VERBOSE=1: also dump raw 36-byte hex & 9 uint32 words per CoPro ioctl.
 *
 * Build for Ninja V (AArch64):
 *   aarch64-linux-gnu-gcc -shared -fPIC -O2 -Wall -Wextra -Werror \
 *       -I../../recording-engine -o libfakecopro.so fake_copro_interceptor.c -ldl
 */

enum tracked_dev_kind {
    DEV_NONE       = 0,
    DEV_COPRO      = 1,
    DEV_DMA_HEAP   = 2,
    DEV_CUSTOM_CMA = 3,
    DEV_ALLEGRO    = 4,
    DEV_DMAPROXY   = 5,
};

#define MAX_TRACKED_FDS 4096

static int g_tracked_fd[MAX_TRACKED_FDS];
static int g_mock_mode = 0;
static int g_log_eagain = 0;
static int g_verbose = 0;
static char g_fwd_sock_path[108];
static int g_fwd_fd = -1;
static unsigned char g_fwd_lock = 0;

static int (*real_open)(const char *pathname, int flags, ...) = NULL;
static int (*real_open64)(const char *pathname, int flags, ...) = NULL;
static int (*real_openat)(int dirfd, const char *pathname, int flags, ...) = NULL;
static int (*real_openat64)(int dirfd, const char *pathname, int flags, ...) = NULL;
static int (*real_close)(int fd) = NULL;
static int (*real_dup)(int oldfd) = NULL;
static int (*real_dup2)(int oldfd, int newfd) = NULL;
static int (*real_dup3)(int oldfd, int newfd, int flags) = NULL;
static int (*real_ioctl)(int fd, unsigned long request, ...) = NULL;
static ssize_t (*real_read)(int fd, void *buf, size_t count) = NULL;
static ssize_t (*real_write)(int fd, const void *buf, size_t count) = NULL;

__attribute__((constructor))
static void init_hooks(void) {
    static int initialized = 0;
    if (__atomic_load_n(&initialized, __ATOMIC_ACQUIRE)) {
        return;
    }

    real_open     = dlsym(RTLD_NEXT, "open");
    real_open64   = dlsym(RTLD_NEXT, "open64");
    real_openat   = dlsym(RTLD_NEXT, "openat");
    real_openat64 = dlsym(RTLD_NEXT, "openat64");
    real_close    = dlsym(RTLD_NEXT, "close");
    real_dup      = dlsym(RTLD_NEXT, "dup");
    real_dup2     = dlsym(RTLD_NEXT, "dup2");
    real_dup3     = dlsym(RTLD_NEXT, "dup3");
    real_ioctl    = dlsym(RTLD_NEXT, "ioctl");
    real_read     = dlsym(RTLD_NEXT, "read");
    real_write    = dlsym(RTLD_NEXT, "write");

    const char *env_mock = getenv("COPRO_MOCK");
    g_mock_mode = (env_mock && strcmp(env_mock, "1") == 0);

    const char *env_eagain = getenv("COPRO_LOG_EAGAIN");
    g_log_eagain = (env_eagain && strcmp(env_eagain, "1") == 0);

    const char *env_verbose = getenv("COPRO_VERBOSE");
    g_verbose = (env_verbose && strcmp(env_verbose, "1") == 0);

    const char *env_fwd = getenv("COPRO_FWD_SOCK");
    if (env_fwd && env_fwd[0] != '\0' && strlen(env_fwd) < sizeof(g_fwd_sock_path)) {
        memcpy(g_fwd_sock_path, env_fwd, strlen(env_fwd) + 1);
    }

    __atomic_store_n(&initialized, 1, __ATOMIC_RELEASE);
    fprintf(stderr,
            "[COPRO_SNOOP] Initialized (mode=%s, log_eagain=%d, verbose=%d, fwd_sock=%s)\n",
            g_mock_mode ? "MOCK" : "PASSTHROUGH", g_log_eagain, g_verbose,
            g_fwd_sock_path[0] ? g_fwd_sock_path : "none");
}

static void fwd_lock_acquire(void) {
    while (__atomic_test_and_set(&g_fwd_lock, __ATOMIC_ACQUIRE)) {
        /* spin briefly on rare concurrent RX */
    }
}

static void fwd_lock_release(void) {
    __atomic_clear(&g_fwd_lock, __ATOMIC_RELEASE);
}

static void forward_copro_msg(const struct atomos_copro_msg *m) {
    if (!g_fwd_sock_path[0] || !m) {
        return;
    }

    struct atomos_copro_msg copy;
    memcpy(&copy, m, sizeof(copy));

    fwd_lock_acquire();

    if (g_fwd_fd < 0) {
        int s = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (s >= 0) {
            struct sockaddr_un addr;
            memset(&addr, 0, sizeof(addr));
            addr.sun_family = AF_UNIX;
            memcpy(addr.sun_path, g_fwd_sock_path, strlen(g_fwd_sock_path) + 1);
            if (connect(s, (const struct sockaddr *)&addr, sizeof(addr)) == 0) {
                g_fwd_fd = s;
                fprintf(stderr, "[COPRO_FWD] Connected to %s (fd=%d)\n",
                        g_fwd_sock_path, g_fwd_fd);
            } else {
                real_close(s);
            }
        }
    }

    if (g_fwd_fd >= 0) {
        struct iovec iov;
        iov.iov_base = &copy;
        iov.iov_len = sizeof(copy);

        struct msghdr hdr;
        memset(&hdr, 0, sizeof(hdr));
        hdr.msg_iov = &iov;
        hdr.msg_iovlen = 1;

        union {
            char buf[CMSG_SPACE(sizeof(int))];
            struct cmsghdr align;
        } u;

        if (copy.dma_fd >= 0) {
            memset(&u, 0, sizeof(u));
            hdr.msg_control = u.buf;
            hdr.msg_controllen = sizeof(u.buf);
            struct cmsghdr *cmsg = CMSG_FIRSTHDR(&hdr);
            cmsg->cmsg_level = SOL_SOCKET;
            cmsg->cmsg_type = SCM_RIGHTS;
            cmsg->cmsg_len = CMSG_LEN(sizeof(int));
            memcpy(CMSG_DATA(cmsg), &copy.dma_fd, sizeof(int));
        }

        if (sendmsg(g_fwd_fd, &hdr, MSG_NOSIGNAL | MSG_DONTWAIT) < 0) {
            int err = errno;
            if (err != EAGAIN && err != EWOULDBLOCK) {
                real_close(g_fwd_fd);
                g_fwd_fd = -1;
            }
        }
    }

    fwd_lock_release();
}

static enum tracked_dev_kind classify_path(const char *path) {
    if (!path) return DEV_NONE;
    if (strstr(path, "copro_comms") != NULL) return DEV_COPRO;
    if (strstr(path, "dma_heap") != NULL) return DEV_DMA_HEAP;
    if (strstr(path, "custom_cma") != NULL) return DEV_CUSTOM_CMA;
    if (strstr(path, "allegro") != NULL) return DEV_ALLEGRO;
    if (strstr(path, "dmaproxy") != NULL) return DEV_DMAPROXY;
    return DEV_NONE;
}

static void set_tracked_fd(int fd, enum tracked_dev_kind kind) {
    if (fd >= 0 && fd < MAX_TRACKED_FDS) {
        __atomic_store_n(&g_tracked_fd[fd], (int)kind, __ATOMIC_RELAXED);
    }
}

static enum tracked_dev_kind get_tracked_fd(int fd) {
    if (fd >= 0 && fd < MAX_TRACKED_FDS) {
        return (enum tracked_dev_kind)__atomic_load_n(&g_tracked_fd[fd], __ATOMIC_RELAXED);
    }
    return DEV_NONE;
}

static void dump_copro_msg(const char *tag, int fd, int rc, int saved_errno,
                           const struct atomos_copro_msg *m) {
    if (!m) {
        fprintf(stderr, "[%s] fd=%d rc=%d errno=%d arg=NULL\n",
                tag, fd, rc, saved_errno);
        return;
    }

    struct atomos_copro_msg msg;
    memcpy(&msg, m, sizeof(msg));

    fprintf(stderr,
            "[%s] fd=%d rc=%d type=%s(0x%04X) dma_fd=%d flags=0x%02X rsv=0x%02X "
            "phys=0x%08X size=%u",
            tag, fd, rc, atomos_copro_msg_name(msg.msg_type), msg.msg_type,
            msg.dma_fd, msg.flags, msg.reserved0, msg.phys_addr, msg.size);

    switch (msg.msg_type) {
    case ATOMOS_COPRO_MSG_FRAME_V1:
        fprintf(stderr, " | frameId=%u id=%u meta=0x%02X/0x%02X/0x%04X",
                msg.payload.frame_v1.frame_id_word & 0x7FFFU,
                msg.payload.frame_v1.debug_id,
                msg.payload.frame_v1.meta_flags,
                msg.payload.frame_v1.meta_b1,
                msg.payload.frame_v1.meta_u16);
        break;
    case ATOMOS_COPRO_MSG_FRAME_V2:
        fprintf(stderr, " | frameId=%u id=%u pts=%u dts=%u",
                msg.payload.frame_v2.frame_id_word & 0x7FFFU,
                msg.payload.frame_v2.debug_id,
                msg.payload.frame_v2.pts,
                msg.payload.frame_v2.dts);
        break;
    case ATOMOS_COPRO_MSG_VIDEO_CONFIG:
    case ATOMOS_COPRO_MSG_STREAMING_CONFIG:
    case ATOMOS_COPRO_MSG_NDI_CONNECT_SRC: {
        uint32_t cfg_off = msg.payload.dmabuf_ref.struct_offset;
        uint32_t cfg_len = msg.payload.dmabuf_ref.struct_len;
        fprintf(stderr, " | id=%u cfg_off=%u cfg_len=%u",
                msg.payload.dmabuf_ref.debug_id, cfg_off, cfg_len);

        if (rc == 0 && !g_mock_mode && msg.dma_fd >= 0 && cfg_len > 0 &&
            (msg.msg_type == ATOMOS_COPRO_MSG_VIDEO_CONFIG ||
             msg.msg_type == ATOMOS_COPRO_MSG_STREAMING_CONFIG)) {
            struct atomos_mapped_region reg;
            if (atomos_mmap_aligned(msg.dma_fd, cfg_off, cfg_len,
                                    PROT_READ, MAP_SHARED, &reg) == 0) {
                if (msg.msg_type == ATOMOS_COPRO_MSG_VIDEO_CONFIG &&
                    cfg_len >= ATOMOS_MSG_VIDEO_CONFIG_SIZE) {
                    struct atomos_msg_video_config vc;
                    memcpy(&vc, reg.data, sizeof(vc));
                    fprintf(stderr, " {res=%u dir=%u mode=%u %ux%u%c @%u/%u fmt=0x%02X col=0x%04X}",
                            vc.result, vc.direction, vc.video_mode,
                            vc.width, vc.height, vc.interlaced ? 'i' : 'p',
                            vc.fps_num, vc.fps_den, vc.format_flags, vc.colorimetry);
                } else if (msg.msg_type == ATOMOS_COPRO_MSG_STREAMING_CONFIG &&
                           cfg_len >= ATOMOS_MSG_STREAMING_CONFIG_SIZE) {
                    struct atomos_msg_streaming_config sc;
                    memcpy(&sc, reg.data, sizeof(sc));
                    fprintf(stderr, " {res=%u dir=%u %ux%u%c @%u/%u proto=%u key=\"%.32s\"}",
                            sc.result, sc.direction,
                            sc.width, sc.height, sc.interlaced ? 'i' : 'p',
                            sc.fps_num, sc.fps_den, sc.stream_proto, sc.stream_key_or_url);
                }
                atomos_munmap_aligned(&reg);
            }
        }
        break;
    }
    default:
        fprintf(stderr, " | payload=");
        for (size_t i = 0; i < sizeof(msg.payload.raw); i++) {
            fprintf(stderr, "%02X%s", msg.payload.raw[i],
                    (i + 1 < sizeof(msg.payload.raw)) ? " " : "");
        }
        break;
    }
    fprintf(stderr, "\n");

    if (g_verbose) {
        const uint8_t *raw = (const uint8_t *)&msg;
        uint32_t w[9];
        memcpy(w, &msg, sizeof(w));
        fprintf(stderr, "  RAW36:");
        for (size_t i = 0; i < sizeof(msg); i++) {
            fprintf(stderr, " %02X", raw[i]);
        }
        fprintf(stderr, "\n  WORDS:");
        for (size_t i = 0; i < sizeof(w) / sizeof(w[0]); i++) {
            fprintf(stderr, " [%zu]=0x%08X", i, w[i]);
        }
        fprintf(stderr, "\n");
    }
}

static int needs_open_mode(int flags) {
    if (flags & O_CREAT) return 1;
#ifdef O_TMPFILE
    if ((flags & O_TMPFILE) == O_TMPFILE) return 1;
#endif
    return 0;
}

static int handle_open_common(const char *pathname, int flags, mode_t mode,
                              int has_mode, int dirfd, int is_64, int is_at) {
    init_hooks();
    enum tracked_dev_kind kind = classify_path(pathname);

    if (g_mock_mode && (kind == DEV_COPRO || kind == DEV_ALLEGRO)) {
        int fd = real_open("/dev/null", O_RDWR | (flags & O_CLOEXEC));
        if (fd >= 0) {
            set_tracked_fd(fd, kind);
        }
        fprintf(stderr, "[COPRO_MOCK] open%s(\"%s\", 0x%x) -> mock fd=%d\n",
                is_at ? (is_64 ? "at64" : "at") : (is_64 ? "64" : ""),
                pathname, flags, fd);
        return fd;
    }

    int fd = -1;
    if (is_at) {
        if (is_64 && real_openat64) {
            fd = has_mode ? real_openat64(dirfd, pathname, flags, mode)
                          : real_openat64(dirfd, pathname, flags);
        } else {
            fd = has_mode ? real_openat(dirfd, pathname, flags, mode)
                          : real_openat(dirfd, pathname, flags);
        }
    } else {
        if (is_64 && real_open64) {
            fd = has_mode ? real_open64(pathname, flags, mode)
                          : real_open64(pathname, flags);
        } else {
            fd = has_mode ? real_open(pathname, flags, mode)
                          : real_open(pathname, flags);
        }
    }

    if (fd >= 0 && kind != DEV_NONE) {
        set_tracked_fd(fd, kind);
        fprintf(stderr, "[COPRO_SNOOP] open(\"%s\", 0x%x) -> fd=%d (kind=%d)\n",
                pathname, flags, fd, (int)kind);
    }
    return fd;
}

int open(const char *pathname, int flags, ...) {
    mode_t mode = 0;
    int has_mode = needs_open_mode(flags);
    if (has_mode) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return handle_open_common(pathname, flags, mode, has_mode, AT_FDCWD, 0, 0);
}

int open64(const char *pathname, int flags, ...) {
    mode_t mode = 0;
    int has_mode = needs_open_mode(flags);
    if (has_mode) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return handle_open_common(pathname, flags, mode, has_mode, AT_FDCWD, 1, 0);
}

int openat(int dirfd, const char *pathname, int flags, ...) {
    mode_t mode = 0;
    int has_mode = needs_open_mode(flags);
    if (has_mode) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return handle_open_common(pathname, flags, mode, has_mode, dirfd, 0, 1);
}

int openat64(int dirfd, const char *pathname, int flags, ...) {
    mode_t mode = 0;
    int has_mode = needs_open_mode(flags);
    if (has_mode) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return handle_open_common(pathname, flags, mode, has_mode, dirfd, 1, 1);
}

int dup(int oldfd) {
    init_hooks();
    int newfd = real_dup(oldfd);
    if (newfd >= 0) {
        set_tracked_fd(newfd, get_tracked_fd(oldfd));
    }
    return newfd;
}

int dup2(int oldfd, int newfd) {
    init_hooks();
    int rc = real_dup2(oldfd, newfd);
    if (rc >= 0) {
        set_tracked_fd(rc, get_tracked_fd(oldfd));
    }
    return rc;
}

int dup3(int oldfd, int newfd, int flags) {
    init_hooks();
    int rc = real_dup3(oldfd, newfd, flags);
    if (rc >= 0) {
        set_tracked_fd(rc, get_tracked_fd(oldfd));
    }
    return rc;
}

int close(int fd) {
    init_hooks();
    enum tracked_dev_kind kind = get_tracked_fd(fd);
    if (kind != DEV_NONE) {
        fprintf(stderr, "[COPRO_SNOOP] close(fd=%d, kind=%d)\n", fd, (int)kind);
        set_tracked_fd(fd, DEV_NONE);
    }
    return real_close(fd);
}

int ioctl(int fd, unsigned long request, ...) {
    init_hooks();
    va_list args;
    va_start(args, request);
    void *argp = va_arg(args, void *);
    va_end(args);

    enum tracked_dev_kind kind = get_tracked_fd(fd);
    unsigned long req_u32 = request & 0xFFFFFFFFUL;

    if (g_mock_mode && (kind == DEV_COPRO || kind == DEV_ALLEGRO)) {
        if (req_u32 == ATOMOS_COPRO_IOC_GET_MESSAGE) {
            usleep(25000);
            errno = EAGAIN;
            return -1;
        }
        if (req_u32 == ATOMOS_COPRO_IOC_SEND_MESSAGE ||
            req_u32 == ATOMOS_COPRO_IOC_PREPARE_DMABUF) {
            dump_copro_msg(req_u32 == ATOMOS_COPRO_IOC_SEND_MESSAGE ? "COPRO_MOCK_TX" : "COPRO_MOCK_PREP",
                           fd, 0, 0, (const struct atomos_copro_msg *)argp);
            return 0;
        }
        return 0;
    }

    if (req_u32 == ATOMOS_COPRO_IOC_SEND_MESSAGE) {
        struct atomos_copro_msg tx_copy;
        if (argp) {
            memcpy(&tx_copy, argp, sizeof(tx_copy));
        }
        int rc = real_ioctl(fd, request, argp);
        int saved = errno;
        dump_copro_msg("COPRO_TX", fd, rc, saved, argp ? &tx_copy : NULL);
        errno = saved;
        return rc;
    }

    int rc = real_ioctl(fd, request, argp);
    int saved = errno;

    if (req_u32 == ATOMOS_COPRO_IOC_GET_MESSAGE) {
        if (rc == 0) {
            if (argp) {
                forward_copro_msg((const struct atomos_copro_msg *)argp);
            }
            dump_copro_msg("COPRO_RX", fd, rc, 0, (const struct atomos_copro_msg *)argp);
        } else if (g_log_eagain || saved != EAGAIN) {
            fprintf(stderr, "[COPRO_RX] fd=%d rc=%d errno=%d (%s)\n",
                    fd, rc, saved, strerror(saved));
        }
    } else if (req_u32 == ATOMOS_COPRO_IOC_PREPARE_DMABUF) {
        dump_copro_msg("COPRO_PREP", fd, rc, saved, (const struct atomos_copro_msg *)argp);
    } else if (req_u32 == DMA_HEAP_IOCTL_ALLOC) {
        const struct atomos_dma_heap_allocation_data *h =
            (const struct atomos_dma_heap_allocation_data *)argp;
        if (h) {
            fprintf(stderr,
                    "[DMA_HEAP_ALLOC] fd=%d rc=%d len=%llu dma_fd=%u fd_flags=0x%X heap_flags=0x%llX\n",
                    fd, rc, (unsigned long long)h->len, h->fd,
                    h->fd_flags, (unsigned long long)h->heap_flags);
        }
    } else if (req_u32 == ATOMOS_CUSTOM_CMA_IOC_GET_REGION ||
               req_u32 == ATOMOS_CUSTOM_CMA_IOC_RESIZE) {
        const struct atomos_custom_cma_region *r =
            (const struct atomos_custom_cma_region *)argp;
        if (r) {
            fprintf(stderr, "[CUSTOM_CMA] fd=%d req=0x%08lX rc=%d name=\"%.31s\" base=0x%llX size=0x%llX\n",
                    fd, req_u32, rc, r->name,
                    (unsigned long long)r->base, (unsigned long long)r->size);
        }
    } else if (kind != DEV_NONE && req_u32 != DMA_BUF_IOCTL_SYNC) {
        fprintf(stderr, "[DEV_IOCTL] kind=%d fd=%d req=0x%08lX argp=%p rc=%d errno=%d\n",
                (int)kind, fd, req_u32, argp, rc, saved);
    }

    errno = saved;
    return rc;
}

ssize_t write(int fd, const void *buf, size_t count) {
    init_hooks();
    if (g_mock_mode && get_tracked_fd(fd) == DEV_COPRO) {
        fprintf(stderr, "[COPRO_MOCK_WRITE] fd=%d count=%zu\n", fd, count);
        return (ssize_t)count;
    }
    return real_write(fd, buf, count);
}

ssize_t read(int fd, void *buf, size_t count) {
    init_hooks();
    if (g_mock_mode && get_tracked_fd(fd) == DEV_COPRO) {
        fprintf(stderr, "[COPRO_MOCK_READ] fd=%d count=%zu -> 0\n", fd, count);
        return 0;
    }
    return real_read(fd, buf, count);
}
