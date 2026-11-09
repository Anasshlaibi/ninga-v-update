//! Benchmark specifically tailored for evaluating software compression on AArch64
//! Target Reference: Atomos Ninja V (Quad-Core Cortex-A53 @ 1.2 GHz, ZynqMP XCZU3EG)
//! Input: 4K UHD (3840x2160) 12-bit Bayer RAW
//! Compression: intoPIX TICO-RAW (Star-Tetrix Bayer Decorrelation + 5/3 Reversible DWT + Bit-packing)
//!
//! NOTE: Execution under QEMU user emulation (qemu-aarch64-static) measures software functional
//! correctness and algorithmic behavior on translated AArch64 instructions, but DOES NOT represent
//! real-time silicon cycle timing or cache/memory contention of the physical Cortex-A53 cores.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use bluecompress::frame::{encode_frame, forward_star_tetrix, forward_wavelet, Coeffs, Planes};
use bluecompress::tico::{Layout, TicoHeader};
use bluecompress::bpp_of;

include!("common/synthetic_6k.rs");

/// Generate synthetic raw Bayer quad planes (untransformed pixels)
fn generate_raw_bayer(l: &Layout, seed: u32) -> Planes {
    let mut pl = Planes::new(l.cw, l.ch);
    for c in 0..4 {
        for y in 0..l.ch {
            for x in 0..l.cw {
                let (fx, fy) = (x as f32 / l.cw as f32, y as f32 / l.ch as f32);
                let hill = 0.5 + 0.1 * (fx * 9.0).sin();
                let v = if fy < hill {
                    9000.0 - 4000.0 * fy + 300.0 * c as f32
                } else {
                    let leaf = (fx * 400.0).sin() * (fy * 300.0).cos();
                    -4000.0 + 5000.0 * leaf + 1500.0 * noise(x / 3, y / 3, seed + 7)
                };
                pl.data[c * l.cw * l.ch + y * l.cw + x] = (v + 900.0 * noise(x, y, seed + c as u32)) as i32;
            }
        }
    }
    pl
}

/// Full end-to-end compression pipeline for a single frame:
/// Raw Bayer -> Star-Tetrix Decorrelation -> 5/3 Wavelet -> Bit-packing
fn compress_full_frame(hd: &TicoHeader, l: &Layout, raw_pl: &Planes, budget: i32) -> (Vec<u8>, f64, f64, f64) {
    let mut pl = raw_pl.clone();
    
    // Stage 1: Star-Tetrix
    let t0 = Instant::now();
    forward_star_tetrix(&mut pl);
    let st_sec = t0.elapsed().as_secs_f64();

    // Stage 2: 5/3 Wavelet
    let mut coeffs = vec![0i32; Coeffs::len(l)];
    let t1 = Instant::now();
    forward_wavelet(l, &pl, &mut coeffs);
    let dwt_sec = t1.elapsed().as_secs_f64();

    // Stage 3: Bit-packing / Frame Encode
    let t2 = Instant::now();
    let cs = encode_frame(hd, l, &coeffs, budget).unwrap();
    let pack_sec = t2.elapsed().as_secs_f64();

    (cs, st_sec, dwt_sec, pack_sec)
}

fn main() {
    println!("================================================================================");
    println!(" AArch64 Full-Frame RAW Compression Benchmark (Atomos Ninja V Reference)");
    println!(" Pipeline: Raw Bayer -> Star-Tetrix -> 5/3 DWT -> Bit-packing");
    println!(" Resolution: 3840x2160 (4K UHD) | Color: 12-bit Bayer | Test Mode: Full Frame");
    println!(" Execution: QEMU User Emulation (Host translated, not physical A53 silicon timing)");
    println!("================================================================================");

    let (w, h) = (3840u16, 2160u16);
    let (hd, l) = header(w, h);

    let raw_bayer_bytes = (w as u64) * (h as u64) * 12 / 8; // 12-bit Bayer = 12,441,600 bytes
    println!("Input frame: {} x {} 12-bit Bayer ({:.2} MB/frame)", w, h, raw_bayer_bytes as f64 / 1_048_576.0);

    // [1/3] Single-frame pipeline stage breakdown
    println!("\n[1/3] Detailed Breakdown of Full-Frame Stages (Single Worker):");
    let test_raw = generate_raw_bayer(&l, 100);
    let budget = 120i32; // Standard nominal quality

    let (sample_out, st_s, dwt_s, pack_s) = compress_full_frame(&hd, &l, &test_raw, budget);
    let total_s = st_s + dwt_s + pack_s;
    let comp_bytes = sample_out.len();
    let bpp = bpp_of(comp_bytes as f64, w as u32, h as u32);
    let ratio = raw_bayer_bytes as f64 / comp_bytes as f64;

    println!("  - Stage 1 (Star-Tetrix Decorrelation): {:.2} ms ({:4.1}%)", st_s * 1000.0, (st_s / total_s) * 100.0);
    println!("  - Stage 2 (5/3 Discrete Wavelet DWT):   {:.2} ms ({:4.1}%)", dwt_s * 1000.0, (dwt_s / total_s) * 100.0);
    println!("  - Stage 3 (Precinct Bit-Packing):       {:.2} ms ({:4.1}%)", pack_s * 1000.0, (pack_s / total_s) * 100.0);
    println!("  -> Total Single-Frame Latency:          {:.2} ms", total_s * 1000.0);
    println!("  -> Output: {} bytes ({:.2} MB) | {:.2} bpp | Compression Ratio: {:.2}:1", 
        comp_bytes, comp_bytes as f64 / 1_048_576.0, bpp, ratio);

    // [2/3] Multithreaded Full-Frame Compression Scaling
    println!("\n[2/3] Multithreaded Full-Frame Compression Scaling (1, 2, 4 worker threads):");
    println!("      Each thread runs the complete end-to-end pipeline: Bayer -> Tetrix -> DWT -> Pack");

    // Prepare 4 distinct raw Bayer scenes
    let raw_scenes: Vec<Planes> = (0..4).map(|i| generate_raw_bayer(&l, 10 + i as u32)).collect();

    for &num_workers in &[1, 2, 4] {
        let frame_count = 8;
        let next = AtomicUsize::new(0);
        let out: Mutex<Vec<Option<usize>>> = Mutex::new(vec![None; frame_count]);
        let t_start = Instant::now();

        std::thread::scope(|sc| {
            for _ in 0..num_workers {
                sc.spawn(|| loop {
                    let idx = next.fetch_add(1, Ordering::SeqCst);
                    if idx >= frame_count {
                        return;
                    }
                    let (cs, _, _, _) = compress_full_frame(&hd, &l, &raw_scenes[idx % 4], budget);
                    out.lock().unwrap()[idx] = Some(cs.len());
                });
            }
        });

        let elapsed_sec = t_start.elapsed().as_secs_f64();
        let fps = frame_count as f64 / elapsed_sec;
        let mb_s = (comp_bytes as f64 * fps) / 1_048_576.0;
        let latency_per_frame_ms = (elapsed_sec / frame_count as f64) * 1000.0;
        println!("  - Workers: {:1} | Time: {:.3}s | Mean Latency: {:6.2} ms/frame | Throughput: {:5.2} FPS ({:5.1} MB/s)",
            num_workers, elapsed_sec, latency_per_frame_ms, fps, mb_s);
    }

    println!("\n[3/3] Critical Technical Distinctions:");
    println!("  1. FULL-FRAME vs REQUANT: This benchmark measures true full-frame compression from raw pixels.");
    println!("  2. EMULATION LIMITATION: QEMU user mode executes on the host CPU via JIT translation;");
    println!("     it cannot measure Cortex-A53 in-order pipeline stall cycles, memory bus contention,");
    println!("     or LPDDR4 bandwidth on the physical Zynq UltraScale+ board.");
    println!("  3. DMA & FPGA STATUS: Real-time 24/60fps recording on the physical Ninja V relies on");
    println!("     hardware-level FPGA bitstreams (`DPGA*.BIN`) and direct DMA paths, NOT software CPU encoding.");
    println!("================================================================================");
}
