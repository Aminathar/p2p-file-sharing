# P2P File Sharing

A peer-to-peer file sharing app for your local network. Two computers on the same
WiFi can discover each other and transfer files directly — no cloud, no upload to
a third-party server, no account. Includes a built-in mobile uploader: phones on
the same network can drop files into the app through their browser.

Built with Python + PyQt6. Targets Windows. Trilingual UI (English / Русский /
Қазақша).

## Features

- **Direct LAN transfer.** UDP broadcast discovery + TCP file transfer.
- **Resume support.** Partial files survive disconnects; transfers pick up where
  they left off and verify with MD5.
- **Per-chunk CRC32 + per-file MD5** for integrity (hashes computed by hand-written
  x86-64 assembly DLLs — see `crc32.asm` / `md5.asm`).
- **Mobile uploader.** Built-in HTTP server at `http://<pc-ip>:8000` so phones on
  the same WiFi can authorize with a 6-digit code and upload/download files.
- **Pause / resume / cancel** on both sides.
- **Folder sending** (auto-zipped) and **optional compression**.
- **Dark / light theme.**
- **System tray** so the app keeps running on close.

## Requirements

- Windows 10 or 11
- Python 3.10+ (only if running from source)
- The two computers must be on the **same local network**, and Windows Firewall
  must allow the app — see [Firewall setup](#firewall-setup) below

## Install

### Option 1: pre-built executable (easiest)

Grab the latest release from the [Releases](../../releases) page and run the
installer. The app installs to `Program Files` and adds a Start Menu shortcut.

### Option 2: from source

```powershell
git clone https://github.com/<your-username>/p2p-file-sharing.git
cd p2p-file-sharing
pip install -r requirements.txt
python main.py
```

The included `crc32.dll` and `libmd5.dll` are pre-built. If you want to rebuild
them from the `.asm` sources you'll need [NASM](https://www.nasm.us/) and `gcc`:

```powershell
.\build.bat
```

## Firewall setup

Windows Firewall blocks UDP broadcast discovery by default. The repo includes a
PowerShell script that adds the right rules:

```powershell
# Run as Administrator
.\fix_firewall.ps1
```

Without this, the app may run fine but other PCs won't see yours in the device
list. If you're on a "Public" network profile, also switch it to "Private" in
Windows network settings — broadcast traffic is blocked on Public networks.

## Usage

1. Run the app on **both** computers.
2. The **Receive** tab on the destination PC starts listening automatically.
3. On the source PC, switch to the **Send** tab and click **Search Receivers**.
4. Pick the other PC from the list, click **Connect**, then **Send Files**.
5. Accept the connection prompt on the receiving PC (or check "Auto-accept all").

### Sending from a phone

1. Start the mobile server (Mobile tab → Start).
2. On your phone's browser, open the URL shown (e.g. `http://192.168.1.42:8000`).
3. Enter the 6-digit code displayed on the PC.
4. Upload files or download what the PC is sharing.

## Known limitations

- **LAN only.** Discovery uses UDP broadcast, which doesn't cross routers or the
  internet. For internet-scale sending, the right add-on is something like
  [magic-wormhole](https://magic-wormhole.readthedocs.io/).
- **No encryption.** Designed for trusted local networks. Don't use over open WiFi.
- **Windows only.** Uses Windows-specific DLLs and `SIO_KEEPALIVE_VALS`.
- **Max 50 files per transfer batch.**

## Technical details

See [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) for the wire
protocol, chunking strategy, custom DLL design, and timeouts.

## License

[MIT](LICENSE) — Amin Athar
