# 🎙️ Mesin Live v4 — Live Recording + Transkripsi Real-Time (STANDALONE)

**Versi:** 4.0 (standalone)
**Lokasi:** `6_mesin_v4/`
**Dibuat:** Agustus 2026
**Lingkungan:** Python 3.12 + Windows 11 (WDAC-enabled)

**Mesin ini 100% mandiri** — satu file Python, tanpa ketergantungan ke mesin
lain di workspace. Diadopsi dari `5_mesin_v3` (mesin transkripsi file) dengan
semua bagian yang tidak diperlukan dihapus.

---

## 📋 Daftar Isi

1. [Apa Itu Mesin Ini](#-apa-itu-mesin-ini)
2. [Struktur Folder](#-struktur-folder)
3. [Prasyarat](#-prasyarat)
4. [Penggunaan](#-penggunaan)
5. [Skenario Google Meet (VB-CABLE)](#-skenario-google-meet-vb-cable)
6. [Output](#-output)
7. [Mekanisme Teknis](#-mekanisme-teknis)
8. [FAQ](#-faq)

---

## ✨ Apa Itu Mesin Ini

Rekam audio dari perangkat input (mikrofon fisik ATAU virtual cable seperti
VB-CABLE) dan transkripsikan **saat itu juga** per chunk. Outputnya:
`transkrip.txt` + `transkrip.json` + `Notulen_*.md` — semuanya otomatis.

Kegunaan utama di tim BTD: transkripsi rapat/meeting/diskusi Google Meet tanpa
harus mengetik manual.

---

## 📁 Struktur Folder

```
6_mesin_v4/
├── .venv/                # Python virtual environment (Python 3.12.10)
├── transcribe_hasil/     # OUTPUT — folder hasil transkripsi (auto-created)
│   └── XX_live_YYYYMMDD-HHMM/
├── live_transcribe.py    # 🎙️ SATU-SATUNYA mesin (semua logika di sini)
├── requirements.txt      # Dependency: faster-whisper + numpy
└── README.md
```

Tidak ada file lain. Mesin ini tidak memakai `transcribe.py`, `generate_docx.py`,
`audio_archive`, atau `zip_archive`.

---

## 📋 Prasyarat

1. **Python 3.12** — venv sudah dibuat di `.venv/` (tidak menyentuh Python global).
2. **ffmpeg sistem** — `ffmpeg -version` untuk cek. Install: `winget install Gyan.FFmpeg.Essentials`
3. **Perangkat input** — mikrofon fisik, atau virtual cable (VB-CABLE) untuk menangkap suara komputer.
4. **Internet** — hanya saat pertama kali model di-download dari HuggingFace (~970 MB untuk `small`).

---

## 🎙️ Penggunaan

```powershell
cd "D:\SULTAN NAUFAL\KULIAH\MAGANG\MAGANG BTD\proyek\workspace\6_mesin_v4"

# 1. Lihat perangkat input yang terdeteksi
.venv\Scripts\python.exe live_transcribe.py --list-devices

# 2. Mulai sesi live (default: model small, bahasa id, chunk 15 detik)
.venv\Scripts\python.exe live_transcribe.py

# 3. Berhenti: tekan Ctrl+C
```

### Opsi CLI

```
--model small|medium|tiny|base|large   Model Whisper (default: small)
--language id|en|...                   Kode bahasa (default: id)
--device "<nama>"                      Perangkat input spesifik (lihat --list-devices)
--chunk-sec <detik>                    Durasi tiap chunk (default: 15)
--max-min <menit>                      Auto-stop setelah N menit
--once                                 Rekam 1 chunk lalu selesai (tes cepat)
--compute-type int8|float32            Tipe komputasi CTranslate2 (default: int8)
```

---

## 🎥 Skenario Google Meet (VB-CABLE)

**Tujuan:** hanya suara yang KELUAR dari komputer (suara peserta Meet) yang
ditranskrip — tanpa noise luar (mikrofon fisik tidak dipakai).

### Setup sekali saja
1. Install VB-CABLE (sudah terpasang di mesin ini, dari vb-audio.com).
2. Windows: Win+R → `mmsys.cpl` → tab Recording → klik kanan
   **"CABLE Output (VB-Audio Virtual Cable)"** → Properties → tab **Listen**
   → centang **"Listen to this device"** → *Playback through*: pilih
   headsetmu → OK.
   (Supaya kamu tetap MENDENGAR meeting meski output Meet dialihkan ke kabel.)

### Saat meeting
```powershell
# 1. Nyalakan mesin DULU
.venv\Scripts\python.exe live_transcribe.py --device "CABLE Output (VB-Audio Virtual Cable)"

# 2. GMeet → Settings → Audio:
#    Speaker     → "CABLE Input" (yang TANPA "16 Ch")
#    Microphone  → mute / mikrofon fisik (JANGAN pilih CABLE — nanti loop)

# 3. Meeting selesai → Ctrl+C → notulen otomatis jadi
```

### Alur audio
```
Suara peserta → Meet → CABLE Input → [kabel virtual] → CABLE Output
                                                       ├─→ live_transcribe.py (transkripsi)
                                                       └─→ headsetmu (via Listen to this device)
Noise luar (ambient) → mikrofon fisik → TIDAK direkam
```

### Pengecekan transkripsi berjalan
- Konsol mencetak teks per chunk: `[HH:MM:SS] <teks>`. Chunk pertama butuh
  ±15–30 detik sebelum teks pertama muncul.
- `transkrip.txt` di folder hasil bertambah real-time (buka di VS Code).
- Kalau chunk hening: muncul `(hening — tidak ada ucapan terdeteksi)`.
- Kalau konsol terus "hening" padahal meeting ramai → cek Speaker Meet
  (harus "CABLE Input") dan `--device` transcriber (harus "CABLE Output").

---

## 📄 Output

Setiap sesi membuat folder `transcribe_hasil/XX_live_YYYYMMDD-HHMM/`
(XX = penomoran urut otomatis):

| File | Isi |
|------|-----|
| `transkrip.txt` | Teks mentah, per chunk dengan timestamp jam dinding `[HH:MM:SS]` |
| `transkrip.json` | Metadata: model, bahasa, durasi, jumlah chunk, segmen (start/end = detik sesi) |
| `Notulen_live_*.md` | Draft notulen: peserta, agenda, ringkasan, keputusan & tindak lanjut |

> Notulen MD dibuat template heuristik (bukan AI) — **review manual sebelum
> distribusi**.

---

## 🔧 Mekanisme Teknis

| Komponen | Teknologi |
|----------|-----------|
| Speech-to-Text | faster-whisper 1.2.1 (CTranslate2 4.8.1) |
| Audio decode | ffmpeg subprocess + NumPy (bukan PyAV — diblokir WDAC) |
| Audio capture | ffmpeg dshow (bukan pyaudio — .pyd diblokir WDAC) |
| Python | CPython 3.12.10 (venv `.venv/`) |

**Workaround WDAC** (di-inline di `live_transcribe.py`):
- Fake module `av` di-isi ke `sys.modules` sebelum import faster-whisper.
- `decode_audio` di-monkey-patch ke implementasi ffmpeg di 3 lokasi
  (`faster_whisper`, `faster_whisper.audio`, `faster_whisper.transcribe`).
- Capture mikrofon via `ffmpeg -f dshow` (binary eksternal, lolos WDAC).

---

## ❓ FAQ

### Q: Bisa merekam semua suara peserta Meet?
Ya — dengan VB-CABLE, arahkan Speaker Meet ke "CABLE Input" dan rekam dari
"CABLE Output". Tanpa VB-CABLE, perekaman hanya menangkap suara dari mikrofon
fisik (suaramu saja).

### Q: Kenapa tidak mendengar meeting setelah Speaker Meet diarahkan ke CABLE?
Aktifkan "Listen to this device" di CABLE Output (lihat bagian Meet di atas).
Jangan set playback-nya ke perangkat CABLE (loop).

### Q: Apa bedanya 2 kanal vs 16 kanal (device CABLE)?
Satu kabel virtual yang sama, beda lebar kanal. 2 kanal (tanpa "16 Ch") cukup
untuk percakapan; 16 kanal untuk kebutuhan multitrack profesional. Di Meet
pakai yang tanpa "16 Ch".

### Q: Apakah mesin ini merusak Python 3.12 global?
Tidak. Semua dependency ada di `.venv/` folder ini, dibuat dari
`C:\Program Files\Python312\python.exe` tanpa menyentuh install global.

### Q: Kenapa file `transcribe.py` / `generate_docx.py` tidak ada?
Sengaja dihapus — mesin ini standalone. Semua logika (WDAC workaround,
penomoran folder, generator notulen) sudah di-inline ke `live_transcribe.py`.
Mesin file transkripsi tetap tersedia utuh di `5_mesin_v3/`.

---

## 📝 Lisensi & Kredit

Dibuat untuk keperluan internal **BTD UGM** — Program Magang 2026.
- **Whisper model:** OpenAI (MIT license)
- **faster-whisper:** Guillaume Klein, Systran (MIT license)
- **CTranslate2:** OpenNMT (MIT license)

---

*Dokumentasi terakhir diperbarui: Agustus 2026*
