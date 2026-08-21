# Mesin Transcribe — Firmware GUI (Dashboard Web)

> **Status:** Developer stage — PoC end-to-end, Phase 2 (AI notulen) + Phase 3 (audio panjang & anti-halusinasi) selesai (Agustus 2026)
> **Acuan:** `Kajian GUI Transcribe Mesin` (folder dokumentasi magang)
> **Basis engine:** `5_mesin_v3/transcribe.py` (faster-whisper + CTranslate2, WDAC workaround)
> **Q&A hasil review:** `JAWABAN_PERTANYAAN.md` (file ini)

## Keputusan Utama (2026-08-16, amendemen 2026-08-17)

| Keputusan | Pilihan | Catatan |
|---|---|---|
| Bentuk UI | **Dashboard web via IP local** | Terminal input `transcribe` → muncul IP → buka browser |
| Backend | FastAPI + SSE (ringan) | Bukan Gradio/Streamlit (ditolak kajian karena overhead) |
| Engine | Modular, reuse dari kajian | `src/core`, `src/notulen`, `src/export` |
| Lingkungan | Venv khusus di folder ini | Terpisah dari 5_mesin_v3 |
| Notulen | **AI via 9router lokal (gemini-3.7-flash)** | DOCX langsung dari transkrip TXT/JSON; fitur MD **dimatikan** |
| Settings | Persistence ke JSON config | Pilihan model/bahasa terakhir tersimpan |

## Risk Management (Awal Perancangan → Status Akhir)

Dokumen acuan: `RISK_MANAGEMENT_ARCHITECTURE_TRANSCRIBE_GUI.md` (kajian,
Februari 2026) + `AMENDEMEN_2026-08-16_WEB_DASHBOARD.md`.

### Metodologi

Skor risiko = **Probability × Impact** (masing-masing skala 1-5).
Peta status: skor ≥ 20 🔴 critical, 12-16 🟠 high, 6-9 🟡 medium, ≤ 6 🟢 low.
Setiap risiko punya strategi mitigasi, aksi konkret, dan residual risk.

### Risk Register Awal — Kajian (Februari 2026)

| ID | Risiko | Kategori | P | I | Skor |
|----|--------|----------|---|---|------|
| R-01 | UI freeze / hang saat transkripsi (blocking main thread) | Technical | 5 | 5 | **25** |
| R-02 | WDAC workaround gagal (import PyAV sebelum patch) | Compatibility | 4 | 5 | **20** |
| R-04 | Adoption resistance — staf BTD non-teknis | Adoption | 4 | 4 | **16** |
| R-05 | Model download pertama (~970 MB) tanpa indikator | UX | 5 | 3 | **15** |
| R-03 | Memory exhaustion audio >1 jam (semua segmen di RAM) | Performance | 3 | 4 | **12** |
| R-07 | PySide6 packaging complexity (PyInstaller + CTranslate2) | Build/Deploy | 3 | 4 | **12** |
| R-13 | Qt event loop conflict dgn bootstrap venv re-exec | Technical | 3 | 4 | **12** |
| R-08 | Large file handling (drag-drop 2 GB, crash) | Robustness | 2 | 4 | **8** |
| R-09 | ffmpeg missing di mesin target | Environment | 3 | 3 | **9** |
| R-10 | Path spasi / karakter non-ASCII (nama file Indonesia) | Compatibility | 4 | 2 | **8** |
| R-14 | Scope creep — fitur tak direncanakan | Project Mgmt | 4 | 2 | **8** |
| R-15 | CTranslate2 version conflict (numpy/onnxruntime) | Dependency | 2 | 4 | **8** |
| R-06 | Breakage CLI workflow existing | Regression | 2 | 3 | **6** |
| R-11 | Concurrent transcription (klik Transcribe 2×) | Robustness | 3 | 2 | **6** |
| R-12 | Settings/config corruption (app crash startup) | Robustness | 2 | 3 | **6** |

### Mitigation Plan Awal (dari kajian, diringkas)

| ID | Strategi | Aksi kunci |
|----|----------|-----------|
| R-01 | Worker thread + signal | Transkripsi di background thread; progress bar; tombol disabled saat running; cancel |
| R-02 | Guarded initialization | WDAC patch dipanggil paling awal, sebelum import faster-whisper; unit test urutan import |
| R-03 | Streaming write + pagination | Tulis JSON bertahap; batasi segmen di RAM; monitor memori |
| R-04 | Progressive disclosure UI | Default sederhana; opsi teknis disembunyikan; tooltip/help |
| R-05 | Download progress dialog | Hook progress download model, tampilkan persen & estimasi |
| R-06 | Backward compat CLI | `5_mesin_v3` tidak disentuh; engine jadi shared library; backup kode |
| R-07 | Early PoC packaging | Uji PyInstaller dini; `--collect-all` CTranslate2 |
| R-08 | File validation | Cek ukuran saat drop; validasi header ffmpeg; pesan error halus |
| R-09 | Startup env check | Cek `ffmpeg --version` saat start; tampilkan warning + link download |
| R-10 | Path normalization | `pathlib.Path`; quote path ffmpeg; uji nama file Indonesia/spasi |
| R-11 | State machine guard | State IDLE→TRANSCRIBING→DONE; disable tombol saat jalan |
| R-12 | Config safety | Try/except load; corrupt → backup + reset default; validasi schema |
| R-13 | Eliminate bootstrap re-exec | Launcher pastikan venv aktif (tanpa re-exec di event loop) |
| R-14 | Strict scope control | MVP fixed; change request didokumentasikan; scope review |
| R-15 | Frozen dependency lock | Pin versi di requirements; lock file; test clean install |

### Contingency Plans (dari kajian)

| Trigger | Contingency | Decision Point |
|---------|-------------|----------------|
| R-01 mitigasi gagal (UI tetap freeze) | Pindah ke framework lebih mudah threading | 1 hari debugging tanpa progres |
| R-02 mitigasi gagal (WDAC crash) | Minta exception policy ke IT | Workaround terlalu fragile |
| R-07 packaging gagal terus | Distribusi folder portable, bukan exe | 2 hari mencoba PyInstaller |
| R-04 adoption rendah | Quick-start wizard + video tutorial | Setelah user testing pertama |
| Scope creep parah | Hard freeze fitur; defer ke v2 | Review mingguan |

### Risiko Baru — Keputusan Web (amendemen 16-08-2026)

| ID | Risiko | Mitigasi | Status |
|----|--------|----------|--------|
| W-01 | Port bentrok saat server start | Deteksi port sibuk → pilih port lain | ⏳ Ditunda (TODO) |
| W-02 | Upload file besar lewat browser | Batasi ukuran + warning | ⏳ Ditunda (write chunked 1 MB sudah ada) |
| W-03 | Browser auto-open di mesin tanpa GUI | Launcher flag `--no-browser` | ✅ Dimitigasi |
| W-04 | SSE reconnect saat job selesai | Client tutup EventSource saat `job_end` | ✅ Dimitigasi |

### Risiko Baru — Phase 2 AI Notulen & Phase 3 (17-08-2026)

| ID | Risiko | Mitigasi | Status |
|----|--------|----------|--------|
| AI-01 | 9router mati saat tombol AI diklik | Error jelas + retry 1× + timeout 600 s; `/api/env` tampilkan status AI | ✅ Dimitigasi |
| AI-02 | AI mengarang fakta/nama/keputusan | Prompt larangan tegas; bagian tak jelas → `[tidak jelas]`; output wajib review manual | ✅ Dimitigasi |
| AI-03 | Transkrip > 180.000 karakter | Dipotong + ditandai di hasil | ✅ Dimitigasi |
| P3-01 | Loop halusinasi pada audio 1-3 jam | `condition_on_previous_text=False` + `hallucination_silence_threshold=2.0` + VAD | ✅ Terverifikasi (stress test) |

### Status Mitigasi Akhir (17-08-2026) — bukti nyata di kode

| ID | Status | Bukti implementasi |
|----|--------|--------------------|
| R-01 | ✅ **Terverifikasi** | Job background thread (`job_manager.py`) + SSE real-time + cancel; uji e2e cancel tanpa crash; tombol disabled saat running |
| R-02 | ✅ **Terverifikasi** | `TranscribeEngine.apply_wdac_patch()` dipanggil paling awal di `server.py`; import faster-whisper hanya lazy di engine; test `test_wdac_patch.py`; transcribe nyata berhasil |
| R-03 | ✅ **Terverifikasi** | Stress test `meet-teknis-MCE.mp3` 1j42m: RSS stabil 514-522 MB, 12 menit, tanpa crash (bukan streaming write — residual risk kecil, lihat catatan) |
| R-04 | ⏳ **Ditunda** | UAT staf belum dijalankan (di luar scope Phase 3 user); UI dibuat sederhana (dropzone + 1 tombol) |
| R-05 | 🟡 **Sebagian** | `/api/env` menampilkan `model_cached` + log "Memuat model..."; belum ada dialog progress download |
| R-06 | ✅ **Terverifikasi** | `5_mesin_v3` tidak disentuh; backup dibuat; baseline CLI v3 tetap jalan (12 s sample) |
| R-07 | ⏳ **Ditunda** | Phase 4 (packaging) ditunda atas keputusan user |
| R-08 | ⏳ **Ditunda** | Di luar scope Phase 3; upload sudah chunked 1 MB |
| R-09 | ✅ **Terverifikasi** | `check_ffmpeg()` di `/api/env` + warning dashboard; test `ffmpeg_available` |
| R-10 | ✅ **Terverifikasi** | Sanitasi nama file + regex `XX_nama` + pathlib; seluruh proyek jalan di path ber-spasi (`D:\SULTAN NAUFAL\...`) |
| R-11 | ✅ **Terverifikasi** | Flag `running` + tombol disabled + cancel; uji e2e |
| R-12 | ✅ **Terverifikasi** | `load_config()` try/except + backup `.json.bak` (R-12 di kode) |
| R-13 | ⏳ **Tidak relevan** | Arah berubah ke web (bukan Qt event loop); bootstrap path venv di docx_converter diperbaiki |
| R-14 | ✅ **Dikelola** | Scope ketat Phase 3 atas keputusan user; setiap keputusan dikonfirmasi |
| R-15 | ✅ **Terverifikasi** | Venv khusus + `requirements_gui.txt` + `baseline_pip_freeze_v3.txt` |

**Catatan residual:** R-03 tidak memakai streaming write (kajian menyarankan) — verifikasi nyata membuktikan memori stabil untuk 1j42m, tapi untuk audio 3 jam + model lebih besar, streaming write tetap menjadi rekomendasi perbaikan berikutnya. W-01/W-02 ditunda ke fase berikutnya.

## Cara Menjalankan

Dari folder ini, di terminal:

```bash
./transcribe                    # git-bash / Linux-style terminal
# atau
transcribe.bat                  # PowerShell / CMD
```

Server start di `http://127.0.0.1:8765`, IP local dicetak di terminal,
browser terbuka otomatis. Akses dari perangkat lain di LAN:

```bash
./transcribe --host 0.0.0.0 --port 8765
```

Catatan: browser dibuka otomatis setelah ~1 detik; `--no-browser` untuk
menonaktifkan. Proses pertama bisa lama karena model di-load ke memori.

## Flow Penggunaan (Panduan Pengguna)

### 1. Menjalankan Mesin

Buka terminal (git-bash / PowerShell) → pindah ke folder proyek:

```bash
cd "D:\SULTAN NAUFAL\KULIAH\MAGANG\MAGANG BTD\proyek\workspace\firmware_transcribe"
./transcribe        # git-bash
# atau
transcribe.bat      # PowerShell / CMD
```

Terminal mencetak alamat (`http://127.0.0.1:8765`) dan browser terbuka
otomatis setelah ~1 detik. Server dihentikan dengan `Ctrl+C` di terminal.

### 2. Cek Status Lingkungan

Header dashboard menampilkan status otomatis: ✅ ffmpeg OK · model small
tersedia · AI gemini/gemini-3.7-flash. Jika ada komponen yang kurang,
muncul peringatan di sini sebelum dipakai.

### 3. Pilih File Audio

Panel kiri "📁 File Audio": seret file ke kotak dropzone, atau klik untuk
memilih. Ekstensi yang diterima: `.mp3 .wav .m4a .flac .aac .ogg`. Setelah
terpilih, tampil nama file + ukuran.

### 4. Pengaturan (Opsional)

Panel "⚙️ Pengaturan": pilih model (`tiny/base/small/medium`) dan bahasa
(`id/en`). Pilihan terakhir **tersimpan otomatis** dan dipulihkan saat
server dinyalakan lagi (settings persistence).

### 5. Transcribe

Klik "🚀 Transcribe" → file di-upload ke server → transkripsi berjalan di
background:
- Progress bar di panel "📊 Status" (persen + pesan)
- Panel "📜 Log & Segmen Real-time" menampilkan potongan teks per segmen
- Jika keliru/terlalu lama → klik "⛔ Batal"

### 6. Lihat Hasil Transkripsi

Panel "📄 Hasil" aktif dengan tab:
- **TXT** — transkrip mentah lengkap
- **JSON** — segmen + metadata (untuk keperluan teknis)

Tombol "Buka folder hasil" membuka folder di Explorer:
`transcribe_hasil\XX_nama\` (isi: `transkrip.txt` + `transkrip.json`).

### 7. Buat Notulen AI (Fitur Utama)

Klik "🤖 Buat Notulen AI" → AI (9router lokal, gemini-3.7-flash) membaca
transkrip dan menyusun notulen rapi (ringkasan eksekutif, pembahasan,
keputusan, tindak lanjut). Proses beberapa menit — progress tampil di
log/status. Setelah selesai:
- Tab "Notulen AI" menampilkan preview notulen
- Link "⬇️ Download DOCX" muncul → klik → file Word
  (`NotulenAI_<nama>.docx`) ter-download, siap diedit/dibagikan

Catatan: **9router harus hidup** (proses node di background, port 20128);
jika mati muncul error jelas di log.

### 8. Riwayat Hasil Lama

Panel "📂 Riwayat" menampilkan semua folder hasil (`01_nama`, `02_nama`,
dst). Klik salah satu → hasil lama bisa dibuka lagi; jika belum punya
notulen AI, tombol "Buat Notulen AI" tersedia di sana juga.

### 9. Akses dari Perangkat Lain (LAN — Tahap Nanti)

```bash
./transcribe --host 0.0.0.0 --port 8765
```

Terminal menampilkan dua alamat: `127.0.0.1` (laptop ini) dan IP LAN
(mis. `http://192.168.1.5:8765`) yang bisa dibuka dari HP/laptop lain di
jaringan yang sama — tanpa install apa pun.

**Ringkasan satu siklus kerja:** buka terminal → ketik `transcribe` →
drag file → klik Transcribe → tunggu → klik Buat Notulen AI → Download
DOCX.

## Struktur

```
firmware_transcribe/
├── transcribe / transcribe.bat   # launcher CLI (per notulen: input "transcribe")
├── main.py                       # [arsip] entry desktop PySide6 (PoC awal)
├── requirements_gui.txt
├── src/
│   ├── core/                     # engine modular (WDAC patch, decode, merge, writer)
│   ├── notulen/generator.py      # [tidak dipakai web] notulen MD heuristik (fitur MD mati)
│   ├── notulen/ai_generator.py   # ★ AI notulen: TXT/JSON → 9router → DOCX (Phase 2)
│   ├── export/docx_converter.py  # MD→DOCX + MdToDocx.from_text (DOCX dari string)
│   ├── utils/                    # config (persistence), ffmpeg_checker, paths
│   ├── services/                 # [arsip] worker Qt (tidak dipakai web)
│   ├── gui/                      # [arsip] window PySide6 (tidak dipakai web)
│   └── web/
│       ├── server.py             # FastAPI app + launcher
│       ├── job_manager.py        # job background (transcribe + AI) + event queue + SSE
│       ├── templates/index.html  # dashboard
│       └── static/               # style.css + app.js
├── uploads/                      # file audio yang di-upload via browser
├── transcribe_hasil/             # output: XX_nama/ (TXT+JSON+[DOCX & notulen_ai.txt via AI])
├── sample_audio/                 # sample 75s untuk tes
└── tests/                        # pytest (30 test)
```

## API

| Endpoint | Fungsi |
|---|---|
| `GET /` | Halaman dashboard |
| `GET /api/env` | Cek ffmpeg + cache model + config AI + settings tersimpan |
| `POST /api/upload` | Upload audio (multipart) |
| `POST /api/transcribe` | Mulai job `{audio_path, model, language}` (MD tidak lagi dipakai) |
| `GET /api/jobs/{id}` | Status job |
| `GET /api/jobs/{id}/stream` | SSE: log, progress, segment, finished, job_end |
| `POST /api/jobs/{id}/cancel` | Batalkan job |
| `POST /api/notulen/ai` | Mulai job AI notulen `{output_dir}` → DOCX (Phase 2) |
| `GET /api/history` | Daftar folder hasil (file `.md` disembunyikan) |
| `GET /api/history/{folder}/file/{file}` | Preview isi file hasil |
| `GET /api/history/{folder}/file/{file}?download=1` | Download file (DOCX/teks) |

## Fitur Notulen AI (Phase 2)

Satu tombol **"🤖 Buat Notulen AI"** di dashboard (panel hasil): AI membaca
`transkrip.txt`/`transkrip.json`, menyusun notulen rapi & terstruktur, lalu
render **langsung ke DOCX** — tanpa file MD perantara.

Output per folder hasil:
- `NotulenAI_<nama>.docx` — notulen resmi siap download
- `notulen_ai.txt` — preview plain di browser (tab "Notulen AI")

Konfigurasi via env var (bisa di `.env` project):
- `TRANSCRIBE_AI_BASE_URL` — default `http://localhost:20128/v1` (9router)
- `TRANSCRIBE_AI_MODEL` — default `gemini/gemini-3.7-flash`
- `TRANSCRIBE_AI_API_KEY` — opsional (9router lokal tanpa key)

Catatan: **9router harus hidup** saat tombol diklik. Job AI berjalan di
background thread (SSE sama seperti transcribe). Transkrip > 180.000 karakter
dipotong (ditandai di hasil). Hasil AI **wajib direview manual** — prompt
melarang AI mengarang fakta, bagian tidak jelas ditulis `[tidak jelas]`.

## Settings Persistence (Phase 2)

Pilihan model/bahasa terakhir tersimpan otomatis ke
`%APPDATA%/TranscribeGUI/config.json` dan dipulihkan saat server start
(prefill dropdown di dashboard).

## Anti-Halusinasi & Audio Panjang (Phase 3)

Transkripsi 1-3 jam stabil dengan output bersih. Parameter default engine
(`src/core/engine.py`) — semuanya bisa di-override via config job:

| Parameter | Default | Fungsi |
|---|---|---|
| `vad_filter` | `True` | Lewati bagian non-speech (silence panjang di rapat) — hemat waktu, tidak ada teks di silence |
| `condition_on_previous_text` | `False` | Cegah loop halusinasi ("terima kasih" berulang) yang sering muncul di audio panjang |
| `hallucination_silence_threshold` | `2.0` | Segmen yang diikuti silence > 2s dianggap halusinasi → di-drop |
| `no_speech_threshold` | `0.6` | Ambang deteksi non-speech (default faster-whisper) |
| `compression_ratio_threshold` | `2.4` | Tolak teks terlalu "mampat" (indikasi halusinasi) |
| `log_prob_threshold` | `-1.0` | Tolak segmen probabilitas rendah |

**Hasil stress test nyata** (17-08-2026, `meet-teknis-MCE.mp3`, 6161 s / 1j42m,
model small int8 CPU):
- Proses **12 menit** (≈8.5x realtime), selesai tanpa crash
- Memori stabil: RSS 514-522 MB sepanjang proses (tidak bocor)
- Cakupan penuh 0 - 6156.9 s; hanya 1 gap > 10 s (silence rapat — VAD bekerja)
- 425 segmen, 7.697 kata, tanpa loop halusinasi atau teks di bagian hening

Skrip stress test: `phase3_stress.py` (output: `transcribe_hasil/07_meet-teknis-MCE/`).

## Test

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

Engine test (tanpa model download, sample_75s.mp3) + web test end-to-end
(TestClient, SSE stream penuh).

## Catatan WDAC (KRITIS)

PyAV diblokir kebijakan WDAC. Engine memakai fake `av` module +
monkey-patch `decode_audio` ke ffmpeg subprocess. Wajib:
- `TranscribeEngine.apply_wdac_patch()` dipanggil SEBELUM import faster-whisper
- Jangan import `faster_whisper` di module-level lain; hanya lazy di engine

## Roadmap (per kajian)

- [x] Phase 0: baseline + folder kerja + venv khusus
- [x] Phase 1: PoC teknis (engine modular, WDAC, threading) — **diadaptasi ke web**
- [x] PoC dashboard web end-to-end (upload → SSE → hasil → cancel → history)
- [x] Phase 2: AI notulen (DOCX dari TXT/JSON via 9router) + settings persistence
- [ ] Phase 2 lanjutan: polish UX (mis. pilihan model AI di UI, konfirmasi sebelum AI)
- [x] Phase 3: hardening — **sesuai kebutuhan user**: audio 1-3 jam stabil + anti-halusinasi (UAT staf & edge case lain ditunda)
- [ ] Phase 4: packaging (portable + venv) — ditunda, pertimbangkan belakangan

## Rekapan Proses Pengembangan (Kronologis Lengkap)

### Konteks Awal — Kondisi Sebelum Pengembangan

Mesin transcribe v3 (`5_mesin_v3/transcribe.py`) hanya bisa dipakai via CLI:
staf non-teknis harus buka VS Code → aktifkan venv → jalankan
`python transcribe.py <audio>` → cari hasil manual di folder. Kendala sistem:
Windows 11 **WDAC memblokir PyAV**, sehingga engine wajib memakai workaround
fake `av` module + decode audio via ffmpeg subprocess. Ada kajian
`Kajian GUI Transcribe Mesin` (4 dokumen) yang menjadi acuan wajib, plus
`generate_docx.py` untuk konversi notulen MD → DOCX.

### 16-08-2026 — Analisis, Fondasi, dan PoC Dashboard Web

Fase kajian yang dijalankan hari ini: **Phase 0 (Foundation)** dan
**Phase 1 (MVP Core)** — dieksekusi paralel dan **diadaptasi ke arah web**
(D-1 revisi, lihat amendemen).

1. **Analisis kajian** — membaca 4 dokumen kajian; menyimpulkan as-is
   (CLI-only, WDAC, model small ~970 MB di cache) dan to-be (GUI untuk
   staf non-teknis). Risiko kritis diidentifikasi: threading anti-freeze,
   WDAC patch, packaging.
2. **Folder & environment terpisah** (rule dari user) — `firmware_transcribe/`
   dengan venv khusus Python 3.12 (faster-whisper 1.2.1, ctranslate2 4.8.1,
   onnxruntime, fastapi, uvicorn, dll). Mesin v3 **tidak disentuh**.
3. **Backup mesin v3** — `backup_5_mesin_v3_20260816/` (transcribe.py,
   generate_docx.py, requirements, README) + `baseline_pip_freeze_v3.txt`
   sebagai jaring pengaman & baseline perbandingan.
4. **Keputusan arsitektur** — arah awal PySide6 (desktop) diganti menjadi
   **dashboard web via IP local**: ketik `transcribe` di terminal → IP tampil
   → browser terbuka otomatis. Backend **FastAPI + SSE** (Gradio/Streamlit
   ditolak kajian karena overhead). Engine modular reuse dari kajian.
5. **Engine modular** — `src/core/` (engine.py dengan WDAC patch + callback
   log/progress/segment/finished/error + cancel, audio_decoder, segment_merger,
   output_writer), `src/notulen/generator.py` (notulen MD heuristik),
   `src/export/docx_converter.py` (MD → DOCX).
6. **Dashboard web end-to-end** — `src/web/server.py` (8 endpoint + SSE),
   `job_manager.py` (job background + event queue), frontend
   `templates/index.html` + `static/` (drag-drop upload, progress bar,
   log segmen real-time, preview, riwayat, tombol batal), launcher
   `transcribe` / `transcribe.bat`.
7. **Verifikasi nyata** — 16/16 pytest lolos (engine + WDAC + web
   end-to-end via TestClient dengan SSE stream penuh); e2e via API:
   upload → transcribe (small, id) → 10 segmen live → finished → file
   TXT/JSON tersimpan → history; cancel tanpa crash; baseline CLI v3
   12 detik untuk sample 75s; DOCX converter OK.
8. **Dokumentasi** — `README_GUI.md` + amendemen kajian
   `AMENDEMEN_2026-08-16_WEB_DASHBOARD.md` agar kajian tetap jadi acuan.

### 17-08-2026 — Phase 2: AI Notulen (keputusan via konfirmasi user)

Kebutuhan user: DOCX **bukan** sekadar transkrip — AI merangkum dan menyusun
notulen rapi, terstruktur, jelas. Keputusan yang dikonfirmasi:
- **Model AI**: lokal via 9router (`http://localhost:20128/v1`, model
  `gemini/gemini-3.7-flash`) — data rapat tidak keluar jaringan.
- **Kapan jalan**: on-demand — tombol "🤖 Buat Notulen AI" di dashboard.
- **Struktur**: bebas — AI menata struktur terbaik (ringkasan eksekutif,
  pembahasan per topik, keputusan, tindak lanjut, dll), asal rapi & jelas.
- **Sumber**: DOCX diambil dari **transkrip TXT/JSON**, bukan dari MD.
- **Fitur MD dimatikan**: checkbox MD dihapus, file `.md` disembunyikan dari
  UI, server memaksa `with_md=False`.

Implementasi:
- `src/notulen/ai_generator.py` — baca transkrip TXT/JSON, prompt notulen
  (larangan mengarang fakta, bagian tidak jelas → `[tidak jelas]`,
  transkrip > 180.000 karakter dipotong), panggil 9router via httpx
  (retry 1x, timeout 600s), render **langsung ke DOCX** via
  `MdToDocx.from_text` (baru — tanpa file .md perantara). Output:
  `NotulenAI_<nama>.docx` + `notulen_ai.txt` (preview).
- `src/export/docx_converter.py` — dukungan mode string (`text=`) + fix bug
  bootstrap path venv (salah hitung lokasi).
- `src/web/job_manager.py` — job jenis baru `ai_notulen` (`create_ai`),
  reuse event queue + SSE yang sama.
- `src/web/server.py` — `POST /api/notulen/ai` (validasi folder hasil
  `XX_nama` + cegah path traversal), `?download=1` untuk download file,
  history menyembunyikan `.md`, `/api/env` menampilkan config AI + settings,
  transcribe menyimpan settings terakhir.
- Frontend — tab "Notulen AI", tombol Buat Notulen AI + progress SSE,
  link "⬇️ Download DOCX", prefill model/bahasa dari settings tersimpan,
  tanpa checkbox MD.
- `src/utils/config.py` — settings persistence ke
  `%APPDATA%/TranscribeGUI/config.json`.

Verifikasi: **30/30 test** lolos (14 test AI baru, semua panggilan LLM
di-mock); e2e nyata dengan 9router asli — upload → transcribe → AI job →
DOCX 37 KB ter-generate berisi notulen rapi (ringkasan eksekutif,
pembahasan, catatan, daftar isi), history tanpa `.md`. Artefak tes
dibersihkan.

### 17-08-2026 — Phase 3: Audio Panjang 1-3 Jam & Anti-Halusinasi

Kebutuhan user (tegas): hanya memastikan mesin bisa mentranskripsi audio
**1-3 jam** dengan **output bersih dan meminimalisir halusinasi kata**.
Hal di luar kebutuhan (UAT staf, edge case upload, polish) **ditunda** —
konfirmasi dulu bila ada pekerjaan keluar scope.

Perubahan di `src/core/engine.py` (default, bisa di-override per job):

| Parameter | Default | Alasan |
|---|---|---|
| `vad_filter` | `True` | Lewati silence panjang (rapat) — hemat waktu, tidak ada teks di bagian hening |
| `condition_on_previous_text` | `False` | Cegah loop halusinasi ("terima kasih" berulang) khas audio panjang |
| `hallucination_silence_threshold` | `2.0` | Drop segmen yang diikuti silence > 2s (dianggap halusinasi) |
| `no_speech_threshold` | `0.6` | Ambang deteksi non-speech |
| `compression_ratio_threshold` | `2.4` | Tolak teks terlalu mampat (indikasi halusinasi) |
| `log_prob_threshold` | `-1.0` | Tolak segmen probabilitas rendah |

**Stress test nyata** — `meet-teknis-MCE.mp3` (5_mesin_v3, 6161 s / 1j42m,
80 MB), model small int8 CPU, via `phase3_stress.py` dengan monitor memori:

| Metrik | Hasil |
|---|---|
| Waktu proses | **12 menit** (≈8.5x realtime) |
| Memori (RSS) | stabil **514-522 MB** sepanjang proses — tanpa kebocoran |
| Cakupan transkripsi | 0 - 6156.9 s dari 6161 s (full) |
| Segmen | 425 segmen, 7.697 kata (≈75 kata/menit, normal rapat) |
| Silence | hanya 1 gap > 10 s — VAD bekerja, tidak ada teks halusinasi di silence |
| Halusinasi loop | tidak ada ("mas a." 4x = ucapan asli nama orang) |
| Kualitas teks | natural dari awal (setup screen share) → tengah (pembahasan) → akhir (penutup rapat) |

Verifikasi: **32/32 test** lolos (2 test baru untuk forwarding parameter
anti-halusinasi dengan model di-mock).

### Kesesuaian dengan Exit Criteria Kajian

| Fase kajian | Exit criteria (kajian) | Realisasi |
|---|---|---|
| Phase 0 Foundation | Setup env; PoC window→worker→progress; WDAC di context app | ✅ Venv khusus, engine modular, WDAC patch di awal server |
| Phase 1 MVP | Drag-drop; pilih model/bahasa; transcribe background; progress real-time; cancel; TXT/JSON; tanpa freeze; cek ffmpeg; WDAC berfungsi | ✅ Semua terpenuhi di dashboard web (16 test + e2e) |
| Phase 2 Polish & Export | Settings tersimpan; riwayat; export DOCX; notulen MD (toggle) | ✅ Settings persistence + history + export DOCX via AI. Notulen MD toggle **diganti** AI notulen (keputusan user) |
| Phase 3 Hardening | Edge case; optimasi memori; cancel graceful; packaging; UAT | 🟡 Sebagian sesuai scope user: audio 1-3 jam + anti-halusinasi **terverifikasi**; packaging (Phase 4) & UAT staf **ditunda** |

### Status Akhir (17-08-2026)

- PoC end-to-end berjalan; Phase 2 (AI notulen + settings persistence) dan
  Phase 3 (audio panjang + anti-halusinasi) **selesai & terverifikasi nyata**.
- `src/notulen/generator.py` (MD heuristik) tidak dipakai dashboard — fitur
  MD dimatikan, file MD lama tetap di disk tapi disembunyikan dari UI.
- 9router lokal wajib hidup saat tombol AI diklik (error jelas jika mati).
- Berkas tersimpan: `README_GUI.md`, `JAWABAN_PERTANYAAN.md`,
  `phase3_stress.py`, hasil stress test di `transcribe_hasil/07_meet-teknis-MCE/`.

## File yang Tidak Dipakai Lagi

`src/services/`, `src/gui/`, `main.py`, `tests/poc_headless.py` adalah
arsip dari arah desktop PySide6 (diputuskan ganti ke web). Engine dan
test-nya tetap dipakai. Hapus saat bersih-bersih jika sudah yakin.

`src/notulen/generator.py` (notulen MD heuristik) tidak dipakai dashboard —
fitur MD dimatikan, notulen diganti AI. File MD lama di folder hasil tetap
disimpan di disk tapi disembunyikan dari UI.

-------------------------------------------------------------------------------------------------------------------
## PERTANYAAN
1. tadi kamu semapt menyinggung penggunaan API, server local, port 8766 dan 8765. itu semua fungsinya untuk apa ?
2. maksud dari Akses dari perangkat lain di LAN itu bagaimana
3. apa itu PoC
4. roadmap selanjutnya phase 2, 3 dan 4 itu untuk apa ?
5. sebutkan secara eksplisit apa yang kamu lakukan untuk mengembangkan dashboard ini dan jelaskn fungsi fungsinya juga
6. apakah pembuatan dashboard ini aman ? berikan argument berdasarkan semua tahapan tahapan yang kamu lakukan
7. apakah dashboard tersebut dibuat menggunakan html ?
8. jelaskan flow sistemnya dari awal hingga akhir beserta tools tools yang digunakan disetiap flownya
9. dokumentasikan proses pembuatan dashboard ini secara lengkap di README ini
10. apa fungsi backup mesin v3 jika folder 5_mesin_v3 masih utuh ?
11. apa itu Linkt dan mengapa tadi aku melihat ada python 3.11 ? bukanya kita hanya menggunakan python 3.12.10
12. karena untuk generate docx disini menggunakan model dari 9router. bagaimana caranya dashboard tersebut membuka server local dari 9router ? karena untuk menjalankan modelnya, dahsboard 9router kan seharusnya dibuka terlebih dahulu 