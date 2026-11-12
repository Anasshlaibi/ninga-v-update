/*
 * atomos_copro_abi.h — Proposed AtomOS (Ninja V / XCZU5EV) Kernel Driver &
 * Video Pipeline ABI Bindings for recording-engine/vraw_daemon
 *
 * Derived strictly from static AArch64 ELF & kernel module analysis of:
 *   - /usr/bin/video_pipeline (AtomOS 11.19.00, stripped ELF64 AArch64 PIE)
 *   - /usr/bin/core_control, /usr/bin/media_control
 *   - /lib/modules/6.1.5-xilinx-v2023.1/extra/copro-comms.ko
 *   - /lib/modules/6.1.5-xilinx-v2023.1/extra/copro-buf-exporter.ko
 *   - /lib/modules/6.1.5-xilinx-v2023.1/extra/custom-cma.ko
 *   - /lib/modules/6.1.5-xilinx-v2023.1/extra/al5e/al5e.ko
 *   - /lib/modules/6.1.5-xilinx-v2023.1/extra/dmaproxy/dmaproxy.ko
 *   - /usr/lib/libgstallocators-1.0.so.0.2005.0
 *   - reverse-engineering/device-tree/system.dts
 *
 * Note: Struct layouts are recovered from instruction/register offsets. While
 * ioctl opcodes, struct sizes, and dma_fd/flags/type/phys/size offsets are
 * directly verified in kernel & userspace machine code, runtime RAW Bayer frame
 * availability on /dev/copro_comms_data vs VCU YUV paths remains runtime-unverified
 * on physical Ninja V hardware.
 */

#ifndef ATOMOS_COPRO_ABI_H
#define ATOMOS_COPRO_ABI_H

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * 1. Device Node Paths & UNIX IPC Socket Endpoints
 * ========================================================================== */

#define ATOMOS_DEV_COPRO_DATA      "/dev/copro_comms_data"   /* video_pipeline, streaming_pl */
#define ATOMOS_DEV_COPRO_CTRL      "/dev/copro_comms_ctrl"   /* core_control */
#define ATOMOS_DEV_COPRO_APP2      "/dev/copro_comms_app2"   /* secondary streaming pipeline */
#define ATOMOS_DEV_COPRO_APP3      "/dev/copro_comms_app3"   /* cloud_service */
#define ATOMOS_DEV_COPRO_APP4      "/dev/copro_comms_app4"   /* media_control */
#define ATOMOS_DEV_COPRO_APP5      "/dev/copro_comms_app5"   /* camera_control, audio_encoder, talkback_pl */

#define ATOMOS_DEV_DMA_HEAP_DIR    "/dev/dma_heap"
#define ATOMOS_DEV_DMA_HEAP_CODEC  "/dev/dma_heap/codec_output"
#define ATOMOS_DEV_CUSTOM_CMA      "/dev/custom_cma"
#define ATOMOS_DEV_ALLEGRO_ENC     "/dev/allegroIP"
#define ATOMOS_DEV_ALLEGRO_DEC     "/dev/allegroDecodeIP"
#define ATOMOS_DEV_DMAPROXY        "/dev/dmaproxy"
#define ATOMOS_DEV_MEM             "/dev/mem"

#define ATOMOS_VIDEO_SOCK_USER     "/var/run/user/1000/atomos/video_pipeline_socket"
#define ATOMOS_VIDEO_SOCK_FALLBACK "/var/run/atomos/video_pipeline_socket"

/* ============================================================================
 * 2. Reserved Physical Memory Layout (system.dts)
 * ========================================================================== */

#define ATOMOS_PHYS_MISC_CMA_BASE      0x1a000000ULL
#define ATOMOS_PHYS_MISC_CMA_SIZE      0x01000000ULL  /* 16 MiB, shared-dma-pool (default) */

#define ATOMOS_PHYS_CODEC_INPUT_BASE   0x1b000000ULL
#define ATOMOS_PHYS_CODEC_INPUT_SIZE   0x11000000ULL  /* 272 MiB, no-map (CoPro/R5/FPGA shared input) */

#define ATOMOS_PHYS_CODEC_OUTPUT_BASE  0x2c000000ULL
#define ATOMOS_PHYS_CODEC_OUTPUT_SIZE  0x34000000ULL  /* 832 MiB, shared-dma-pool (restrict-range 0x4f000000) */

/* ============================================================================
 * 3. /dev/copro_comms_* Interface (copro-comms.ko + copro-buf-exporter.ko)
 * ========================================================================== */

/*
 * Flag bits observed in copro_comms_ioctl (0x1050) and
 * copro_comms_on_buffer_released (0x0d20):
 *   - (flags & 0xC0) == 0x40: RX imports phys/len via copro_buf_exporter_import_buffer()
 *     and returns a CLOEXEC+RDWR dma_buf FD in dma_fd; closing dma_fd triggers
 *     copro_comms_on_buffer_released() which writes flags = 0xC0 and returns the
 *     32-byte ipi_msg back to R5 over IPI mailbox.
 *   - COPRO_IOC_PREPARE_DMABUF_MSG (0xc0242002): for dma_fd >= 0 with
 *     (flags & 0xC0) == 0x40, attaches/maps dma_buf and populates phys_addr + size
 *     from sg_dma_address / sg_dma_len.
 */
#define ATOMOS_COPRO_FLAG_BUFFER_MASK   0xC0U
#define ATOMOS_COPRO_FLAG_HAS_BUFFER    0x40U
#define ATOMOS_COPRO_FLAG_RELEASE_BIT   0x80U
#define ATOMOS_COPRO_FLAG_BUF_RELEASED  0xC0U

#define ATOMOS_COPRO_IPI_MSG_BYTES      32U
#define ATOMOS_COPRO_PAYLOAD_WORDS      5U

/*
 * /dev/copro_comms_data Message Opcodes (verified via Ghidra decompilation of
 * MessageRouter::dispatch 0x214930, ConfigHandler 0x054ce0, DmaSrcElement
 * 0x0c0b40, and Pipeline/MlspSrc TX helpers).
 */
#define ATOMOS_COPRO_MSG_FRAME_V1          0x0001U /* RX: DmaSrcElement 0x0c3210->0x0c2f70->0x0c2e10 */
#define ATOMOS_COPRO_MSG_NDI_CONNECT       0x0017U /* RX: ConfigHandler 0x053ab0 (inline NDI conn) */
#define ATOMOS_COPRO_MSG_VIDEO_TIMING      0x001BU /* TX: 0x0aa4a0 (12B: fps, interlaced, color) */
#define ATOMOS_COPRO_MSG_AUDIO_FORMAT      0x001CU /* TX: 0x0aa6d0 (8B: 48000 Hz, channels, flags) */
#define ATOMOS_COPRO_MSG_AUDIO_CFG         0x001DU /* RX/TX: ConfigHandler 0x053980 (vtable[4]) */
#define ATOMOS_COPRO_MSG_VIDEO_CONFIG      0x0040U /* RX: ConfigHandler 0x052e20 (DMABUF >= 263B) */
#define ATOMOS_COPRO_MSG_VIDEO_CONFIG_GET  0x0041U /* RX: ConfigHandler 0x053610 (vtable[7]) */
#define ATOMOS_COPRO_MSG_VIDEO_FINISH      0x0042U /* RX: DmaSrcElement 0x0bf310 (onVideoFinish/EOS) */
#define ATOMOS_COPRO_MSG_VIDEO_CFG_INLINE  0x0050U /* RX/TX: ConfigHandler 0x053840 / 0x053760 */
#define ATOMOS_COPRO_MSG_VIDEO_STATUS      0x0051U /* RX: ConfigHandler 0x053760 (replies as 0x0050) */
#define ATOMOS_COPRO_MSG_NEW_STREAM        0x0052U /* RX: DmaSrcElement 0x0bf1a0 (onNewStream) */
#define ATOMOS_COPRO_MSG_SEGMENT_START     0x0053U /* RX: DmaSrcElement 0x0bf590 (segment bounds) */
#define ATOMOS_COPRO_MSG_SEGMENT_STOP      0x0054U /* RX: DmaSrcElement 0x0bf030 (onSegmentStop) */
#define ATOMOS_COPRO_MSG_FRAME_V2          0x0055U /* RX: DmaSrcElement 0x0c3440->0x0c3320 (pts/dts) */
#define ATOMOS_COPRO_MSG_MLSP_TX_STAT_0    0x0060U /* TX: 0x088538 / 0x08c608 */
#define ATOMOS_COPRO_MSG_MLSP_TX_STAT_1    0x0061U /* TX: 0x088318 / 0x08c3e8 */
#define ATOMOS_COPRO_MSG_STREAM_CFG_INLINE 0x0070U /* RX: ConfigHandler 0x053d10 (vtable[1]) */
#define ATOMOS_COPRO_MSG_STREAM_CFG_GET    0x0071U /* RX: ConfigHandler 0x0536b0 (vtable[8]) */
#define ATOMOS_COPRO_MSG_STREAMING_CONFIG  0x0072U /* RX: ConfigHandler 0x052f70 (DMABUF >= 426B) */
#define ATOMOS_COPRO_MSG_STREAM_TALKBACK_0 0x0076U /* TX: 0x09d868 */
#define ATOMOS_COPRO_MSG_NDI_CONNECT_SRC   0x0078U /* RX: ConfigHandler 0x0530c0 (DMABUF >= 24B) */
#define ATOMOS_COPRO_MSG_STREAM_TALKBACK_1 0x007AU /* TX: 0x0a3948 */

struct atomos_copro_msg {
    int32_t  dma_fd;                                /* +0x00: exported/imported DMA-BUF fd (-1 if none) */
    uint8_t  flags;                                 /* +0x04: IPI header byte 0 (0x40=buf, 0xC0=release) */
    uint8_t  reserved0;                             /* +0x05: IPI header byte 1 */
    uint16_t msg_type;                              /* +0x06: message identifier / opcode (le16) */
    uint32_t phys_addr;                             /* +0x08: 32-bit DMA/physical address (w[0]) */
    uint32_t size;                                  /* +0x0C: buffer length in bytes (w[1]) */
    union {
        uint8_t  raw[20];                           /* +0x10..0x23: trailing IPI payload bytes */
        uint32_t words[ATOMOS_COPRO_PAYLOAD_WORDS]; /* +0x10..0x23: 5x uint32 trailing words (w[2..6]) */

        /* msg_type == ATOMOS_COPRO_MSG_FRAME_V1 (0x0001): verified in 0x0c2e10 & 0x0bf870 */
        struct {
            uint32_t debug_id;                      /* +0x10 (w[2]): logged by copro-comms.ko as id=%u */
            uint32_t reserved1;                     /* +0x14 (w[3]) */
            uint32_t frame_id_word;                 /* +0x18 (w[4]): frameId = frame_id_word & 0x7FFF */
            uint32_t reserved2;                     /* +0x1C (w[5]): unused in V1 (0) */
            uint8_t  meta_flags;                    /* +0x20 (w[6] b0): bit7=flag, bits[6:0]=flags */
            uint8_t  meta_b1;                       /* +0x21 (w[6] b1): attached to GstAtomosFrameMeta */
            uint16_t meta_u16;                      /* +0x22 (w[6] b2..3): attached to GstAtomosFrameMeta */
        } __attribute__((packed)) frame_v1;

        /* msg_type == ATOMOS_COPRO_MSG_FRAME_V2 (0x0055): verified in 0x0c3440->0x0c3320 */
        struct {
            uint32_t debug_id;                      /* +0x10 (w[2]) */
            uint32_t reserved1;                     /* +0x14 (w[3]) */
            uint32_t frame_id_word;                 /* +0x18 (w[4]): frameId = frame_id_word & 0x7FFF */
            uint32_t pts;                           /* +0x1C (w[5]): presentation timestamp */
            uint32_t dts;                           /* +0x20 (w[6]): decode timestamp */
        } __attribute__((packed)) frame_v2;

        /* DmabufCallbackReadWrite (0x0040, 0x0072, 0x0078): verified in 0x213fe0 */
        struct {
            uint32_t debug_id;                      /* +0x10 (w[2]) */
            uint32_t reserved1;                     /* +0x14 (w[3]) */
            uint32_t struct_offset;                 /* +0x18 (w[4]): byte offset inside dma_fd */
            uint32_t struct_len;                    /* +0x1C (w[5]): payload length (263 / 426 / 24) */
            uint32_t reserved2;                     /* +0x20 (w[6]) */
        } __attribute__((packed)) dmabuf_ref;
    } payload;
} __attribute__((packed));

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(struct atomos_copro_msg) == 36,
               "atomos_copro_msg must match kernel 36-byte ioctl size");
_Static_assert(offsetof(struct atomos_copro_msg, flags) == 4,
               "ipi_msg begins immediately after dma_fd at offset +4");
_Static_assert(offsetof(struct atomos_copro_msg, phys_addr) == 8,
               "phys_addr must be at offset +8");
_Static_assert(offsetof(struct atomos_copro_msg, size) == 12,
               "size must be at offset +12");
_Static_assert(offsetof(struct atomos_copro_msg, payload.frame_v2.dts) == 32,
               "frame_v2.dts must end at byte +36");
#endif

/* ============================================================================
 * 3b. Pixel Format Bitfield & Video Config Payloads (Ghidra Verified)
 * ========================================================================== */

/*
 * Packed 32-bit video pixel-format & geometry descriptor observed across
 * FUN_0031cc10, FUN_0031c8a0, FUN_0031c700, FUN_0031c560, FUN_0031ca90:
 *   bits [2:0]  : color_mode    (1=RGB, 2=ARGB, 3=YCbCr, 4=YOnly, 5=CbCrOnly, 6=Bayer)
 *   bits [4:3]  : subfmt_or_bayer:
 *                   when mode == Bayer (6): 0=RGGB, 1=GRBG, 2=GBRG, 3=BGGR
 *                   otherwise             : 0=4:2:2, 1=4:4:4, 2=4:2:0, 3=packed
 *   bits [6:5]  : bit_depth     (0=8BPP, 1=10BPP, 2=12BPP)
 *   bits [17:8] : width_div8    (width = ((v >> 5) & 0x1FF8))
 *   bits [27:18]: height_div8   (height = ((v >> 15) & 0x0FF8))
 *   bit  [30]   : interlaced    (1=interlaced 'i', 0=progressive 'p')
 */
#define ATOMOS_COLOR_RGB        1U
#define ATOMOS_COLOR_ARGB       2U
#define ATOMOS_COLOR_YCBCR      3U
#define ATOMOS_COLOR_YONLY      4U
#define ATOMOS_COLOR_CBCRONLY   5U
#define ATOMOS_COLOR_BAYER      6U

#define ATOMOS_BAYER_RGGB       0U
#define ATOMOS_BAYER_GRBG       1U
#define ATOMOS_BAYER_GBRG       2U
#define ATOMOS_BAYER_BGGR       3U

#define ATOMOS_CHROMA_422       0U
#define ATOMOS_CHROMA_444       1U
#define ATOMOS_CHROMA_420       2U
#define ATOMOS_CHROMA_PACKED    3U

#define ATOMOS_DEPTH_8BPP       0U
#define ATOMOS_DEPTH_10BPP      1U
#define ATOMOS_DEPTH_12BPP      2U

#define ATOMOS_PXFMT_COLOR_MODE(v)  ((uint32_t)(v) & 0x07U)
#define ATOMOS_PXFMT_PACKING(v)     (((uint32_t)(v) >> 3) & 0x03U)
#define ATOMOS_PXFMT_DEPTH_CODE(v)  (((uint32_t)(v) >> 5) & 0x03U)
#define ATOMOS_PXFMT_WIDTH(v)       (((uint32_t)(v) >> 5) & 0x1FF8U)
#define ATOMOS_PXFMT_HEIGHT(v)      (((uint32_t)(v) >> 15) & 0x0FF8U)
#define ATOMOS_PXFMT_INTERLACED(v)  (((uint32_t)(v) >> 30) & 0x01U)

/*
 * wire format_flags byte (offset +0x0D in msg_video_config_str /
 * +0x0E in msg_streaming_config_str / +0x0A in msg_video_status):
 *   bits [2:0]: depth/format selector (0->0x23 YCbCr422-10b, 1->0x03 YCbCr422-8b, 2->0x13 YCbCr420-8b)
 *   bits [5:4]: chroma (0=422, 1=444, 2=420, 3=packed)
 *   bit  [7]  : no_video_input (1=no input signal, 0=active input)
 */
#define ATOMOS_FMTFLAG_MODE_MASK    0x07U
#define ATOMOS_FMTFLAG_CHROMA_SHIFT 4U
#define ATOMOS_FMTFLAG_CHROMA_MASK  0x30U
#define ATOMOS_FMTFLAG_NO_INPUT     0x80U

/*
 * struct atomos_msg_video_config (msg_video_config_str, 263 bytes = 0x107).
 * Offsets +0x00..+0x17 recovered byte-for-byte from FUN_00159100 (RX decoder)
 * and FUN_00156a10 (0x0041 serializer) inside ConfigHandler.
 */
#define ATOMOS_MSG_VIDEO_CONFIG_SIZE 263U

struct atomos_msg_video_config {
    uint8_t  result;                  /* +0x00: status echo (1=OK, 3=EINVAL, 4=err, 0xFF=busy) */
    uint8_t  direction;               /* +0x01: 0=none, 1=Decode(2), 2=Encode(1) via DAT_00325ea8 */
    uint16_t video_mode;              /* +0x02: pipeline/codec selector (valid: 1..8) */
    uint8_t  interlaced;              /* +0x04: non-zero => interlaced ('i') */
    uint16_t width;                   /* +0x05: active frame width in pixels */
    uint16_t height;                  /* +0x07: active frame height in pixels */
    uint16_t fps_num;                 /* +0x09: frame rate numerator (e.g. 24000, 30000, 23976) */
    uint16_t fps_den;                 /* +0x0B: frame rate denominator (e.g. 1000, 1001, 100) */
    uint8_t  format_flags;            /* +0x0D: packed fmt[2:0] | chroma[5:4] | no_input[7] */
    uint16_t colorimetry;             /* +0x0E: nibbles primaries[3:0], transfer[7:4], matrix[11:8], range[15:12] */
    uint8_t  latency_insensitive;     /* +0x10: GstQueue/sink latency-insensitive flag */
    uint8_t  live_flag;               /* +0x11: live / low-latency option flag */
    uint16_t profile_or_bitrate;      /* +0x12: profile index / override bitrate */
    uint8_t  gop_override_enable;     /* +0x14: non-zero enables explicit gop_length/b_frames */
    uint8_t  gop_length;              /* +0x15: GOP length */
    uint8_t  b_frames;                /* +0x16: B-frame count */
    uint8_t  bitrate_override_enable; /* +0x17: non-zero sets target bitrate = profile_or_bitrate */
    uint8_t  reserved[239];           /* +0x18..+0x106: trailing zero/reserved config bytes */
} __attribute__((packed));

/*
 * struct atomos_msg_streaming_config (msg_streaming_config_str, 426 bytes = 0x1AA).
 * Offsets +0x00..+0x1A9 recovered byte-for-byte from FUN_0015a3e0 and FUN_0015b090.
 */
#define ATOMOS_MSG_STREAMING_CONFIG_SIZE 426U

struct atomos_msg_streaming_config {
    uint8_t  result;                  /* +0x00 */
    uint8_t  direction;               /* +0x01: 0..2 */
    uint16_t bitrate_or_quality;      /* +0x02 */
    uint8_t  live_cloud_upload;       /* +0x04: bit 0 */
    uint8_t  interlaced;              /* +0x05 */
    uint16_t width;                   /* +0x06 */
    uint16_t height;                  /* +0x08 */
    uint16_t fps_num;                 /* +0x0A */
    uint16_t fps_den;                 /* +0x0C */
    uint8_t  format_flags;            /* +0x0E */
    uint16_t colorimetry;             /* +0x0F */
    uint8_t  stream_proto;            /* +0x11: 1..11 (DAT_00325e78 protocol map) */
    uint8_t  latency_insensitive;     /* +0x12 */
    uint16_t reserved_13;             /* +0x13 */
    uint8_t  low_latency_decode;      /* +0x15 */
    uint16_t enc_fps_num;             /* +0x16 */
    uint16_t enc_fps_den;             /* +0x18 */
    char     model[32];               /* +0x1A */
    char     user_name[16];           /* +0x3A */
    char     sys_version[16];         /* +0x4A */
    char     device_aid[32];          /* +0x5A */
    char     device_id[32];           /* +0x7A */
    uint8_t  gop_override_enable;     /* +0x9A */
    uint8_t  gop_length;              /* +0x9B */
    uint8_t  b_frames;                /* +0x9C */
    uint8_t  bitrate_override_enable; /* +0x9D */
    uint8_t  talkback_tx;             /* +0x9E */
    uint8_t  no_ndi_preview;          /* +0x9F */
    uint8_t  audio_count;             /* +0xA0 */
    char     stream_key_or_url[128];  /* +0xA1 */
    char     ndi_groups[128];         /* +0x121 */
    uint8_t  ndi_multicast_enable;    /* +0x1A1 */
    uint32_t ndi_multicast_ip_be;     /* +0x1A2 */
    uint32_t ndi_multicast_mask_be;   /* +0x1A6 */
} __attribute__((packed));

/* Inline response emitted on msg_type 0x0050 when queried via 0x0051 (FUN_00156790) */
struct atomos_msg_video_status {
    uint8_t  direction;               /* +0x00: 0..2 */
    uint8_t  interlaced_bit7;         /* +0x01: bit 7 set when interlaced */
    uint16_t width;                   /* +0x02 */
    uint16_t height;                  /* +0x04 */
    uint16_t fps_num;                 /* +0x06 */
    uint16_t fps_den;                 /* +0x08 */
    uint8_t  format_flags;            /* +0x0A */
    uint8_t  reserved;                /* +0x0B */
} __attribute__((packed));

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(struct atomos_msg_video_config) == ATOMOS_MSG_VIDEO_CONFIG_SIZE,
               "atomos_msg_video_config must match msg_video_config_str 263 bytes");
_Static_assert(sizeof(struct atomos_msg_streaming_config) == ATOMOS_MSG_STREAMING_CONFIG_SIZE,
               "atomos_msg_streaming_config must match msg_streaming_config_str 426 bytes");
_Static_assert(offsetof(struct atomos_msg_streaming_config, ndi_multicast_mask_be) == 0x1A6,
               "ndi_multicast_mask_be must be at +0x1A6");
#endif

#define ATOMOS_COPRO_IOC_MAGIC          0x20U       /* ' ' */
#define ATOMOS_COPRO_IOC_GET_MESSAGE    _IOR(ATOMOS_COPRO_IOC_MAGIC,  0x00U, struct atomos_copro_msg)   /* 0x80242000 */
#define ATOMOS_COPRO_IOC_SEND_MESSAGE   _IOW(ATOMOS_COPRO_IOC_MAGIC,  0x01U, struct atomos_copro_msg)   /* 0x40242001 */
#define ATOMOS_COPRO_IOC_PREPARE_DMABUF _IOWR(ATOMOS_COPRO_IOC_MAGIC, 0x02U, struct atomos_copro_msg)   /* 0xc0242002 */

/* ============================================================================
 * 4. /dev/custom_cma Interface (custom-cma.ko)
 * ========================================================================== */

struct atomos_custom_cma_region {
    char     name[32];  /* +0x00: null-terminated CMA area name, e.g. "codec_output" */
    uint64_t base;      /* +0x20: physical base address from cma_get_base() */
    uint64_t size;      /* +0x28: region size in bytes from cma_get_size() */
};

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(struct atomos_custom_cma_region) == 48,
               "atomos_custom_cma_region must match kernel 48-byte ioctl size");
#endif

#define ATOMOS_CUSTOM_CMA_IOC_MAGIC       0x30U     /* '0' */
#define ATOMOS_CUSTOM_CMA_IOC_GET_REGION  _IOWR(ATOMOS_CUSTOM_CMA_IOC_MAGIC, 0x00U, struct atomos_custom_cma_region) /* 0xc0303000 */
#define ATOMOS_CUSTOM_CMA_IOC_RESIZE      _IOW(ATOMOS_CUSTOM_CMA_IOC_MAGIC,  0x01U, struct atomos_custom_cma_region) /* 0x40303001 */

/* ============================================================================
 * 5. Standard Linux DMA-Heap & DMA-BUF Sync ABI (verified in libgstallocators)
 * ========================================================================== */

struct atomos_dma_heap_allocation_data {
    uint64_t len;
    uint32_t fd;
    uint32_t fd_flags;
    uint64_t heap_flags;
};

#ifndef DMA_HEAP_IOCTL_ALLOC
#define DMA_HEAP_IOCTL_ALLOC _IOWR('H', 0x00, struct atomos_dma_heap_allocation_data) /* 0xc0184800 */
#endif

struct atomos_dma_buf_sync {
    uint64_t flags;
};

#define ATOMOS_DMA_BUF_SYNC_READ   (1ULL << 0)
#define ATOMOS_DMA_BUF_SYNC_WRITE  (2ULL << 0)
#define ATOMOS_DMA_BUF_SYNC_RW     (ATOMOS_DMA_BUF_SYNC_READ | ATOMOS_DMA_BUF_SYNC_WRITE)
#define ATOMOS_DMA_BUF_SYNC_START  (0ULL << 2)
#define ATOMOS_DMA_BUF_SYNC_END    (1ULL << 2)

#ifndef DMA_BUF_IOCTL_SYNC
#define DMA_BUF_IOCTL_SYNC _IOW('b', 0x00, struct atomos_dma_buf_sync) /* 0x40086200 */
#endif

/* ============================================================================
 * 6. /dev/dmaproxy & /dev/allegroIP Reference Opcodes (dmaproxy.ko / al5e.ko)
 * ========================================================================== */

/*
 * Note: al5e.ko struct layouts beyond ioctl sizes require symbol/struct analysis
 * against ctrlsw_encoder/liballegro_encode.so before issuing VCU encode calls.
 * Verified sizes from al5e_ioctl() (0x270) dispatch comparisons:
 */
#define ATOMOS_AL5E_IOC_CREATE_CHANNEL    0xc20c7102UL /* 524 bytes */
#define ATOMOS_AL5E_IOC_DESTROY_CHANNEL   0x00007104UL /* no arg / scalar */
#define ATOMOS_AL5E_IOC_ENCODE_ONE_FRAME  0xc4087105UL /* 1032 bytes */
#define ATOMOS_AL5E_IOC_WAIT_FOR_STATUS   0xc2047106UL /* 516 bytes */
#define ATOMOS_AL5E_IOC_GET_DMA_FD        0xc00c710dUL /* 12 bytes */
#define ATOMOS_AL5E_IOC_GET_DMABUF_ADDR   0xc00c7112UL /* 12 bytes */
#define ATOMOS_AL5E_IOC_PUT_STREAM_BUF    0xc0207116UL /* 32 bytes */
#define ATOMOS_AL5E_IOC_GET_REC           0xc0147117UL /* 20 bytes */
#define ATOMOS_AL5E_IOC_RELEASE_REC       0xc0047118UL /* 4 bytes */

#define ATOMOS_DMAPROXY_IOC_XFER          0xc0083201UL /* copies 24-byte xfer desc (2x u32 fd, 2x u32 off, size_t len) */

/* ============================================================================
 * 7. Page-Aligned mmap & DMA-BUF Helper Wrappers (matches video_pipeline 0x213fe0)
 * ========================================================================== */

struct atomos_mapped_region {
    void   *map_base;   /* base pointer returned by mmap(), MAP_FAILED on error */
    size_t  map_len;    /* len + page_delta passed to mmap()/munmap() */
    size_t  page_delta; /* offset - aligned_offset */
    size_t  req_len;    /* caller's requested byte length */
    void   *data;       /* (uint8_t *)map_base + page_delta */
};

static inline int atomos_mmap_aligned(int fd, uint64_t offset, size_t len,
                                      int prot, int flags,
                                      struct atomos_mapped_region *out)
{
    if (!out || fd < 0 || len == 0) {
        return -EINVAL;
    }

    long pgsz_l = sysconf(_SC_PAGESIZE);
    if (pgsz_l <= 0) {
        return -errno;
    }
    size_t pgsz = (size_t)pgsz_l;
    uint64_t aligned = (offset / pgsz) * pgsz;
    size_t delta = (size_t)(offset - aligned);

    if (len > SIZE_MAX - delta) {
        return -EOVERFLOW;
    }

    size_t total = len + delta;
    void *base = mmap(NULL, total, prot, flags, fd, (off_t)aligned);
    if (base == MAP_FAILED) {
        out->map_base = MAP_FAILED;
        out->map_len = 0;
        out->page_delta = 0;
        out->req_len = 0;
        out->data = NULL;
        return -errno;
    }

    out->map_base = base;
    out->map_len = total;
    out->page_delta = delta;
    out->req_len = len;
    out->data = (uint8_t *)base + delta;
    return 0;
}

static inline int atomos_munmap_aligned(struct atomos_mapped_region *reg)
{
    if (!reg || reg->map_base == MAP_FAILED || reg->map_base == NULL || reg->map_len == 0) {
        return -EINVAL;
    }
    int rc = munmap(reg->map_base, reg->map_len);
    reg->map_base = MAP_FAILED;
    reg->map_len = 0;
    reg->page_delta = 0;
    reg->req_len = 0;
    reg->data = NULL;
    return (rc == 0) ? 0 : -errno;
}

static inline int atomos_dmabuf_sync(int dmabuf_fd, uint64_t sync_flags)
{
    struct atomos_dma_buf_sync sync;
    sync.flags = sync_flags;
    if (dmabuf_fd < 0) {
        return -EINVAL;
    }
    if (ioctl(dmabuf_fd, DMA_BUF_IOCTL_SYNC, &sync) < 0) {
        return -errno;
    }
    return 0;
}

/*
 * Map a video/DMA-BUF frame whose backing allocation in copro-buf-exporter.ko
 * starts at (phys_addr & PAGE_MASK) with mmap offset == 0, while valid frame
 * pixels begin at page_delta = phys_addr & (pagesize - 1) (matches
 * video_pipeline FUN_001c6dd0 gst_dmabuf_allocator_alloc region slicing).
 */
static inline int atomos_mmap_dmabuf_frame(int fd, uint32_t phys_addr,
                                           size_t len, int prot, int flags,
                                           struct atomos_mapped_region *out)
{
    if (out) {
        out->map_base = MAP_FAILED;
        out->map_len = 0;
        out->page_delta = 0;
        out->req_len = 0;
        out->data = NULL;
    }
    if (!out || fd < 0 || len == 0) {
        return -EINVAL;
    }

    errno = 0;
    long pgsz_l = sysconf(_SC_PAGESIZE);
    if (pgsz_l <= 0) {
        return (errno != 0) ? -errno : -EINVAL;
    }

    size_t pgsz = (size_t)pgsz_l;
    size_t delta = (size_t)((uint64_t)phys_addr % (uint64_t)pgsz);
    if (len > SIZE_MAX - delta) {
        return -EOVERFLOW;
    }

    size_t total = len + delta;
    void *base = mmap(NULL, total, prot, flags, fd, 0);
    if (base == MAP_FAILED) {
        return -errno;
    }

    out->map_base = base;
    out->map_len = total;
    out->page_delta = delta;
    out->req_len = len;
    out->data = (uint8_t *)base + delta;
    return 0;
}

static inline const char *atomos_copro_msg_name(uint16_t msg_type)
{
    switch (msg_type) {
    case ATOMOS_COPRO_MSG_FRAME_V1:          return "FRAME_V1";
    case ATOMOS_COPRO_MSG_NDI_CONNECT:       return "NDI_CONNECT";
    case ATOMOS_COPRO_MSG_VIDEO_TIMING:      return "VIDEO_TIMING";
    case ATOMOS_COPRO_MSG_AUDIO_FORMAT:      return "AUDIO_FORMAT";
    case ATOMOS_COPRO_MSG_AUDIO_CFG:         return "AUDIO_CFG";
    case ATOMOS_COPRO_MSG_VIDEO_CONFIG:      return "VIDEO_CONFIG";
    case ATOMOS_COPRO_MSG_VIDEO_CONFIG_GET:  return "VIDEO_CONFIG_GET";
    case ATOMOS_COPRO_MSG_VIDEO_FINISH:      return "VIDEO_FINISH";
    case ATOMOS_COPRO_MSG_VIDEO_CFG_INLINE:  return "VIDEO_CFG_INLINE";
    case ATOMOS_COPRO_MSG_VIDEO_STATUS:      return "VIDEO_STATUS";
    case ATOMOS_COPRO_MSG_NEW_STREAM:        return "NEW_STREAM";
    case ATOMOS_COPRO_MSG_SEGMENT_START:     return "SEGMENT_START";
    case ATOMOS_COPRO_MSG_SEGMENT_STOP:      return "SEGMENT_STOP";
    case ATOMOS_COPRO_MSG_FRAME_V2:          return "FRAME_V2";
    case ATOMOS_COPRO_MSG_MLSP_TX_STAT_0:    return "MLSP_TX_STAT_0";
    case ATOMOS_COPRO_MSG_MLSP_TX_STAT_1:    return "MLSP_TX_STAT_1";
    case ATOMOS_COPRO_MSG_STREAM_CFG_INLINE: return "STREAM_CFG_INLINE";
    case ATOMOS_COPRO_MSG_STREAM_CFG_GET:    return "STREAM_CFG_GET";
    case ATOMOS_COPRO_MSG_STREAMING_CONFIG:  return "STREAMING_CONFIG";
    case ATOMOS_COPRO_MSG_STREAM_TALKBACK_0: return "STREAM_TALKBACK_0";
    case ATOMOS_COPRO_MSG_NDI_CONNECT_SRC:   return "NDI_CONNECT_SRC";
    case ATOMOS_COPRO_MSG_STREAM_TALKBACK_1: return "STREAM_TALKBACK_1";
    default:                                 return "UNKNOWN";
    }
}

struct atomos_pxfmt_info {
    uint32_t    raw;
    uint32_t    width;
    uint32_t    height;
    uint8_t     color_mode;
    uint8_t     packing;
    uint8_t     bit_depth;
    uint8_t     interlaced;
    const char *color_name;
    const char *packing_name;
};

static inline void atomos_pxfmt_decode(uint32_t pxfmt,
                                       struct atomos_pxfmt_info *out)
{
    if (!out) {
        return;
    }

    out->raw = pxfmt;
    out->width = ATOMOS_PXFMT_WIDTH(pxfmt);
    out->height = ATOMOS_PXFMT_HEIGHT(pxfmt);
    out->color_mode = (uint8_t)ATOMOS_PXFMT_COLOR_MODE(pxfmt);
    out->packing = (uint8_t)ATOMOS_PXFMT_PACKING(pxfmt);
    out->interlaced = (uint8_t)ATOMOS_PXFMT_INTERLACED(pxfmt);

    uint32_t depth_code = ATOMOS_PXFMT_DEPTH_CODE(pxfmt);
    if (depth_code == ATOMOS_DEPTH_8BPP) {
        out->bit_depth = 8U;
    } else if (depth_code == ATOMOS_DEPTH_10BPP) {
        out->bit_depth = 10U;
    } else if (depth_code == ATOMOS_DEPTH_12BPP) {
        out->bit_depth = 12U;
    } else {
        out->bit_depth = 0U;
    }

    switch (out->color_mode) {
    case ATOMOS_COLOR_RGB:      out->color_name = "RGB"; break;
    case ATOMOS_COLOR_ARGB:     out->color_name = "ARGB"; break;
    case ATOMOS_COLOR_YCBCR:    out->color_name = "YCbCr"; break;
    case ATOMOS_COLOR_YONLY:    out->color_name = "YOnly"; break;
    case ATOMOS_COLOR_CBCRONLY: out->color_name = "CbCrOnly"; break;
    case ATOMOS_COLOR_BAYER:    out->color_name = "Bayer"; break;
    default:                    out->color_name = "Unknown"; break;
    }

    if (out->color_mode == ATOMOS_COLOR_BAYER) {
        switch (out->packing) {
        case ATOMOS_BAYER_RGGB: out->packing_name = "RGGB"; break;
        case ATOMOS_BAYER_GRBG: out->packing_name = "GRBG"; break;
        case ATOMOS_BAYER_GBRG: out->packing_name = "GBRG"; break;
        case ATOMOS_BAYER_BGGR: out->packing_name = "BGGR"; break;
        default:                out->packing_name = "Unknown"; break;
        }
    } else {
        switch (out->packing) {
        case ATOMOS_CHROMA_422:    out->packing_name = "4:2:2"; break;
        case ATOMOS_CHROMA_444:    out->packing_name = "4:4:4"; break;
        case ATOMOS_CHROMA_420:    out->packing_name = "4:2:0"; break;
        case ATOMOS_CHROMA_PACKED: out->packing_name = "packed"; break;
        default:                   out->packing_name = "Unknown"; break;
        }
    }
}

#ifdef __cplusplus
}
#endif

#endif /* ATOMOS_COPRO_ABI_H */

