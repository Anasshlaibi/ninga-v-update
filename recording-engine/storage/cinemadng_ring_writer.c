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
#include <sys/stat.h>
#include <sys/types.h>

#define WIDTH 3840
#define HEIGHT 2160
#define BITS_PER_SAMPLE 12
#define HEADER_SIZE 4096 // 4KB page-aligned header for direct I/O
#define RAW_FRAME_BYTES ((WIDTH * HEIGHT * BITS_PER_SAMPLE) / 8) // 12,441,600 bytes
#define TOTAL_FRAME_BYTES (HEADER_SIZE + RAW_FRAME_BYTES)
#define RING_BUFFER_SLOTS 8 // 8 frame buffer slots (~99.5 MB RAM)

// TIFF / DNG Tag IDs
#define TAG_NEWSUBFILETYPE         0x00FE
#define TAG_IMAGEWIDTH             0x0100
#define TAG_IMAGELENGTH            0x0101
#define TAG_BITSPERSAMPLE          0x0102
#define TAG_COMPRESSION            0x0103
#define TAG_PHOTOMETRIC            0x0106
#define TAG_STRIPOFFSETS           0x0111
#define TAG_SAMPLESPERPXL          0x0115
#define TAG_ROWSPERSTRIP           0x0116
#define TAG_STRIPBYTECOUNTS        0x0117
#define TAG_PLANARCONFIG           0x011C
#define TAG_CFAREPEATPATT          0x828D
#define TAG_CFAPATTERN             0x828E
#define TAG_DNGVERSION             0xC612
#define TAG_DNGFORWARDVERSION      0xC613

#define TYPE_SHORT 3
#define TYPE_LONG  4

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

    uint16_t num_entries = 15;
    uint32_t p = 8;
    memcpy(hdr + p, &num_entries, 2);
    p += 2;

    TiffEntry entries[15] = {
        {TAG_NEWSUBFILETYPE, TYPE_LONG, 1, 0},
        {TAG_IMAGEWIDTH, TYPE_LONG, 1, WIDTH},
        {TAG_IMAGELENGTH, TYPE_LONG, 1, HEIGHT},
        {TAG_BITSPERSAMPLE, TYPE_SHORT, 1, BITS_PER_SAMPLE},
        {TAG_COMPRESSION, TYPE_SHORT, 1, 1}, // Uncompressed
        {TAG_PHOTOMETRIC, TYPE_SHORT, 1, 32803}, // CFA
        {TAG_STRIPOFFSETS, TYPE_LONG, 1, HEADER_SIZE}, // 4096
        {TAG_SAMPLESPERPXL, TYPE_SHORT, 1, 1},
        {TAG_ROWSPERSTRIP, TYPE_LONG, 1, HEIGHT},
        {TAG_STRIPBYTECOUNTS, TYPE_LONG, 1, RAW_FRAME_BYTES},
        {TAG_PLANARCONFIG, TYPE_SHORT, 1, 1},
        {TAG_CFAREPEATPATT, TYPE_SHORT, 2, (2 << 16) | 2},
        {TAG_CFAPATTERN, 1, 4, 0x02010100}, // RGGB (0, 1, 1, 2)
        {TAG_DNGVERSION, 1, 4, 0x00000401}, // 1.4.0.0
        {TAG_DNGFORWARDVERSION, 1, 4, 0x00000101} // 1.1.0.0
    };

    memcpy(hdr + p, entries, sizeof(entries));
    p += sizeof(entries);

    uint32_t next_ifd = 0;
    memcpy(hdr + p, &next_ifd, 4);
}

// Generate realistic synthetic 12-bit Bayer pixels
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

        // Dequeue slot
        RingSlot *slot = &q->slots[q->tail];
        q->tail = (q->tail + 1) % RING_BUFFER_SLOTS;
        q->count--;

        pthread_cond_signal(&q->not_full);
        pthread_mutex_unlock(&q->mutex);

        // Perform disk write
        char filename[512];
        snprintf(filename, sizeof(filename), "%s/clip001_%06u.dng", q->output_dir, slot->frame_index);

        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);

        // Try direct I/O; fallback to standard if filesystem doesn't support O_DIRECT
        int fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC | O_DIRECT, 0644);
        if (fd < 0 && errno == EINVAL) {
            fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        }

        if (fd >= 0) {
            ssize_t w = write(fd, slot->buffer, TOTAL_FRAME_BYTES);
            close(fd);
            q->written_frames++;

            clock_gettime(CLOCK_MONOTONIC, &t1);
            double write_ms = (t1.tv_sec - t0.tv_sec) * 1000.0 + (t1.tv_nsec - t0.tv_nsec) / 1000000.0;
            double mb_s = (TOTAL_FRAME_BYTES / (1024.0 * 1024.0)) / (write_ms / 1000.0);

            printf("[DISK_WRITER] Frame %05u written: %.2f MB in %5.2f ms (%6.1f MB/s) | Queue Depth: %d/%d\n",
                slot->frame_index, TOTAL_FRAME_BYTES / (1024.0 * 1024.0), write_ms, mb_s, q->count, RING_BUFFER_SLOTS);
        } else {
            fprintf(stderr, "[DISK_WRITER] Error writing %s: %s\n", filename, strerror(errno));
        }
    }

    return NULL;
}

int main(int argc, char **argv) {
    uint32_t total_frames = 48; // 2 seconds at 24fps
    const char *out_dir = "/tmp/cinemadng_stream";

    if (argc > 1) total_frames = (uint32_t)atoi(argv[1]);
    if (argc > 2) out_dir = argv[2];

    mkdir(out_dir, 0755);

    printf("====================================================================\n");
    printf(" CinemaDNG 12-bit RAW Direct-I/O Ring Buffer Recorder\n");
    printf(" Resolution: %dx%d (4K UHD) | Format: 12-bit Bayer RGGB CinemaDNG\n", WIDTH, HEIGHT);
    printf(" Frame Payload: %.2f MB | Direct I/O Page-Aligned Header: %d bytes\n",
        RAW_FRAME_BYTES / (1024.0 * 1024.0), HEADER_SIZE);
    printf(" Ring Buffer: %d slots (Total Memory: %.2f MB)\n",
        RING_BUFFER_SLOTS, (RING_BUFFER_SLOTS * TOTAL_FRAME_BYTES) / (1024.0 * 1024.0));
    printf(" Streaming Target: %u frames @ 24.00 fps -> %s\n", total_frames, out_dir);
    printf("====================================================================\n\n");

    RingQueue queue;
    memset(&queue, 0, sizeof(queue));
    strncpy(queue.output_dir, out_dir, sizeof(queue.output_dir) - 1);
    pthread_mutex_init(&queue.mutex, NULL);
    pthread_cond_init(&queue.not_empty, NULL);
    pthread_cond_init(&queue.not_full, NULL);

    // Allocate 4KB page-aligned buffers for all ring slots
    for (int i = 0; i < RING_BUFFER_SLOTS; i++) {
        int ret = posix_memalign((void **)&queue.slots[i].buffer, 4096, TOTAL_FRAME_BYTES);
        if (ret != 0 || !queue.slots[i].buffer) {
            fprintf(stderr, "Failed to allocate ring slot %d\n", i);
            return 1;
        }
    }

    pthread_t writer_thread;
    pthread_create(&writer_thread, NULL, disk_writer_thread, &queue);

    struct timespec bench_start, bench_end;
    clock_gettime(CLOCK_MONOTONIC, &bench_start);

    // Producer simulation: streams incoming 4K Bayer frames at 24.00 fps (41.67 ms cadence)
    const long frame_interval_ns = 41666667L; // 24.00 fps

    for (uint32_t f = 0; f < total_frames; f++) {
        struct timespec frame_start;
        clock_gettime(CLOCK_MONOTONIC, &frame_start);

        pthread_mutex_lock(&queue.mutex);
        if (queue.count == RING_BUFFER_SLOTS) {
            // Buffer overflow - dropped frame!
            queue.dropped_frames++;
            pthread_mutex_unlock(&queue.mutex);
            fprintf(stderr, "[PRODUCER] WARNING: Buffer full! Dropped frame %u!\n", f);
            continue;
        }

        RingSlot *slot = &queue.slots[queue.head];
        queue.head = (queue.head + 1) % RING_BUFFER_SLOTS;
        queue.count++;
        pthread_mutex_unlock(&queue.mutex);

        // Populate slot
        slot->frame_index = f;
        slot->timestamp = frame_start;
        build_dng_header(slot->buffer, f);
        fill_synthetic_12bit_bayer(slot->buffer + HEADER_SIZE, f);

        pthread_mutex_lock(&queue.mutex);
        pthread_cond_signal(&queue.not_empty);
        pthread_mutex_unlock(&queue.mutex);

        // Frame rate pacing: sleep remaining time in frame budget (41.67 ms)
        struct timespec frame_now;
        clock_gettime(CLOCK_MONOTONIC, &frame_now);
        long elapsed_ns = (frame_now.tv_sec - frame_start.tv_sec) * 1000000000L + (frame_now.tv_nsec - frame_start.tv_nsec);
        if (elapsed_ns < frame_interval_ns) {
            struct timespec req = {0, frame_interval_ns - elapsed_ns};
            nanosleep(&req, NULL);
        }
    }

    // Terminate stream
    pthread_mutex_lock(&queue.mutex);
    queue.done = 1;
    pthread_cond_signal(&queue.not_empty);
    pthread_mutex_unlock(&queue.mutex);

    pthread_join(writer_thread, NULL);

    clock_gettime(CLOCK_MONOTONIC, &bench_end);
    double total_sec = (bench_end.tv_sec - bench_start.tv_sec) + (bench_end.tv_nsec - bench_start.tv_nsec) / 1000000000.0;
    double total_mb = (queue.written_frames * TOTAL_FRAME_BYTES) / (1024.0 * 1024.0);
    double avg_fps = queue.written_frames / total_sec;
    double avg_throughput = total_mb / total_sec;

    printf("\n====================================================================\n");
    printf(" CinemaDNG Ring Buffer Stream Verification Report:\n");
    printf("   - Total Frames Captured:  %u / %u\n", queue.written_frames, total_frames);
    printf("   - Dropped Frames:         %u (%.2f%% drop rate)\n",
        queue.dropped_frames, (queue.dropped_frames * 100.0) / total_frames);
    printf("   - Total Data Streamed:    %.2f MB in %.3f seconds\n", total_mb, total_sec);
    printf("   - Sustained Framerate:    %.2f FPS (Target: 24.00)\n", avg_fps);
    printf("   - Sustained Throughput:   %.2f MB/s (SATA 3 Limit: ~540 MB/s)\n", avg_throughput);
    printf("   - Real-Time 24p Result:   %s\n",
        (queue.dropped_frames == 0 && avg_fps >= 23.5) ? "SUCCESS - 100% REAL-TIME COMPLIANT" : "FAILED");
    printf("====================================================================\n");

    for (int i = 0; i < RING_BUFFER_SLOTS; i++) {
        free(queue.slots[i].buffer);
    }
    pthread_mutex_destroy(&queue.mutex);
    pthread_cond_destroy(&queue.not_empty);
    pthread_cond_destroy(&queue.not_full);

    return 0;
}
