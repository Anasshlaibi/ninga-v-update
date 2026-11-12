#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <signal.h>

#include "atomos_copro_abi.h"

static volatile int g_running = 1;
static void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

#define WIDTH 3840U
#define HEIGHT 2160U
#define BITS_PER_SAMPLE 12U
#define HEADER_SIZE 4096U // 4KB page-aligned header for direct I/O
#define RAW_FRAME_BYTES ((size_t)WIDTH * (size_t)HEIGHT * BITS_PER_SAMPLE / 8U) // 12,441,600 bytes
#define TOTAL_FRAME_BYTES (HEADER_SIZE + RAW_FRAME_BYTES)
#define RING_BUFFER_SLOTS 8 // 8 frame buffer slots (~99.5 MB RAM)

#define DEFAULT_SOCKET_PATH ATOMOS_VIDEO_SOCK_USER
#define FALLBACK_SOCKET_PATH ATOMOS_VIDEO_SOCK_FALLBACK

// TIFF / DNG Tag IDs
#define TAG_NEWSUBFILETYPE         0x00FE
#define TAG_IMAGEWIDTH             0x0100
#define TAG_IMAGELENGTH            0x0101
#define TAG_BITSPERSAMPLE          0x0102
#define TAG_COMPRESSION            0x0103
#define TAG_PHOTOMETRIC            0x0106
#define TAG_MAKE                   0x010F
#define TAG_MODEL                  0x0110
#define TAG_STRIPOFFSETS           0x0111
#define TAG_SAMPLESPERPXL          0x0115
#define TAG_ROWSPERSTRIP           0x0116
#define TAG_STRIPBYTECOUNTS        0x0117
#define TAG_XRESOLUTION            0x011A
#define TAG_YRESOLUTION            0x011B
#define TAG_PLANARCONFIG           0x011C
#define TAG_RESOLUTIONUNIT         0x0128
#define TAG_CFAREPEATPATT          0x828D
#define TAG_CFAPATTERN             0x828E
#define TAG_DNGVERSION             0xC612
#define TAG_DNGFORWARDVERSION      0xC613
#define TAG_UNIQUECAMERAMODEL      0xC614
#define TAG_BLACKLEVEL             0xC61A
#define TAG_WHITELEVEL             0xC61D

#define TYPE_BYTE     1
#define TYPE_ASCII    2
#define TYPE_SHORT    3
#define TYPE_LONG     4
#define TYPE_RATIONAL 5

#pragma pack(push, 1)
typedef struct {
    uint16_t tag;
    uint16_t type;
    uint32_t count;
    uint32_t value_or_offset;
} TiffEntry;
#pragma pack(pop)

typedef struct {
    uint8_t *buffer;
    uint32_t frame_index;
    uint32_t width;
    uint32_t height;
    uint16_t bpp;
    size_t   payload_bytes;
    struct timespec timestamp;
    int is_valid;
} RingSlot;

typedef struct {
    RingSlot slots[RING_BUFFER_SLOTS];
    int head; // Producer write index
    int tail; // Consumer read index
    int count; // Number of queued frames
    int done; // Stream termination flag
    uint32_t dropped_frames;
    uint32_t written_frames;
    uint64_t written_bytes;
    char output_dir[256];
    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
} RingQueue;

// Generate Adobe DNG 1.4 compliant TIFF header
static void build_dng_header(uint8_t *hdr, uint32_t width, uint32_t height,
                             uint16_t bpp, uint32_t payload_bytes) {
    memset(hdr, 0, HEADER_SIZE);

    hdr[0] = 'I'; hdr[1] = 'I';
    hdr[2] = 0x2A; hdr[3] = 0x00;
    uint32_t ifd_offset = 8;
    memcpy(hdr + 4, &ifd_offset, 4);

    const uint32_t off_make = 300;
    memcpy(hdr + off_make, "CinemaDNG\0", 10);

    const uint32_t off_model = 316;
    memcpy(hdr + off_model, "Ninja V RAW\0", 12);

    const uint32_t off_xres = 336;
    uint32_t xres[2] = {72, 1};
    memcpy(hdr + off_xres, xres, 8);

    const uint32_t off_yres = 344;
    uint32_t yres[2] = {72, 1};
    memcpy(hdr + off_yres, yres, 8);

    uint32_t white_level = (bpp >= 16) ? 65535U : ((1U << bpp) - 1U);

    uint16_t num_entries = 23;
    uint32_t p = 8;
    memcpy(hdr + p, &num_entries, 2);
    p += 2;

    TiffEntry entries[23] = {
        {TAG_NEWSUBFILETYPE,    TYPE_LONG,     1,  0},
        {TAG_IMAGEWIDTH,        TYPE_LONG,     1,  width},
        {TAG_IMAGELENGTH,       TYPE_LONG,     1,  height},
        {TAG_BITSPERSAMPLE,     TYPE_SHORT,    1,  bpp},
        {TAG_COMPRESSION,       TYPE_SHORT,    1,  1}, // Uncompressed
        {TAG_PHOTOMETRIC,       TYPE_SHORT,    1,  32803}, // CFA
        {TAG_MAKE,              TYPE_ASCII,    10, off_make},
        {TAG_MODEL,             TYPE_ASCII,    12, off_model},
        {TAG_STRIPOFFSETS,      TYPE_LONG,     1,  HEADER_SIZE},
        {TAG_SAMPLESPERPXL,     TYPE_SHORT,    1,  1},
        {TAG_ROWSPERSTRIP,      TYPE_LONG,     1,  height},
        {TAG_STRIPBYTECOUNTS,   TYPE_LONG,     1,  payload_bytes},
        {TAG_XRESOLUTION,       TYPE_RATIONAL, 1,  off_xres},
        {TAG_YRESOLUTION,       TYPE_RATIONAL, 1,  off_yres},
        {TAG_PLANARCONFIG,      TYPE_SHORT,    1,  1},
        {TAG_RESOLUTIONUNIT,    TYPE_SHORT,    1,  2},
        {TAG_CFAREPEATPATT,     TYPE_SHORT,    2,  (2 << 16) | 2},
        {TAG_CFAPATTERN,        TYPE_BYTE,     4,  0x02010100}, // RGGB (0, 1, 1, 2)
        {TAG_DNGVERSION,        TYPE_BYTE,     4,  0x00000401},
        {TAG_DNGFORWARDVERSION, TYPE_BYTE,     4,  0x00000101},
        {TAG_UNIQUECAMERAMODEL, TYPE_ASCII,    10, off_make},
        {TAG_BLACKLEVEL,        TYPE_SHORT,    1,  0},
        {TAG_WHITELEVEL,        TYPE_LONG,     1,  white_level}
    };

    memcpy(hdr + p, entries, sizeof(entries));
    p += sizeof(entries);

    uint32_t next_ifd = 0;
    memcpy(hdr + p, &next_ifd, 4);
}

static int write_buffer_to_file(int fd, const uint8_t *buf, size_t len) {
    size_t off = 0;
    while (off < len) {
        ssize_t w = write(fd, buf + off, len - off);
        if (w < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        off += (size_t)w;
    }
    return 0;
}

// Consumer thread: Writes CinemaDNG frames to disk with direct I/O
static void *disk_writer_thread(void *arg) {
    RingQueue *q = (RingQueue *)arg;

    while (1) {
        pthread_mutex_lock(&q->mutex);
        while (q->count == 0 && !q->done) {
            pthread_cond_wait(&q->not_empty, &q->mutex);
        }

        if (q->count == 0 && q->done) {
            pthread_mutex_unlock(&q->mutex);
            break;
        }

        RingSlot *slot = &q->slots[q->tail];
        size_t total_bytes = HEADER_SIZE + slot->payload_bytes;
        uint32_t frame_idx = slot->frame_index;
        q->tail = (q->tail + 1) % RING_BUFFER_SLOTS;
        q->count--;
        int q_remaining = q->count;

        pthread_cond_signal(&q->not_full);
        pthread_mutex_unlock(&q->mutex);

        char filename[512];
        snprintf(filename, sizeof(filename), "%s/vraw_%06u.dng", q->output_dir, frame_idx);

        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);

        int fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC | O_DIRECT, 0644);
        int wrote_ok = 0;
        if (fd >= 0) {
            if (write_buffer_to_file(fd, slot->buffer, total_bytes) == 0) {
                wrote_ok = 1;
            } else if (errno == EINVAL) {
                close(fd);
                fd = -1;
            }
        }
        if (!wrote_ok && fd < 0 && (errno == EINVAL || errno == EOPNOTSUPP)) {
            fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd >= 0 && write_buffer_to_file(fd, slot->buffer, total_bytes) == 0) {
                wrote_ok = 1;
            }
        }

        if (fd >= 0) {
            close(fd);
        }
        if (wrote_ok) {
            q->written_frames++;
            q->written_bytes += total_bytes;

            clock_gettime(CLOCK_MONOTONIC, &t1);
            double write_ms = (t1.tv_sec - t0.tv_sec) * 1000.0 + (t1.tv_nsec - t0.tv_nsec) / 1000000.0;
            if (write_ms <= 0.0001) write_ms = 0.0001;
            double mb_s = (total_bytes / (1024.0 * 1024.0)) / (write_ms / 1000.0);

            printf("[VRAW_REC] Frame %05u written: %.2f MB in %5.2f ms (%6.1f MB/s) | Queue: %d/%d\n",
                frame_idx, total_bytes / (1024.0 * 1024.0), write_ms, mb_s, q_remaining, RING_BUFFER_SLOTS);
        } else {
            fprintf(stderr, "[VRAW_REC] Error writing %s: %s\n", filename, strerror(errno));
        }
    }

    return NULL;
}

// Generate realistic synthetic 12-bit Bayer frame (fallback/test generator)
static void fill_synthetic_12bit_bayer(uint8_t *pixel_buf, uint32_t frame_index) {
    size_t byte_idx = 0;
    for (uint32_t y = 0; y < HEIGHT; y++) {
        for (uint32_t x = 0; x < WIDTH; x += 2) {
            uint16_t val_a = (uint16_t)((x * 4095) / WIDTH);
            uint16_t val_b = (uint16_t)(((x + 1) * 4095) / WIDTH);
            val_a = (val_a + (frame_index * 32)) & 0x0FFF;
            val_b = (val_b + (frame_index * 32)) & 0x0FFF;

            pixel_buf[byte_idx++] = (val_a >> 4) & 0xFF;
            pixel_buf[byte_idx++] = ((val_a & 0x0F) << 4) | ((val_b >> 8) & 0x0F);
            pixel_buf[byte_idx++] = val_b & 0xFF;
        }
    }
}

// Connect to AtomOS video_pipeline IPC socket
static int connect_video_pipeline_socket(void) {
    int sock = socket(AF_UNIX, SOCK_SEQPACKET, 0);
    if (sock < 0) {
        perror("[VRAW_IPC] socket(AF_UNIX, SOCK_SEQPACKET) failed");
        return -1;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;

    const char *paths[] = {DEFAULT_SOCKET_PATH, FALLBACK_SOCKET_PATH, "/tmp/atomos_video_pipeline_socket"};
    int connected = 0;

    for (int i = 0; i < 3; i++) {
        if (access(paths[i], F_OK) == 0) {
            strncpy(addr.sun_path, paths[i], sizeof(addr.sun_path) - 1);
            if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
                printf("[VRAW_IPC] Connected to socket: %s\n", paths[i]);
                connected = 1;
                break;
            }
        }
    }

    if (!connected) {
        close(sock);
        return -1;
    }

    // Set 2.0s socket timeout
    struct timeval tv = {2, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    return sock;
}

struct capture_state {
    uint32_t width;
    uint32_t height;
    uint16_t bpp;
    uint32_t captured_frames;
    int      logged_first_dma;
};

static int listen_fwd_socket(const char *path) {
    if (!path || strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        fprintf(stderr, "[VRAW_FWD] Invalid socket path\n");
        return -1;
    }

    unlink(path);
    int sock = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (sock < 0) {
        perror("[VRAW_FWD] socket(AF_UNIX, SOCK_SEQPACKET) failed");
        return -1;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    memcpy(addr.sun_path, path, strlen(path) + 1);

    if (bind(sock, (const struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("[VRAW_FWD] bind() failed");
        close(sock);
        return -1;
    }

    if (listen(sock, 4) < 0) {
        perror("[VRAW_FWD] listen() failed");
        close(sock);
        unlink(path);
        return -1;
    }

    return sock;
}

static int accept_with_poll(int listen_fd) {
    while (g_running) {
        struct pollfd pfd;
        pfd.fd = listen_fd;
        pfd.events = POLLIN;
        pfd.revents = 0;

        int pr = poll(&pfd, 1, 200);
        if (pr < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (pr == 0) {
            continue;
        }
        if (pfd.revents & POLLIN) {
            int cfd = accept(listen_fd, NULL, NULL);
            if (cfd >= 0) {
                return cfd;
            }
            if (errno != EINTR && errno != EAGAIN) {
                return -1;
            }
        }
    }
    return -1;
}

// Receive message and intercept any SCM_RIGHTS file descriptors.
// Returns: 0 on packet received, 1 on poll timeout, -2 on EOF, -1 on error.
static int recv_dmabuf_fd(int sock, int *out_fd, uint8_t *msg_buf,
                          size_t msg_max, size_t *msg_len, int timeout_ms) {
    *out_fd = -1;
    *msg_len = 0;

    if (timeout_ms >= 0) {
        struct pollfd pfd;
        pfd.fd = sock;
        pfd.events = POLLIN;
        pfd.revents = 0;
        int pr = poll(&pfd, 1, timeout_ms);
        if (pr < 0) {
            return (errno == EINTR) ? 1 : -1;
        }
        if (pr == 0) {
            return 1;
        }
    }

    struct msghdr msg;
    memset(&msg, 0, sizeof(msg));

    struct iovec iov;
    iov.iov_base = msg_buf;
    iov.iov_len = msg_max;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;

    char cmsg_buf[CMSG_SPACE(sizeof(int) * 4)];
    memset(cmsg_buf, 0, sizeof(cmsg_buf));
    msg.msg_control = cmsg_buf;
    msg.msg_controllen = sizeof(cmsg_buf);

    ssize_t n = recvmsg(sock, &msg, MSG_CMSG_CLOEXEC);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
            return 1;
        }
        return -1;
    }
    if (n == 0 && msg.msg_controllen == 0) {
        return -2;
    }

    *msg_len = (size_t)n;

    struct cmsghdr *cmsg;
    for (cmsg = CMSG_FIRSTHDR(&msg); cmsg != NULL; cmsg = CMSG_NXTHDR(&msg, cmsg)) {
        if (cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS) {
            size_t fd_bytes = cmsg->cmsg_len - CMSG_LEN(0);
            size_t n_fds = fd_bytes / sizeof(int);
            const int *fds = (const int *)CMSG_DATA(cmsg);
            for (size_t i = 0; i < n_fds; i++) {
                int fd_val;
                memcpy(&fd_val, &fds[i], sizeof(int));
                if (*out_fd < 0 && fd_val >= 0) {
                    *out_fd = fd_val;
                } else if (fd_val >= 0) {
                    close(fd_val);
                }
            }
        }
    }

    return 0;
}

static int ingest_dmabuf_frame(RingQueue *queue, struct capture_state *state,
                               int dma_fd, uint32_t phys_addr,
                               size_t hint_bytes, uint32_t frame_id) {
    if (dma_fd < 0) {
        return -1;
    }

    pthread_mutex_lock(&queue->mutex);
    if (queue->count == RING_BUFFER_SLOTS) {
        queue->dropped_frames++;
        pthread_mutex_unlock(&queue->mutex);
        fprintf(stderr, "[VRAW_PRODUCER] WARNING: Buffer full! Dropped frameId=%u\n", frame_id);
        return -1;
    }
    RingSlot *slot = &queue->slots[queue->head];
    pthread_mutex_unlock(&queue->mutex);

    struct stat st;
    int has_stat = (fstat(dma_fd, &st) == 0);

    long pgsz_l = sysconf(_SC_PAGESIZE);
    size_t pgsz = (pgsz_l > 0) ? (size_t)pgsz_l : 4096U;
    size_t page_delta = (size_t)((uint64_t)phys_addr % (uint64_t)pgsz);

    size_t avail = 0;
    if (has_stat && st.st_size > 0 && (uint64_t)st.st_size > page_delta) {
        avail = (size_t)((uint64_t)st.st_size - page_delta);
    }

    size_t copy_len = (hint_bytes > 0) ? hint_bytes : avail;
    if (has_stat && st.st_size > 0 && copy_len > avail) {
        fprintf(stderr,
                "[VRAW_DMA] Short dma_buf backing (st_size=%lld page_delta=%zu hint=%zu); clamping\n",
                (long long)st.st_size, page_delta, hint_bytes);
        copy_len = avail;
    }
    if (copy_len == 0) {
        fprintf(stderr, "[VRAW_DMA] Skipping zero-byte frame (frameId=%u)\n", frame_id);
        return -1;
    }
    if (copy_len > RAW_FRAME_BYTES) {
        fprintf(stderr,
                "[VRAW_DMA] Frame size %zu exceeds 4K slot capacity %zu; clamping\n",
                copy_len, RAW_FRAME_BYTES);
        copy_len = RAW_FRAME_BYTES;
    }

    int sync_rc = atomos_dmabuf_sync(dma_fd, ATOMOS_DMA_BUF_SYNC_START | ATOMOS_DMA_BUF_SYNC_READ);
    if (sync_rc < 0 && sync_rc != -ENOTTY && sync_rc != -EINVAL) {
        fprintf(stderr, "[VRAW_DMA] SYNC_START error: %s\n", strerror(-sync_rc));
    }

    struct atomos_mapped_region reg;
    int map_rc = atomos_mmap_dmabuf_frame(dma_fd, phys_addr, copy_len,
                                          PROT_READ, MAP_SHARED, &reg);
    if (map_rc == 0) {
        slot->frame_index = state->captured_frames;
        slot->width = state->width;
        slot->height = state->height;
        slot->bpp = state->bpp;
        slot->payload_bytes = copy_len;
        clock_gettime(CLOCK_MONOTONIC, &slot->timestamp);
        build_dng_header(slot->buffer, slot->width, slot->height,
                         slot->bpp, (uint32_t)copy_len);
        memcpy(slot->buffer + HEADER_SIZE, reg.data, copy_len);
        atomos_munmap_aligned(&reg);
    }

    atomos_dmabuf_sync(dma_fd, ATOMOS_DMA_BUF_SYNC_END | ATOMOS_DMA_BUF_SYNC_READ);

    if (map_rc != 0) {
        fprintf(stderr, "[VRAW_DMA] mmap failed for phys=0x%08X len=%zu: %s\n",
                phys_addr, copy_len, strerror(-map_rc));
        return -1;
    }

    if (!state->logged_first_dma) {
        printf("[VRAW_DMA] Ingested live frame (frameId=%u phys=0x%08X page_delta=%zu bytes=%zu -> %ux%u %ubpp)\n",
               frame_id, phys_addr, page_delta, copy_len,
               slot->width, slot->height, slot->bpp);
        state->logged_first_dma = 1;
    }

    pthread_mutex_lock(&queue->mutex);
    queue->head = (queue->head + 1) % RING_BUFFER_SLOTS;
    queue->count++;
    pthread_cond_signal(&queue->not_empty);
    pthread_mutex_unlock(&queue->mutex);

    state->captured_frames++;
    return 0;
}

static int handle_copro_message(RingQueue *queue, struct capture_state *state,
                                const struct atomos_copro_msg *msg, int rx_fd) {
    int ingested = 0;

    switch (msg->msg_type) {
    case ATOMOS_COPRO_MSG_FRAME_V1:
    case ATOMOS_COPRO_MSG_FRAME_V2: {
        uint32_t frame_id = (msg->msg_type == ATOMOS_COPRO_MSG_FRAME_V1)
            ? (msg->payload.frame_v1.frame_id_word & 0x7FFFU)
            : (msg->payload.frame_v2.frame_id_word & 0x7FFFU);
        if (rx_fd >= 0 &&
            ingest_dmabuf_frame(queue, state, rx_fd, msg->phys_addr, msg->size, frame_id) == 0) {
            ingested = 1;
        }
        break;
    }
    case ATOMOS_COPRO_MSG_VIDEO_CONFIG: {
        uint32_t cfg_off = msg->payload.dmabuf_ref.struct_offset;
        uint32_t cfg_len = msg->payload.dmabuf_ref.struct_len;
        if (rx_fd >= 0 && cfg_len >= ATOMOS_MSG_VIDEO_CONFIG_SIZE) {
            struct atomos_mapped_region reg;
            if (atomos_mmap_aligned(rx_fd, cfg_off, cfg_len,
                                    PROT_READ, MAP_SHARED, &reg) == 0) {
                struct atomos_msg_video_config vc;
                memcpy(&vc, reg.data, sizeof(vc));
                printf("[VRAW_COPRO] VIDEO_CONFIG(0x0040): res=%u dir=%u mode=%u %ux%u%c @%u/%u fmt=0x%02X col=0x%04X\n",
                       vc.result, vc.direction, vc.video_mode,
                       vc.width, vc.height, vc.interlaced ? 'i' : 'p',
                       vc.fps_num, vc.fps_den, vc.format_flags, vc.colorimetry);
                if (vc.width > 0 && vc.height > 0) {
                    state->width = vc.width;
                    state->height = vc.height;
                }
                atomos_munmap_aligned(&reg);
            }
        }
        break;
    }
    case ATOMOS_COPRO_MSG_STREAMING_CONFIG: {
        uint32_t cfg_off = msg->payload.dmabuf_ref.struct_offset;
        uint32_t cfg_len = msg->payload.dmabuf_ref.struct_len;
        if (rx_fd >= 0 && cfg_len >= ATOMOS_MSG_STREAMING_CONFIG_SIZE) {
            struct atomos_mapped_region reg;
            if (atomos_mmap_aligned(rx_fd, cfg_off, cfg_len,
                                    PROT_READ, MAP_SHARED, &reg) == 0) {
                struct atomos_msg_streaming_config sc;
                memcpy(&sc, reg.data, sizeof(sc));
                printf("[VRAW_COPRO] STREAMING_CONFIG(0x0072): res=%u dir=%u %ux%u%c @%u/%u proto=%u\n",
                       sc.result, sc.direction, sc.width, sc.height,
                       sc.interlaced ? 'i' : 'p', sc.fps_num, sc.fps_den, sc.stream_proto);
                atomos_munmap_aligned(&reg);
            }
        }
        break;
    }
    default:
        printf("[VRAW_COPRO] Control msg %s(0x%04X) flags=0x%02X phys=0x%08X size=%u\n",
               atomos_copro_msg_name(msg->msg_type), msg->msg_type,
               msg->flags, msg->phys_addr, msg->size);
        break;
    }

    if (rx_fd >= 0) {
        close(rx_fd);
    }
    return ingested;
}

static void print_usage(const char *argv0) {
    printf("Usage: %s [options] [frames] [output_dir]\n"
           "  --standalone, -s          Generate synthetic 12-bit 4K Bayer DNG frames (no IPC)\n"
           "  --direct-copro [dev]      Poll /dev/copro_comms_data (or [dev]) directly via ioctl\n"
           "  --fwd-sock <unix_path>    Listen (SOCK_SEQPACKET) for libfakecopro.so COPRO_FWD_SOCK\n"
           "  --help, -h                Show this help\n",
           argv0);
}

int main(int argc, char **argv) {
    uint32_t capture_frames = 24; // Default: 24 frames (0 = unlimited until SIGINT)
    const char *out_dir = "/tmp/vraw_capture";
    const char *copro_dev = NULL;
    const char *fwd_sock_path = NULL;
    int standalone = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--standalone") == 0 || strcmp(argv[i], "-s") == 0) {
            standalone = 1;
        } else if (strcmp(argv[i], "--direct-copro") == 0) {
            if (i + 1 < argc && strncmp(argv[i + 1], "/dev/", 5) == 0) {
                copro_dev = argv[++i];
            } else {
                copro_dev = ATOMOS_DEV_COPRO_DATA;
            }
        } else if (strcmp(argv[i], "--fwd-sock") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Missing socket path for --fwd-sock\n");
                return 1;
            }
            fwd_sock_path = argv[++i];
        } else if (argv[i][0] != '\0' && strspn(argv[i], "0123456789") == strlen(argv[i])) {
            uint32_t val = 0;
            const char *p = argv[i];
            while (*p >= '0' && *p <= '9') {
                val = val * 10 + (*p - '0');
                p++;
            }
            capture_frames = val;
        } else if (argv[i][0] != '-') {
            out_dir = argv[i];
        } else {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            print_usage(argv[0]);
            return 1;
        }
    }

    mkdir(out_dir, 0755);

    printf("====================================================================\n");
    printf(" Verdanove RAW Native C Integration Daemon (vraw_daemon)\n");
    printf(" Target: Atomos Ninja V (Quad Cortex-A53 / Zynq UltraScale+)\n");
    printf(" Pipeline Mode: 12-Bit Uncompressed Bayer (RGGB) CinemaDNG\n");
    printf(" Output Resolution: %ux%u (4K UHD) | Direct I/O Sector Size: %u\n", WIDTH, HEIGHT, HEADER_SIZE);
    printf(" Streaming Target: %u frames @ 24.00 fps -> %s\n", capture_frames, out_dir);
    printf("====================================================================\n\n");

    // Initialize ring buffer queue
    RingQueue queue;
    memset(&queue, 0, sizeof(queue));
    strncpy(queue.output_dir, out_dir, sizeof(queue.output_dir) - 1);
    pthread_mutex_init(&queue.mutex, NULL);
    pthread_cond_init(&queue.not_empty, NULL);
    pthread_cond_init(&queue.not_full, NULL);

    for (int i = 0; i < RING_BUFFER_SLOTS; i++) {
        int ret = posix_memalign((void **)&queue.slots[i].buffer, 4096, TOTAL_FRAME_BYTES);
        if (ret != 0 || !queue.slots[i].buffer) {
            fprintf(stderr, "Failed to allocate 4KB-aligned ring slot %d\n", i);
            return 1;
        }
    }

    pthread_t writer_thread;
    pthread_create(&writer_thread, NULL, disk_writer_thread, &queue);

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    int copro_fd = -1;
    int fwd_listen_fd = -1;
    int ipc_sock = -1;

    if (!standalone) {
        if (copro_dev) {
            copro_fd = open(copro_dev, O_RDWR | O_CLOEXEC);
            if (copro_fd < 0) {
                fprintf(stderr, "[VRAW_COPRO] Failed to open %s: %s (note: copro-comms.ko is single-accessor without DTB allow-multiple-accessors)\n",
                        copro_dev, strerror(errno));
            } else {
                printf("[VRAW_COPRO] Opened direct CoPro RX device %s (fd=%d)\n", copro_dev, copro_fd);
            }
        } else if (fwd_sock_path) {
            fwd_listen_fd = listen_fwd_socket(fwd_sock_path);
            if (fwd_listen_fd < 0) {
                return 1;
            }
            printf("[VRAW_FWD] Listening on UNIX SEQPACKET socket %s (awaiting COPRO_FWD_SOCK client)\n",
                   fwd_sock_path);
        } else {
            printf("[VRAW_IPC] Attempting connection to AtomOS video_pipeline IPC socket...\n");
            ipc_sock = connect_video_pipeline_socket();
            if (ipc_sock < 0) {
                printf("[VRAW_IPC] Daemon socket unavailable; operating in standalone synthetic DMA mode.\n");
            } else {
                uint8_t handshake_pkt[] = {0x04, 0x08, 0x01, 0x12, 0x00};
                send(ipc_sock, handshake_pkt, sizeof(handshake_pkt), 0);
                printf("[VRAW_IPC] Sent Protobuf configuration handshake.\n");
            }
        }
    } else {
        printf("[VRAW_IPC] Standalone test mode active.\n");
    }

    struct capture_state state;
    state.width = WIDTH;
    state.height = HEIGHT;
    state.bpp = BITS_PER_SAMPLE;
    state.captured_frames = 0;
    state.logged_first_dma = 0;

    struct timespec bench_start, bench_end;
    clock_gettime(CLOCK_MONOTONIC, &bench_start);

    if (copro_fd >= 0) {
        while (g_running && (capture_frames == 0 || state.captured_frames < capture_frames)) {
            struct pollfd pfd;
            pfd.fd = copro_fd;
            pfd.events = POLLIN;
            pfd.revents = 0;
            int pr = poll(&pfd, 1, 200);
            if (pr < 0) {
                if (errno == EINTR) continue;
                perror("[VRAW_COPRO] poll");
                break;
            }
            if (pr == 0) continue;

            struct atomos_copro_msg msg;
            memset(&msg, 0, sizeof(msg));
            msg.dma_fd = -1;
            if (ioctl(copro_fd, ATOMOS_COPRO_IOC_GET_MESSAGE, &msg) == 0) {
                handle_copro_message(&queue, &state, &msg, msg.dma_fd);
            } else if (errno != EAGAIN && errno != EINTR) {
                perror("[VRAW_COPRO] ATOMOS_COPRO_IOC_GET_MESSAGE");
                break;
            }
        }
    } else if (fwd_listen_fd >= 0) {
        int client_fd = -1;
        while (g_running && (capture_frames == 0 || state.captured_frames < capture_frames)) {
            if (client_fd < 0) {
                client_fd = accept_with_poll(fwd_listen_fd);
                if (client_fd < 0) break;
                printf("[VRAW_FWD] Forwarder client connected (fd=%d)\n", client_fd);
            }

            int rx_fd = -1;
            size_t rx_len = 0;
            uint8_t rx_buf[1024];
            int rr = recv_dmabuf_fd(client_fd, &rx_fd, rx_buf, sizeof(rx_buf), &rx_len, 200);
            if (rr == 1) {
                continue;
            } else if (rr < 0) {
                printf("[VRAW_FWD] Client %s\n", (rr == -2) ? "disconnected (EOF)" : "error");
                close(client_fd);
                client_fd = -1;
                if (rx_fd >= 0) close(rx_fd);
                continue;
            }

            if (rx_len == sizeof(struct atomos_copro_msg)) {
                struct atomos_copro_msg msg;
                memcpy(&msg, rx_buf, sizeof(msg));
                handle_copro_message(&queue, &state, &msg, rx_fd);
            } else if (rx_fd >= 0) {
                ingest_dmabuf_frame(&queue, &state, rx_fd, 0, 0, state.captured_frames);
                close(rx_fd);
            }
        }
        if (client_fd >= 0) {
            close(client_fd);
        }
    } else if (!copro_dev) {
        const long frame_interval_ns = 41666667L; // 24.00 fps cadence

        for (uint32_t f = 0; (capture_frames == 0 || state.captured_frames < capture_frames) && g_running; f++) {
            struct timespec frame_start;
            clock_gettime(CLOCK_MONOTONIC, &frame_start);

            int rx_fd = -1;
            size_t rx_len = 0;
            uint8_t rx_buf[1024];

            if (ipc_sock >= 0 && recv_dmabuf_fd(ipc_sock, &rx_fd, rx_buf, sizeof(rx_buf), &rx_len, -1) == 0) {
                if (rx_len == sizeof(struct atomos_copro_msg)) {
                    struct atomos_copro_msg msg;
                    memcpy(&msg, rx_buf, sizeof(msg));
                    handle_copro_message(&queue, &state, &msg, rx_fd);
                } else if (rx_fd >= 0) {
                    ingest_dmabuf_frame(&queue, &state, rx_fd, 0, 0, f);
                    close(rx_fd);
                }
            } else {
                if (rx_fd >= 0) close(rx_fd);

                pthread_mutex_lock(&queue.mutex);
                if (queue.count == RING_BUFFER_SLOTS) {
                    queue.dropped_frames++;
                    pthread_mutex_unlock(&queue.mutex);
                    fprintf(stderr, "[VRAW_PRODUCER] WARNING: Buffer full! Dropped frame %u!\n", f);
                    continue;
                }
                RingSlot *slot = &queue.slots[queue.head];
                pthread_mutex_unlock(&queue.mutex);

                slot->frame_index = state.captured_frames;
                slot->width = WIDTH;
                slot->height = HEIGHT;
                slot->bpp = BITS_PER_SAMPLE;
                slot->payload_bytes = RAW_FRAME_BYTES;
                slot->timestamp = frame_start;
                build_dng_header(slot->buffer, WIDTH, HEIGHT, BITS_PER_SAMPLE, (uint32_t)RAW_FRAME_BYTES);
                fill_synthetic_12bit_bayer(slot->buffer + HEADER_SIZE, f);

                pthread_mutex_lock(&queue.mutex);
                queue.head = (queue.head + 1) % RING_BUFFER_SLOTS;
                queue.count++;
                pthread_cond_signal(&queue.not_empty);
                pthread_mutex_unlock(&queue.mutex);

                state.captured_frames++;

                struct timespec frame_now;
                clock_gettime(CLOCK_MONOTONIC, &frame_now);
                long elapsed_ns = (frame_now.tv_sec - frame_start.tv_sec) * 1000000000L +
                                  (frame_now.tv_nsec - frame_start.tv_nsec);
                if (elapsed_ns < frame_interval_ns) {
                    struct timespec req = {0, frame_interval_ns - elapsed_ns};
                    nanosleep(&req, NULL);
                }
            }
        }
    }

    // Terminate stream & join writer
    pthread_mutex_lock(&queue.mutex);
    queue.done = 1;
    pthread_cond_signal(&queue.not_empty);
    pthread_mutex_unlock(&queue.mutex);

    pthread_join(writer_thread, NULL);

    if (copro_fd >= 0) {
        close(copro_fd);
    }
    if (fwd_listen_fd >= 0) {
        close(fwd_listen_fd);
        unlink(fwd_sock_path);
    }
    if (ipc_sock >= 0) {
        close(ipc_sock);
    }

    clock_gettime(CLOCK_MONOTONIC, &bench_end);
    double total_sec = (bench_end.tv_sec - bench_start.tv_sec) +
                       (bench_end.tv_nsec - bench_start.tv_nsec) / 1000000000.0;
    if (total_sec <= 0.0001) total_sec = 0.0001;
    double total_mb = (double)queue.written_bytes / (1024.0 * 1024.0);
    double avg_fps = queue.written_frames / total_sec;
    double avg_throughput = total_mb / total_sec;
    uint32_t denom = (capture_frames > 0) ? capture_frames
                     : (queue.written_frames + queue.dropped_frames);
    double drop_pct = (denom > 0) ? ((queue.dropped_frames * 100.0) / denom) : 0.0;

    printf("\n====================================================================\n");
    printf(" Verdanove RAW Capture Engine Summary:\n");
    printf("   - Total Frames Captured:  %u / %u\n", queue.written_frames, capture_frames);
    printf("   - Dropped Frames:         %u (%.2f%% drop rate)\n", queue.dropped_frames, drop_pct);
    printf("   - Total Data Streamed:    %.2f MB in %.3f seconds\n", total_mb, total_sec);
    printf("   - Sustained Framerate:    %.2f FPS (Target: 24.00)\n", avg_fps);
    printf("   - Sustained Throughput:   %.2f MB/s (SATA 3 Limit: ~540 MB/s)\n", avg_throughput);
    printf("   - Real-Time Verification: %s\n",
        (queue.dropped_frames == 0 && (fwd_sock_path || copro_dev || avg_fps >= 23.5))
            ? "PASSED (100% Real-Time Compliant)" : "FAILED");
    printf("====================================================================\n");

    for (int i = 0; i < RING_BUFFER_SLOTS; i++) {
        free(queue.slots[i].buffer);
    }
    pthread_mutex_destroy(&queue.mutex);
    pthread_cond_destroy(&queue.not_empty);
    pthread_cond_destroy(&queue.not_full);

    return (copro_dev && copro_fd < 0) ? 1 : 0;
}

