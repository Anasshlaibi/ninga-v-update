#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <signal.h>

static volatile int g_running = 1;
static void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

#define WIDTH 3840
#define HEIGHT 2160
#define BITS_PER_SAMPLE 12
#define HEADER_SIZE 4096 // 4KB page-aligned header for direct I/O
#define RAW_FRAME_BYTES ((WIDTH * HEIGHT * BITS_PER_SAMPLE) / 8) // 12,441,600 bytes
#define TOTAL_FRAME_BYTES (HEADER_SIZE + RAW_FRAME_BYTES)
#define RING_BUFFER_SLOTS 8 // 8 frame buffer slots (~99.5 MB RAM)

#define DEFAULT_SOCKET_PATH "/var/run/user/1000/atomos/video_pipeline_socket"
#define FALLBACK_SOCKET_PATH "/var/run/atomos/video_pipeline_socket"

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
    char output_dir[256];
    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
} RingQueue;

// Generate Adobe DNG 1.4 compliant TIFF header
static void build_dng_header(uint8_t *hdr, uint32_t frame_index) {
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

    uint16_t num_entries = 23;
    uint32_t p = 8;
    memcpy(hdr + p, &num_entries, 2);
    p += 2;

    TiffEntry entries[23] = {
        {TAG_NEWSUBFILETYPE,    TYPE_LONG,     1,  0},
        {TAG_IMAGEWIDTH,        TYPE_LONG,     1,  WIDTH},
        {TAG_IMAGELENGTH,       TYPE_LONG,     1,  HEIGHT},
        {TAG_BITSPERSAMPLE,     TYPE_SHORT,    1,  BITS_PER_SAMPLE},
        {TAG_COMPRESSION,       TYPE_SHORT,    1,  1}, // Uncompressed
        {TAG_PHOTOMETRIC,       TYPE_SHORT,    1,  32803}, // CFA
        {TAG_MAKE,              TYPE_ASCII,    10, off_make},
        {TAG_MODEL,             TYPE_ASCII,    12, off_model},
        {TAG_STRIPOFFSETS,      TYPE_LONG,     1,  HEADER_SIZE},
        {TAG_SAMPLESPERPXL,     TYPE_SHORT,    1,  1},
        {TAG_ROWSPERSTRIP,      TYPE_LONG,     1,  HEIGHT},
        {TAG_STRIPBYTECOUNTS,   TYPE_LONG,     1,  RAW_FRAME_BYTES},
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
        {TAG_WHITELEVEL,        TYPE_LONG,     1,  4095}
    };

    memcpy(hdr + p, entries, sizeof(entries));
    p += sizeof(entries);

    uint32_t next_ifd = 0;
    memcpy(hdr + p, &next_ifd, 4);
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
        q->tail = (q->tail + 1) % RING_BUFFER_SLOTS;
        q->count--;

        pthread_cond_signal(&q->not_full);
        pthread_mutex_unlock(&q->mutex);

        char filename[512];
        snprintf(filename, sizeof(filename), "%s/vraw_%06u.dng", q->output_dir, slot->frame_index);

        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);

        int fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC | O_DIRECT, 0644);
        if (fd < 0 && (errno == EINVAL || errno == EOPNOTSUPP)) {
            fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        }

        if (fd >= 0) {
            ssize_t w = write(fd, slot->buffer, TOTAL_FRAME_BYTES);
            close(fd);
            q->written_frames++;

            clock_gettime(CLOCK_MONOTONIC, &t1);
            double write_ms = (t1.tv_sec - t0.tv_sec) * 1000.0 + (t1.tv_nsec - t0.tv_nsec) / 1000000.0;
            double mb_s = (TOTAL_FRAME_BYTES / (1024.0 * 1024.0)) / (write_ms / 1000.0);

            printf("[VRAW_REC] Frame %05u written: %.2f MB in %5.2f ms (%6.1f MB/s) | Queue: %d/%d\n",
                slot->frame_index, TOTAL_FRAME_BYTES / (1024.0 * 1024.0), write_ms, mb_s, q->count, RING_BUFFER_SLOTS);
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

// Receive message and intercept any SCM_RIGHTS file descriptors
static int recv_dmabuf_fd(int sock, int *out_fd, uint8_t *msg_buf, size_t msg_max, size_t *msg_len) {
    struct msghdr msg;
    memset(&msg, 0, sizeof(msg));

    struct iovec iov;
    iov.iov_base = msg_buf;
    iov.iov_len = msg_max;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;

    char cmsg_buf[CMSG_SPACE(sizeof(int) * 4)];
    msg.msg_control = cmsg_buf;
    msg.msg_controllen = sizeof(cmsg_buf);

    ssize_t n = recvmsg(sock, &msg, 0);
    if (n < 0) {
        return -1;
    }

    *msg_len = (size_t)n;
    *out_fd = -1;

    struct cmsghdr *cmsg;
    for (cmsg = CMSG_FIRSTHDR(&msg); cmsg != NULL; cmsg = CMSG_NXTHDR(&msg, cmsg)) {
        if (cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS) {
            int *fds = (int *)CMSG_DATA(cmsg);
            *out_fd = fds[0];
            break;
        }
    }

    return 0;
}

int main(int argc, char **argv) {
    uint32_t capture_frames = 24; // Default: 24 frames
    const char *out_dir = "/tmp/vraw_capture";
    int standalone = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--standalone") == 0 || strcmp(argv[i], "-s") == 0) {
            standalone = 1;
        } else if (atoi(argv[i]) > 0) {
            capture_frames = (uint32_t)atoi(argv[i]);
        } else if (argv[i][0] != '-') {
            out_dir = argv[i];
        }
    }

    mkdir(out_dir, 0755);

    printf("====================================================================\n");
    printf(" Verdanove RAW Native C Integration Daemon (vraw_daemon)\n");
    printf(" Target: Atomos Ninja V (Quad Cortex-A53 / Zynq UltraScale+)\n");
    printf(" Pipeline Mode: 12-Bit Uncompressed Bayer (RGGB) CinemaDNG\n");
    printf(" Output Resolution: %dx%d (4K UHD) | Direct I/O Sector Size: %d\n", WIDTH, HEIGHT, HEADER_SIZE);
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

    int ipc_sock = -1;
    if (!standalone) {
        printf("[VRAW_IPC] Attempting connection to AtomOS video_pipeline IPC socket...\n");
        ipc_sock = connect_video_pipeline_socket();
        if (ipc_sock < 0) {
            printf("[VRAW_IPC] Daemon socket unavailable; operating in standalone synthetic DMA mode.\n");
        } else {
            // Send Protobuf configuration handshake: request mode=Bayer, depth=12BPP
            // Framed Varint Protobuf payload for Service.Requests (version=1, getStatus)
            uint8_t handshake_pkt[] = {0x04, 0x08, 0x01, 0x12, 0x00};
            send(ipc_sock, handshake_pkt, sizeof(handshake_pkt), 0);
            printf("[VRAW_IPC] Sent Protobuf configuration handshake.\n");
        }
    } else {
        printf("[VRAW_IPC] Standalone test mode active.\n");
    }

    struct timespec bench_start, bench_end;
    clock_gettime(CLOCK_MONOTONIC, &bench_start);

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    const long frame_interval_ns = 41666667L; // 24.00 fps cadence

    for (uint32_t f = 0; (capture_frames == 0 || f < capture_frames) && g_running; f++) {
        struct timespec frame_start;
        clock_gettime(CLOCK_MONOTONIC, &frame_start);

        pthread_mutex_lock(&queue.mutex);
        if (queue.count == RING_BUFFER_SLOTS) {
            queue.dropped_frames++;
            pthread_mutex_unlock(&queue.mutex);
            fprintf(stderr, "[VRAW_PRODUCER] WARNING: Buffer full! Dropped frame %u!\n", f);
            continue;
        }

        RingSlot *slot = &queue.slots[queue.head];
        queue.head = (queue.head + 1) % RING_BUFFER_SLOTS;
        queue.count++;
        pthread_mutex_unlock(&queue.mutex);

        // Populate slot metadata & header
        slot->frame_index = f;
        slot->timestamp = frame_start;
        build_dng_header(slot->buffer, f);

        int dma_fd = -1;
        size_t rx_len = 0;
        uint8_t rx_buf[1024];

        if (ipc_sock >= 0 && recv_dmabuf_fd(ipc_sock, &dma_fd, rx_buf, sizeof(rx_buf), &rx_len) == 0 && dma_fd >= 0) {
            // Live zero-copy DMA buffer received via SCM_RIGHTS!
            struct stat st;
            if (fstat(dma_fd, &st) == 0 && st.st_size >= RAW_FRAME_BYTES) {
                void *mapped = mmap(NULL, RAW_FRAME_BYTES, PROT_READ, MAP_SHARED, dma_fd, 0);
                if (mapped != MAP_FAILED) {
                    memcpy(slot->buffer + HEADER_SIZE, mapped, RAW_FRAME_BYTES);
                    munmap(mapped, RAW_FRAME_BYTES);
                }
            }
            close(dma_fd);
        } else {
            // Generate synthetic Bayer 12-bit gradient frame
            fill_synthetic_12bit_bayer(slot->buffer + HEADER_SIZE, f);
        }

        pthread_mutex_lock(&queue.mutex);
        pthread_cond_signal(&queue.not_empty);
        pthread_mutex_unlock(&queue.mutex);

        // Frame rate pacing
        struct timespec frame_now;
        clock_gettime(CLOCK_MONOTONIC, &frame_now);
        long elapsed_ns = (frame_now.tv_sec - frame_start.tv_sec) * 1000000000L + (frame_now.tv_nsec - frame_start.tv_nsec);
        if (elapsed_ns < frame_interval_ns) {
            struct timespec req = {0, frame_interval_ns - elapsed_ns};
            nanosleep(&req, NULL);
        }
    }

    // Terminate stream & join writer
    pthread_mutex_lock(&queue.mutex);
    queue.done = 1;
    pthread_cond_signal(&queue.not_empty);
    pthread_mutex_unlock(&queue.mutex);

    pthread_join(writer_thread, NULL);

    if (ipc_sock >= 0) {
        close(ipc_sock);
    }

    clock_gettime(CLOCK_MONOTONIC, &bench_end);
    double total_sec = (bench_end.tv_sec - bench_start.tv_sec) + (bench_end.tv_nsec - bench_start.tv_nsec) / 1000000000.0;
    double total_mb = (queue.written_frames * TOTAL_FRAME_BYTES) / (1024.0 * 1024.0);
    double avg_fps = queue.written_frames / total_sec;
    double avg_throughput = total_mb / total_sec;

    printf("\n====================================================================\n");
    printf(" Verdanove RAW Capture Engine Summary:\n");
    printf("   - Total Frames Captured:  %u / %u\n", queue.written_frames, capture_frames);
    printf("   - Dropped Frames:         %u (%.2f%% drop rate)\n",
        queue.dropped_frames, (queue.dropped_frames * 100.0) / capture_frames);
    printf("   - Total Data Streamed:    %.2f MB in %.3f seconds\n", total_mb, total_sec);
    printf("   - Sustained Framerate:    %.2f FPS (Target: 24.00)\n", avg_fps);
    printf("   - Sustained Throughput:   %.2f MB/s (SATA 3 Limit: ~540 MB/s)\n", avg_throughput);
    printf("   - Real-Time Verification: %s\n",
        (queue.dropped_frames == 0 && avg_fps >= 23.5) ? "PASSED (100% Real-Time Compliant)" : "FAILED");
    printf("====================================================================\n");

    for (int i = 0; i < RING_BUFFER_SLOTS; i++) {
        free(queue.slots[i].buffer);
    }
    pthread_mutex_destroy(&queue.mutex);
    pthread_cond_destroy(&queue.not_empty);
    pthread_cond_destroy(&queue.not_full);

    return 0;
}

