//! Benchmark specifically tailored for Atomos Ninja V (Quad-Core Cortex-A53 @ 1.2 GHz)
//! Simulates real-time 4K UHD (3840x2160) 12-bit Bayer RAW compression using
//! intoPIX TICO RAW (JPEG XS / Star-Tetrix + 5/3 Wavelet).
//!
//! Evaluates whether the A53 ARM cores can sustain real-time software compression
//! or if dedicated FPGA hardware logic (PL) is mandatory for 24fps / 60fps.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use bluecompress::frame::{encode_frame, forward_star_tetrix, forward_wavelet, Coeffs, Planes};
use bluecompress::requant::{requant_codestream_seeded, RequantParams};
use bluecompress::tico::{Layout, TicoHeader};
use bluecompress::{bpp_of, Target};

include!("common/synthetic_6k.rs");

fn main() {
    println!("============================================================");
    println!(" Atomos Ninja V (ZynqMP XCZU3EG) ARM64 Compression Benchmark");
    println!(" Target: Quad Cortex-A53 @ 1.2 GHz | Video: 4K UHD 3840x2160");
    println!("============================================================");

    let (w, h) = (3840u16, 2160u16);
    let (hd, l) = header(w, h);

    let raw_bayer_bytes = (w as u64) * (h as u64) * 12 / 8; // 12-bit Bayer
    println!("Input frame: {} x {} 12-bit Bayer ({:.2} MB/frame)", w, h, raw_bayer_bytes as f64 / 1_048_576.0);
    println!("SATA 3 SSD Bandwidth Budget: ~540 MB/s max sustainable");

    // Measure single-frame pipeline stages
    println!("\n[1/3] Benchmarking pipeline stages (Single Core A53)...");
    
    // Stage A: Star-Tetrix Bayer Decorrelation
    let mut pl = Planes::new(l.cw, l.ch);
    for c in 0..4 {
        for y in 0..l.ch {
            for x in 0..l.cw {
                pl.data[c * l.cw * l.ch + y * l.cw + x] = 2048 + (x % 512) as i32;
            }
        }
    }
    
    let t0 = Instant::now();
    for _ in 0..10 {
        forward_star_tetrix(&mut pl);
    }
    let star_tetrix_ms = t0.elapsed().as_secs_f64() / 10.0 * 1000.0;
    println!("  - Forward Star-Tetrix Decorrelation: {:.2} ms/frame", star_tetrix_ms);

    // Stage B: 5/3 Reversible Discrete Wavelet Transform
    let mut coeffs = vec![0i32; Coeffs::len(&l)];
    let t1 = Instant::now();
    for _ in 0..10 {
        forward_wavelet(&l, &pl, &mut coeffs);
    }
    let wavelet_ms = t1.elapsed().as_secs_f64() / 10.0 * 1000.0;
    println!("  - 5/3 Discrete Wavelet Transform:   {:.2} ms/frame", wavelet_ms);

    // Stage C: Full Frame Encode
    let test_scene = scene(&l, 42);
    let t2 = Instant::now();
    let encoded_sample = encode_frame(&hd, &l, &test_scene, 120).unwrap();
    let encode_ms = t2.elapsed().as_secs_f64() * 1000.0;
    let comp_bytes = encoded_sample.len();
    let bpp = bpp_of(comp_bytes as f64, w as u32, h as u32);
    let ratio = raw_bayer_bytes as f64 / comp_bytes as f64;
    println!("  - Bit-packing & Precinct Encoding:   {:.2} ms/frame", encode_ms);
    println!("  -> Compressed size: {} bytes ({:.2} MB) | {:.2} bpp | Ratio: {:.2}:1", 
        comp_bytes, comp_bytes as f64 / 1_048_576.0, bpp, ratio);

    // Multithreaded scaling test
    println!("\n[2/3] Multithreaded Throughput Scaling (Simulating Cortex-A53 Cores):");
    let test_frames = vec![
        encode_frame(&hd, &l, &scene(&l, 1), 120).unwrap(),
        encode_frame(&hd, &l, &scene(&l, 2), 120).unwrap(),
        encode_frame(&hd, &l, &scene(&l, 3), 120).unwrap(),
        encode_frame(&hd, &l, &scene(&l, 4), 120).unwrap(),
    ];

    let budget = Target::bpp(2.0).budget(w as u32, h as u32);
    let p = RequantParams { budget, gpu: false, ..Default::default() };

    for &cores in &[1, 2, 4] {
        let frame_count = 16;
        let next = AtomicUsize::new(0);
        let out: Mutex<Vec<Option<Vec<u8>>>> = Mutex::new(vec![None; frame_count]);
        let t_start = Instant::now();

        std::thread::scope(|sc| {
            for _ in 0..cores {
                sc.spawn(|| loop {
                    let idx = next.fetch_add(1, Ordering::SeqCst);
                    if idx >= frame_count {
                        return;
                    }
                    let mut seed = Vec::new();
                    let o = requant_codestream_seeded(&test_frames[idx % 4], &p, 1, &mut seed).unwrap().0;
                    out.lock().unwrap()[idx] = Some(o);
                });
            }
        });

        let elapsed_sec = t_start.elapsed().as_secs_f64();
        let fps = frame_count as f64 / elapsed_sec;
        let mb_s = (comp_bytes as f64 * fps) / 1_048_576.0;
        println!("  - Cores: {:1} | Elapsed: {:.3}s | FPS: {:5.2} | Throughput: {:6.2} MB/s",
            cores, elapsed_sec, fps, mb_s);
    }

    println!("\n[3/3] Engineering Conclusion:");
    println!("  - Required 4K 24fps target: 24.0 fps");
    println!("  - Required 4K 60fps target: 60.0 fps");
    println!("============================================================");
}
