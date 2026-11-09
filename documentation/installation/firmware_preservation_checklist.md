# Official Atomos Ninja V Firmware Preservation Checklist

This checklist governs the acquisition, verification, and immutable archival of the official **Atomos Ninja V** firmware (`ATOMNJV.FW`, AtomOS `11.19.00`).

---

## Status Summary (Phase 0 Audit)

- [x] **1. Verify Target Hardware Model:** Original Atomos Ninja V (5-inch model) — *Confirmed (Not Ninja V+, Ninja Ultra, Ninja RAW, or Ninja TX)*.
- [x] **2. Locate Official Firmware Binary:** Found at `C:\Users\HELIOS NEO 16\Documents\framatomos\ATOMNJV_11.19.0 (1)\ATOMNJV.FW`.
- [x] **3. Verify Exact File Size:** `319,558,064` bytes (`304.75 MiB`).
- [x] **4. Compute Cryptographic Checksums:**
  - **SHA-256:** `65e14e67bcc2624115300624d967634042601f23e9574e75ee7f06f2c8004be1`
  - **SHA-1:** `a30ea978a0801f07284be8ecb079997a0fd9f153`
  - **MD5:** `76b48aaa512d146992aed6fbbf68e987`
- [x] **5. Copy to Immutable Repository Location:** Copied to `verdanove-ninja-lab/firmware/original/ATOMNJV.FW`.
- [x] **6. Enforce Read-Only File Attribute:** `IsReadOnly = True` applied on `verdanove-ninja-lab/firmware/original/ATOMNJV.FW`.
- [x] **7. Record Checksums & Manifest:** Written to `SHA256SUMS`, `firmware/hashes/SHA256SUMS`, `firmware_manifest.json`, and `firmware/metadata/firmware_manifest.json`.
- [ ] **8. Archive Official Release Notes PDF (Optional):** If the original ZIP download included `AtomOS_11.19.00_Release_Notes.pdf`, copy it into `verdanove-ninja-lab/firmware/release_notes/`.

---

## Integrity Verification Command

Before running any Phase 1 extraction script, always verify that the immutable copy matches the recorded SHA-256 hash:

### PowerShell
```powershell
$expected = "65E14E67BCC2624115300624D967634042601F23E9574E75EE7F06F2C8004BE1"
$actual = (Get-FileHash -Algorithm SHA256 "firmware\original\ATOMNJV.FW").Hash
if ($actual -eq $expected) {
    Write-Host "OK: ATOMNJV.FW integrity verified ($actual)" -ForegroundColor Green
} else {
    Write-Error "MISMATCH: Expected $expected but got $actual"
}
```

### WSL2 / Linux
```bash
sha256sum -c SHA256SUMS
```

---

## Handling Rules for Phase 1+

1. **Never open `firmware/original/ATOMNJV.FW` in write mode.**
2. **All unpacking/carving operations must output exclusively to `firmware/extracted/`.**
3. **Preserve the external folder `../ATOMNJV_11.19.0 (1)/ATOMNJV.FW` as a secondary cold backup.**
