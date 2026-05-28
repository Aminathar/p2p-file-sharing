# P2P File Sharing Application - Technical Documentation

## Overview

This is a peer-to-peer (P2P) file sharing application built with Python and PyQt6. It allows direct file transfers between computers on the same local network without requiring a central server.

---

## Core Components

### 1. Application Architecture

**Files:**

- `main.py` - Entry point that launches the application
- `main_window.py` - PyQt6 GUI implementation
- `core.py` - Network protocol and file transfer logic
- `crc32.dll` - Custom assembly DLL for CRC32 checksum calculation
- `libmd5.dll` - Custom assembly DLL for MD5 hash calculation

**Design Pattern:**

- **Dual Mode**: Each instance can act as both sender and receiver simultaneously
- **Event-Driven**: Uses PyQt6 signals/slots for UI updates
- **Threaded**: Network operations run in background threads to prevent UI freezing

---

## Network Protocol

### Discovery Mechanism

**Broadcast Discovery:**

- Uses UDP broadcast on port `50000`
- Sender broadcasts `"DISCOVER_P2P"` message
- Receivers respond with `"P2P_RESPONSE:<port>"` containing their listening port
- Discovery timeout: **5 seconds**

**Auto-Refresh:**

- Runs every **4 seconds** when enabled
- Only updates list if no active sender connection exists

### Connection Establishment

**Handshake Protocol:**

1. Sender connects via TCP to receiver's port
2. Sender sends: `"P2P_CONNECT_REQUEST:<sender_name>"`
3. Receiver prompts user for approval (or auto-accepts if enabled)
4. Receiver responds: `"P2P_ACCEPT"` or `"P2P_DENY"`

**Connection Persistence:**

- Connections remain open after transfers complete
- Allows multiple transfers without reconnecting
- Cancel/Stop operations preserve the connection

**Timeouts:**

- Initial connection: **10 seconds**
- Handshake response: **30 seconds**
- Transfer approval: **30 seconds**
- Data chunk acknowledgment: **15 seconds**
- Idle socket check: **1 second** (using `select.select`)

---

## File Transfer Protocol

### Transfer Limits

**Maximum Files Per Transfer:** `50` files

- Defined by `MAX_FILES_PER_TRANSFER` constant
- Prevents memory overflow and excessive processing time

**Chunk Size:** `4096 bytes` (4 KB)

- Defined by `CHUNK_SIZE` constant
- Optimal balance between throughput and responsiveness
- Each chunk includes 4-byte CRC32 checksum

### Transfer Flow

**Sender Side:**

1. **Compression** (if enabled):

   - Multiple files → Creates ZIP archive
   - Single file → Creates ZIP with single file
   - Archive stored in temp directory with timestamp

2. **Metadata Transmission:**

   - Format: `"<filename><SEPARATOR><filesize><SEPARATOR><md5>"`
   - Separator: `"<SEPARATOR>"` string literal
   - Receiver validates and responds with offset

3. **Resume Support:**

   - Receiver sends: `"OFFSET:<bytes>"` or `"OFFSET:FULL"`
   - `OFFSET:0` = Start from beginning
   - `OFFSET:FULL` = File already complete, skip
   - Sender seeks to offset before transmitting

4. **Chunk Transmission:**

   - Format: `CMD_DATA (1 byte) + data (4096 bytes) + CRC32 (4 bytes)`
   - Total: 4101 bytes per chunk
   - Receiver validates CRC32 and responds

5. **Chunk Acknowledgment:**
   - `"OK"` = Chunk accepted, continue
   - `"RETRY"` = CRC mismatch, resend chunk
   - `"STOP_"` = Receiver cancelled, abort transfer
   - Max retries per chunk: **2 attempts**

**Receiver Side:**

1. Receives metadata and checks for existing partial file
2. Calculates MD5 of partial file to verify integrity
3. Sends offset to resume or 0 to restart
4. Receives chunks and validates CRC32
5. Writes data to disk incrementally
6. Verifies final MD5 hash matches sender's

### Pause/Resume Mechanism

**Sender Pause:**

- Sets `self.paused = True`
- Sends `CMD_KEEPALIVE` (1 byte: `'K'`) every 1 second
- Does not send data chunks while paused

**Receiver Pause:**

- Sets `self.paused = True`
- Stops reading from socket
- TCP backpressure naturally pauses sender's transmission

**Cancel Behavior:**

- Sets `self.cancelled = True`
- Sender sends `CMD_ABORT` (1 byte: `'A'`)
- Connection remains open for retry
- File statuses reset to "Pending" in UI

---

## Custom DLL Implementation

### CRC32.dll - Cyclic Redundancy Check

**Purpose:**

- **Data Integrity Verification** during chunk transmission
- Detects corruption in individual 4KB chunks
- Fast computation using lookup table algorithm

**Algorithm:**

- Uses ISO 3309 polynomial: `0xEDB88320`
- Matches Python's `zlib.crc32()` implementation
- 256-entry lookup table for performance

**Usage in Application:**

```python
crc = compute_crc32(data)
chunk_packet = CMD_DATA + data + crc.to_bytes(4, 'big')
```

**Why Custom DLL?**

- **Performance**: 2-3x faster than pure Python
- **Learning**: Demonstrates low-level systems programming
- **Control**: Exact implementation matching protocol needs

**Fallback:**

- If DLL fails to load, application shows error
- No fallback to Python `zlib` (strict mode)

---

### libmd5.dll - Message Digest 5

**Purpose:**

- **File Integrity Verification** for complete files
- Ensures entire file transferred correctly
- Detects any corruption across full transfer

**Algorithm:**

- Standard MD5 hash (RFC 1321)
- Processes data in 64-byte blocks
- Produces 128-bit (16-byte) hash

**Usage in Application:**

```python
file_hash = compute_md5(filepath)
```

**Why Both CRC32 and MD5?**

- **CRC32**: Fast, per-chunk validation (real-time error detection)
- **MD5**: Comprehensive, per-file validation (final verification)
- **Layered Security**: Catches errors at multiple stages

**Resume Support:**

- When resuming, receiver computes MD5 of partial file
- Compares with expected hash up to current offset
- Ensures partial file is valid before continuing

---

## Protocol Commands

**1-Byte Command Codes:**

- `CMD_DATA = b'D'` - Data chunk follows
- `CMD_PAUSE = b'P'` - Sender paused (unused, handled via keepalive)
- `CMD_RESUME = b'R'` - Sender resumed (unused)
- `CMD_ABORT = b'A'` - Transfer aborted by sender
- `CMD_KEEPALIVE = b'K'` - Keep connection alive during pause

**Response Codes:**

- `"OK"` - Chunk received successfully
- `"RETRY"` - Chunk failed CRC check, resend
- `"STOP_"` - Receiver cancelled transfer
- `"OFFSET:<n>"` - Resume from byte position n
- `"OFFSET:FULL"` - File already complete
- `"TRANSFER_APPROVED"` - User approved transfer
- `"TRANSFER_DENIED"` - User denied transfer

---

## Error Handling

### Connection Errors

- **Socket Invalid**: Checks using `select.select()` before operations
- **Timeout**: Raises exception after configured timeout
- **Disconnect**: Preserves connection on soft cancel, closes on hard error

### Transfer Errors

- **CRC Mismatch**: Retries chunk up to 2 times
- **MD5 Mismatch**: Deletes corrupted file, user must retry
- **Partial Transfer**: Keeps partial file for resume
- **Disk Full**: Catches `PermissionError`, shows error to user

### Recovery Mechanisms

- **Resume**: Automatically resumes interrupted transfers
- **Retry**: User can click "Send" again to retry failed files
- **Persistent Connection**: Connection survives cancel operations

---

## Performance Optimizations

### Threading Strategy

- **Discovery**: Separate thread for UDP broadcast
- **Listening**: Dedicated thread for incoming connections
- **Transfers**: Each transfer runs in background thread
- **UI Updates**: Signals/slots ensure thread-safe UI updates

### Memory Management

- **Streaming**: Files read/written in 4KB chunks
- **No Full Load**: Never loads entire file into memory
- **Temp Cleanup**: ZIP archives deleted after transfer in `finally` block

### Network Efficiency

- **TCP Nagle**: Disabled via `TCP_NODELAY` (implicit in PyQt)
- **Buffer Size**: 4096 bytes optimal for local network
- **Select Polling**: 1-second timeout prevents busy-waiting

---

## Security Considerations

### Current Implementation

- **No Encryption**: Data transmitted in plaintext
- **Local Network Only**: Designed for trusted LAN environments
- **User Approval**: Receiver must approve each connection/transfer
- **No Authentication**: No password or key exchange

### Integrity Guarantees

- **CRC32**: Detects transmission errors (not tampering)
- **MD5**: Verifies file completeness (not cryptographic security)
- **Resume Safety**: Validates partial files before continuing

---

## Configuration Constants

```python
CHUNK_SIZE = 4096
BUFFER_SIZE = 4100
MAX_FILES_PER_TRANSFER = 50
BROADCAST_PORT = 50000
SEPARATOR = "<SEPARATOR>"

DISCOVERY_TIMEOUT = 5.0
CONNECTION_TIMEOUT = 10.0
HANDSHAKE_TIMEOUT = 30.0
APPROVAL_TIMEOUT = 30.0
CHUNK_ACK_TIMEOUT = 15.0
SELECT_TIMEOUT = 1.0
AUTO_REFRESH_INTERVAL = 4.0
```

---

## UI Features

### Sender Tab

- File selection with MD5 preview
- Receiver discovery with auto-refresh
- Connection management
- Transfer control (Pause/Resume/Cancel)
- Right-click file removal
- Progress tracking

### Receiver Tab

- Auto-accept option
- Configurable save directory
- Transfer control
- File list with status
- Right-click file removal

---

## Logging

**Location:** `%TEMP%\p2p_app.log`

- No admin privileges required
- Captures all network events
- Includes timestamps and severity levels

---

## Build & Deployment

**PyInstaller:** Bundles Python + PyQt6 + DLLs into single executable

**Inno Setup:** Creates Windows installer with shortcuts and uninstall support

---

## Known Limitations

1. Local network only (no WAN)
2. No encryption
3. One transfer at a time per connection
4. Maximum 50 files per batch
5. No folder support
6. Windows x64 only
