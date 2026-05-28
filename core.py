import socket
import os
import threading
import struct
import tempfile
import time
import zipfile
import platform
import shutil
from PyQt6.QtCore import QObject, pyqtSignal
import sys
import re
import select
import logging
import ctypes
import hashlib
CRC32_LIB = None
MD5_LIB = None
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRC32_PATH = os.path.join(BASE_DIR, "crc32.dll")
MD5_PATH = os.path.join(BASE_DIR, "libmd5.dll")
CRC32_LOAD_ERROR = "Unknown initialization error"
try:
    if os.path.exists(CRC32_PATH):
        try:
            CRC32_LIB = ctypes.CDLL(CRC32_PATH)
            CRC32_LIB.crc32_compute.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
            CRC32_LIB.crc32_compute.restype = ctypes.c_uint32
            print(f"Loaded crc32.dll from {CRC32_PATH}")
            CRC32_LOAD_ERROR = None
        except Exception as e:
             CRC32_LOAD_ERROR = f"CDLL Load Error: {e}"
             print(f"Failed to load crc32.dll: {e}")
    else:
        CRC32_LOAD_ERROR = f"File not found at {CRC32_PATH}"
        print(f"WARNING: crc32.dll not found at {CRC32_PATH}")
except Exception as e:
    CRC32_LOAD_ERROR = f"Path Resolution Error: {e}"
    print(f"Failed to resolve DLL path: {e}")
CHUNK_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
BUFFER_SIZE = CHUNK_SIZE + 4
MAX_FILES_PER_TRANSFER = 50
BROADCAST_PORT = 50000
DISCOVER_MESSAGE = "DISCOVER_P2P"
RESPONSE_PREFIX = "P2P_RESPONSE"
HANDSHAKE_REQUEST = "P2P_CONNECT_REQUEST"
HANDSHAKE_ACCEPT = "P2P_ACCEPT"
HANDSHAKE_DENY = "P2P_DENY"
CMD_DATA = b'D'
CMD_PAUSE = b'P'
CMD_RESUME = b'R'
CMD_ABORT = b'A'
CMD_KEEPALIVE = b'K'
def get_resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
try:
    if os.path.exists(MD5_PATH):
        MD5_LIB = ctypes.CDLL(MD5_PATH)
        MD5_LIB.MD5_Compress.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        MD5_LIB.MD5_Compress.restype = None
        print(f"Loaded libmd5.dll from {MD5_PATH}")
    else:
        print(f"WARNING: libmd5.dll not found at {MD5_PATH}")
except Exception as e:
    print(f"Failed to load libmd5.dll: {e}")
def compute_md5(file_path):
    """Compute MD5 hash using custom DLL if available, else hashlib."""
    if MD5_LIB:
        try:
            A = 0x67452301
            B = 0xefcdab89
            C = 0x98badcfe
            D = 0x10325476
            state = (ctypes.c_uint32 * 4)(A, B, C, D)
            state_ptr = ctypes.cast(state, ctypes.POINTER(ctypes.c_uint32))
            total_len = 0
            block_buf = bytearray(64)
            buf_len = 0
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    chunk_idx = 0
                    chunk_len = len(chunk)
                    while chunk_idx < chunk_len:
                        needed = 64 - buf_len
                        avail = chunk_len - chunk_idx
                        if avail >= needed:
                            block_buf[buf_len:64] = chunk[chunk_idx:chunk_idx+needed]
                            chunk_idx += needed
                            buf_len = 0
                            c_buf = (ctypes.c_ubyte * 64).from_buffer(block_buf)
                            MD5_LIB.MD5_Compress(state_ptr, ctypes.byref(c_buf))
                            total_len += 64
                        else:
                            block_buf[buf_len:buf_len+avail] = chunk[chunk_idx:chunk_idx+avail]
                            buf_len += avail
                            chunk_idx += avail
            total_real_len = total_len + buf_len
            if buf_len < 64:
                block_buf[buf_len] = 0x80
                buf_len += 1
            else:
                pass
            if buf_len > 56:
                while buf_len < 64:
                    block_buf[buf_len] = 0
                    buf_len += 1
                c_buf = (ctypes.c_ubyte * 64).from_buffer(block_buf)
                MD5_LIB.MD5_Compress(state_ptr, ctypes.byref(c_buf))
                buf_len = 0
            while buf_len < 56:
                block_buf[buf_len] = 0
                buf_len += 1
            bit_len = total_real_len * 8
            struct.pack_into('<Q', block_buf, 56, bit_len)
            c_buf = (ctypes.c_ubyte * 64).from_buffer(block_buf)
            MD5_LIB.MD5_Compress(state_ptr, ctypes.byref(c_buf))
            digest = struct.pack("<IIII", state[0], state[1], state[2], state[3])
            md5_hex = digest.hex()
            print(f"  Computed MD5 (DLL) for {file_path}: {md5_hex}")
            return md5_hex
        except Exception as e:
            raise RuntimeError(f"MD5 DLL Logic Error: {e}. Strict mode: hashlib fallback removed.")
    else:
        raise RuntimeError("MD5 DLL not loaded! Strict mode enabled.")
def compute_crc32(data):
    """Compute CRC32 using DLL if available, FORCE usage if loaded."""
    if CRC32_LIB:
        return CRC32_LIB.crc32_compute(data, len(data), 0xFFFFFFFF)
    raise RuntimeError(f"CRC32 DLL not loaded! Strict mode enabled. Cause: {CRC32_LOAD_ERROR}")
def sanitize_filename(filename):
    """Replace problematic characters in filename."""
    return re.sub(r'[^\w\-\.\(\)]', '_', filename)
def is_socket_valid(sock):
    """Check if a socket is valid and connected."""
    if sock is None:
        return False
    try:
        sock.getpeername()
        return True
    except (socket.error, ValueError, OSError):
        return False
def recv_n_bytes(sock, n):
    """Helper to receive exactly n bytes."""
    data = b''
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        except socket.timeout:
            raise
        except Exception as e:
            print(f"recv_n_bytes error: {e}")
            return None
    return data
def get_local_ip(target_ip="8.8.8.8"):
    """
    Determine the best local IP address for communicating with a target.
    Uses a dummy socket connection to let the OS routing table decide.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_ip, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
             return socket.gethostbyname(socket.gethostname())
        except:
             return "127.0.0.1"


def get_all_local_ips():
    """Return every IPv4 address bound to this host (excluding 127.x).
    Used by the self-broadcast filter so we correctly detect our own packets
    even on machines with multiple network interfaces (Ethernet + WiFi, VPN, etc.).
    """
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                ips.add(ip)
    except Exception:
        pass
    try:
        import netifaces
        for iface in netifaces.interfaces():
            for addr in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                ip = addr.get('addr', '')
                if ip and not ip.startswith('127.'):
                    ips.add(ip)
    except Exception:
        pass
    return ips

def get_broadcast_addresses():
    """
    Get all broadcast addresses for active network interfaces.
    Returns a list of broadcast addresses to use for discovery.
    """
    broadcast_addrs = []
    
    try:
        import netifaces
        # If netifaces is available, use it for accurate broadcast addresses
        for interface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        if 'broadcast' in addr_info:
                            bcast = addr_info['broadcast']
                            if bcast and bcast not in broadcast_addrs:
                                broadcast_addrs.append(bcast)
            except Exception:
                continue
    except ImportError:
        # Fallback: calculate broadcast from local IPs
        try:
            hostname = socket.gethostname()
            # Get all IP addresses for this host
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip.startswith('127.'):
                    continue
                
                # Calculate broadcast address assuming /24 subnet
                # This is a reasonable default for most home/office networks
                parts = ip.split('.')
                if len(parts) == 4:
                    # For common private networks, use /24 broadcast
                    broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    print(f"  Debug: Found Interface IP {ip}, using broadcast {broadcast}")
                    if broadcast not in broadcast_addrs:
                        broadcast_addrs.append(broadcast)
                else:
                    print(f"  Debug: Skipping weird IP {ip}")
        except Exception as e:
            print(f"  Error calculating broadcast addresses: {e}")
    
    # Always include the generic broadcast as fallback
    if '255.255.255.255' not in broadcast_addrs:
        broadcast_addrs.append('255.255.255.255')
    
    print(f"  Detected broadcast addresses: {broadcast_addrs}")
    return broadcast_addrs
class PeerDiscovery:
    """UDP broadcast discovery for local network peers."""
    def __init__(self, broadcast_port=BROADCAST_PORT):
        self.broadcast_port = broadcast_port
        self._running = False
        self._thread = None
        self._sock = None
    def start_receiver_announcement(self, transfer_port):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._announcement_loop, args=(transfer_port,), daemon=True)
        self._thread.start()
    def _announcement_loop(self, transfer_port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                s.bind(("0.0.0.0", self.broadcast_port))
                print(f" Bound announcement socket to (0.0.0.0, {self.broadcast_port})")
            except Exception as e:
                print(f"  Bind 0.0.0.0 failed, trying empty string: {e}")
                s.bind(("", self.broadcast_port))
            self._sock = s
            our_ips = get_all_local_ips()
            while self._running:
                try:
                    data, addr = s.recvfrom(1024)
                    print(f"  Received UDP packet from {addr}")
                    msg = data.decode(errors='ignore')
                    if msg == DISCOVER_MESSAGE:
                        # Self-broadcast filter: refresh the local-IP set each time so we
                        # pick up IPs from interfaces that came up after start (VPN, hotspot).
                        if addr[0] in our_ips:
                            logging.debug(f"Ignoring self-broadcast from {addr[0]}")
                            continue
                        # Cheap refresh — if a new interface appeared, re-check.
                        refreshed = get_all_local_ips()
                        if refreshed != our_ips:
                            our_ips = refreshed
                            if addr[0] in our_ips:
                                logging.debug(f"Ignoring self-broadcast from {addr[0]} (after refresh)")
                                continue

                        # Advertise the IP that's actually reachable FROM the sender, not
                        # the IP that routes to the Internet. Asking the routing table
                        # "how would I reach addr[0]" returns a LAN-local IP on the same
                        # interface as the sender — robust across no-Internet, VPN-up,
                        # and multi-NIC setups.
                        if addr[0] == "127.0.0.1":
                            local_ip = "127.0.0.1"
                        else:
                            local_ip = get_local_ip(addr[0])

                        logging.info(f"Discovery from {addr[0]}. Advertising {local_ip}:{transfer_port}")
                        resp = f"{RESPONSE_PREFIX}:{local_ip}:{transfer_port}"
                        s.sendto(resp.encode(), (addr[0], addr[1]))
                except OSError:
                    break
                except Exception as e:
                    logging.error(f"Announcement loop error: {e}")
                    continue
        except Exception as e:
            logging.error(f"Announcement failed: {e}")
        finally:
            try:
                if self._sock:
                    self._sock.close()
            except Exception:
                pass
    def stop(self):
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
    def discover_peers(self, timeout=5.0):
        found = []
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("  Creating discovery socket")
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(timeout)
            
            # CRITICAL FIX DO NOT CHANGE: Bind to local IP, not empty string
            # On Windows (especially Mobile Hotspot), binding to "" or "0.0.0.0" 
            # prevents broadcasts from being sent properly to other peers.
            # We MUST bind to the specific interface IP.
            local_ip = get_local_ip("8.8.8.8")
            try:
                s.bind((local_ip, 0))
                print(f"  Bound discovery socket to {local_ip}")
            except Exception as e:
                print(f"  Failed to bind to {local_ip}: {e}, trying empty string")
                s.bind(("", 0))
            
            # Get all broadcast addresses for active interfaces
            broadcast_addrs = get_broadcast_addresses()

            def send_all():
                for bcast_addr in broadcast_addrs:
                    try:
                        s.sendto(DISCOVER_MESSAGE.encode(), (bcast_addr, self.broadcast_port))
                    except Exception as e:
                        print(f"  Failed to broadcast to {bcast_addr}: {e}")

            # UDP is lossy; one broadcast often gets dropped on busy WiFi.
            # Re-broadcast every REBROADCAST_INTERVAL seconds for the duration
            # of the discovery window so a dropped packet doesn't mean no peers.
            REBROADCAST_INTERVAL = 0.8
            send_all()
            print(f" Sent discovery broadcasts to {broadcast_addrs}:{self.broadcast_port}")
            next_rebroadcast = time.time() + REBROADCAST_INTERVAL

            start = time.time()
            # Use a short per-recv timeout so we can fire periodic re-broadcasts.
            s.settimeout(0.3)
            while True:
                now = time.time()
                if now - start > timeout:
                    break
                if now >= next_rebroadcast:
                    send_all()
                    next_rebroadcast = now + REBROADCAST_INTERVAL
                try:
                    data, addr = s.recvfrom(1024)
                    msg = data.decode(errors='ignore')
                    if msg.startswith(RESPONSE_PREFIX):
                        parts = msg.split(":")
                        if len(parts) >= 3:
                            _, ip, port = parts[:3]
                            found.append((ip, int(port)))
                            print(f"  Found peer: {ip}:{port}")
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"  Discovery error: {e}")
                    break
        except Exception as e:
            print(f"  Fatal discovery error: {e}")
        finally:
            s.close()
        unique = []
        seen = set()
        for ip, port in found:
            key = f"{ip}:{port}"
            if key not in seen:
                seen.add(key)
                unique.append((ip, port))
        print(f" Discovered {len(unique)} unique peers")
        return unique
class P2PApp(QObject):
    progress_updated = pyqtSignal(int)
    file_progress = pyqtSignal(str, int)
    file_status = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    connection_requested = pyqtSignal(str, object)
    connection_status = pyqtSignal(str)
    incoming_connection = pyqtSignal(str, tuple)
    transfer_ready = pyqtSignal(object)
    transfer_completed = pyqtSignal()
    transfer_permission_requested = pyqtSignal(int, object)
    file_metadata = pyqtSignal(str, int)
    chat_received = pyqtSignal(str, str) # sender, message
    transfer_stats = pyqtSignal(str, str) # speed, eta

    def __init__(self, mode, host='0.0.0.0', port=5000, compress=False, save_dir=None):
        super().__init__()
        self.mode = mode
        self.host = host
        self.port = port
        self.sock = None
        self.compress = compress
        self._stop_event = threading.Event()
        self.save_dir = save_dir
        self.discovery = PeerDiscovery()
        self.connected = False
        self.target_host = None
        self.target_port = None
        self.sender_name = None
        self._pending_client = None
        self.active_socket = None
        self.paused = False
        self.cancelled = False
        self.pending_transfers = {}
    def set_save_dir(self, path):
        self.save_dir = path
        print(f"  Set save directory: {path}")
    def start_announcing(self):
        try:
            self.discovery.start_receiver_announcement(self.port)
            self.connection_status.emit(f"Announcing on LAN (port {self.port})")
            print(f"  Emitted connection_status: Announcing on LAN (port {self.port})")
        except Exception as e:
            self.error_occurred.emit(f"Failed to start announcing: {e}")
    def stop_announcing(self):
        try:
            self.discovery.stop()
            self.connection_status.emit("Stopped announcing presence.")
        except Exception as e:
            self.error_occurred.emit(f"Failed to stop announcing: {e}")
    def discover_peers(self, timeout=5.0):
        return self.discovery.discover_peers(timeout=timeout)
    def connect(self, target_host, target_port, sender_name=None):
        """Initiate connection to a receiver and perform handshake."""
        if self.connected and is_socket_valid(self.sock):
            self.connection_status.emit("Already connected.")
            return
        if sender_name is None:
            try:
                sender_name = platform.node()
            except Exception:
                sender_name = "Sender"
        self.sender_name = sender_name
        self.target_host = target_host
        self.target_port = target_port
        try:
            print(f" Attempting to connect to {target_host}:{target_port}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if platform.system() == "Windows":
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 30000, 5000))
            elif platform.system() == "Linux":
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            self.sock.settimeout(15)
            self.sock.connect((target_host, target_port))
            handshake_msg = f"{HANDSHAKE_REQUEST}:{sender_name}"
            self.sock.sendall(handshake_msg.encode())
            print(f" Handshake sent: {handshake_msg}")
            try:
                resp = self.sock.recv(32).decode(errors='ignore')
                print(f" Handshake response: {resp}")
            except socket.timeout:
                raise Exception("No handshake response (timeout).")
            if resp != HANDSHAKE_ACCEPT:
                self.connection_status.emit("Connection rejected by receiver.")
                raise Exception("Connection rejected by receiver.")
            self.sock.settimeout(None)
            self.connected = True
            self.connection_status.emit(f"Connected to {target_host}:{target_port}")
            print(f" Connection established to {target_host}:{target_port}")
        except Exception as e:
            print(f"  Connect failed: {e}")
            self.disconnect()
            self.error_occurred.emit(str(e))
            self.connection_status.emit(f"Connection failed: {e}")
    def pause_transfer(self):
        self.paused = True
        self.connection_status.emit("Transfer paused.")
        print("  Paused transfer state.")
    def resume_transfer(self):
        self.paused = False
        self.connection_status.emit("Transfer resumed.")
        print("  Resumed transfer state.")
    def stop_transfer(self):
        """Soft cancel: signals abort but keeps connection open if possible."""
        self.cancelled = True
        self.connection_status.emit("Stopping transfer...")
        print("  Stopping transfer (flag set).")
    def cancel_transfer(self):
        """Hard cancel: closes socket (legacy/emergency)."""
        self.stop_transfer()
        if self.active_socket:
             try:
                 self.active_socket.close()
             except Exception:
                 pass
             self.active_socket = None
    def disconnect(self):
        """Close the active connection."""
        self.stop_transfer() # Ensure cancelled flag is set
        if self.active_socket:
            try:
                # Signal abort if possible? 
                # self.active_socket.sendall(CMD_ABORT)
                self.active_socket.close()
            except Exception:
                pass
            self.active_socket = None
            
        if self.sock:
            try:
                self.sock.close()
                print("  Socket closed")
            except Exception as e:
                print(f"  Error closing socket: {e}")
            self.sock = None
        self.connected = False
        self.target_host = None
        self.target_port = None
        self.sender_name = None
        self.connection_status.emit("Disconnected.")
    def send_files(self, target_host=None, target_port=None, filenames=None, sender_name=None, use_existing_socket=True):
        """Send files, using existing socket if available."""
        temp_zip = None
        files_to_send = filenames
        s = None
        try:
            if filenames and len(filenames) > MAX_FILES_PER_TRANSFER:
                raise ValueError(f"Too many files selected. Maximum allowed is {MAX_FILES_PER_TRANSFER}.")
            if use_existing_socket and self.connected and is_socket_valid(self.sock):
                if not self.sock:
                    raise ValueError("No active connection.")
                s = self.sock
                target_host = self.target_host
                target_port = self.target_port
                print(f" Reusing existing connection to {target_host}:{target_port}")
            else:
                if not (target_host and target_port and filenames):
                    raise ValueError("Target host, port, and filenames required for new connection.")
                if sender_name is None:
                    try:
                        sender_name = platform.node()
                    except Exception:
                        sender_name = "Sender"
                self.disconnect()
                self.connect(target_host, target_port, sender_name)
                s = self.sock
                self.connection_status.emit(f"Reconnected to {target_host}:{target_port}")
            if not files_to_send:
                raise ValueError("No files selected to send.")
            original_filenames = filenames if filenames else []
            files_to_send = filenames
            self.zips_to_cleanup = []
            folder_map = {}

            # Pre-process folders: Zip them individually first
            processed_files = []
            for p in filenames:
                if os.path.exists(p) and os.path.isdir(p):
                    try:
                        # Create a unique temp directory for this zip to preserve clean filename
                        td = tempfile.mkdtemp()
                        self.zips_to_cleanup.append(td)
                        
                        folder_name = os.path.basename(p)
                        zip_name = f"{folder_name}.zip"
                        zip_path = os.path.join(td, zip_name)
                        
                        print(f" Zipping folder {p} to {zip_path}")
                        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                            for root, dirs, files in os.walk(p):
                                # Sort dirs and files to ensure deterministic zip content
                                dirs.sort()
                                files.sort()
                                for file in files:
                                    abs_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(abs_path, os.path.dirname(p))
                                    zf.write(abs_path, arcname=rel_path)
                        
                        processed_files.append(zip_path)
                        folder_map[zip_path] = folder_name
                    except Exception as e:
                        print(f" Failed to zip folder {p}: {e}")
                        # Fallback? If we fail to zip, we can't send it. Skip or raise?
                        raise ValueError(f"Failed to process folder {folder_name}: {e}")
                else:
                    processed_files.append(p)
            
            # Update the list used for compression/sending
            # If compression is ON, these zips will be added to the big archive.
            # If compression is OFF, these zips will be sent as individual files.
            files_to_send = processed_files 
            filenames = processed_files # IMPORTANT to update this for next block

            files_to_send_final = files_to_send

            temp_zip = None
            if self.compress and len(files_to_send) > 1:
                # Deterministic Archive Name: Hash of sorted filenames
                files_to_send.sort() # Ensure deterministic order
                
                hasher = hashlib.md5()
                for f in files_to_send:
                     hasher.update(os.path.basename(f).encode())
                digest = hasher.hexdigest()[:8]
                
                tmpdir = tempfile.gettempdir()
                temp_zip = os.path.join(tmpdir, f"archive_{digest}.zip")
                
                # Only recreate if it doesn't strictly exist or we want to force? 
                # Actually, temp dir might be cleaned. Better to just overwrite to be safe and ensure it matches.
                # Deterministic content:
                with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for p in files_to_send:
                        zf.write(p, arcname=os.path.basename(p))
                files_to_send_final = [temp_zip]
            elif self.compress and len(files_to_send) == 1 and not folder_map: 
                # Optimization: Only single-zip standard files if requested. 
                # If it's ALREADY a folder-zip (in folder_map), don't double zip it unless user strongly implies?
                # Actually, existing logic double-zips single files if compress=True.
                # Let's keep consistent: if Compress is checked, we compress whatever is there.
                
                # Deterministic name for single file too
                fname = os.path.basename(files_to_send[0])
                hasher = hashlib.md5()
                hasher.update(fname.encode())
                digest = hasher.hexdigest()[:8]
                
                tmpdir = tempfile.gettempdir()
                temp_zip = os.path.join(tmpdir, f"archive_{digest}.zip")
                
                with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(files_to_send[0], arcname=fname)
                files_to_send_final = [temp_zip]
            
            files_to_send = files_to_send_final
            print(f" Sending number of files: {len(files_to_send)}")
            if not is_socket_valid(s):
                raise Exception("Socket became invalid before sending number of files")
            self.active_socket = s
            s.sendall(str(len(files_to_send)).encode() + b'\n')
            time.sleep(0.1)
            print(" Waiting for transfer approval...")
            s.settimeout(30)
            approval_resp = s.recv(64).decode(errors='ignore').strip()
            print(f"  Received approval response: {approval_resp}")
            if approval_resp == "TRANSFER_DENIED":
                raise Exception("Transfer denied by receiver")
            elif approval_resp != "TRANSFER_APPROVED":
                raise Exception(f"Invalid approval response: {approval_resp}")
            print(" Transfer approved, sending files...")
            total_bytes = sum(os.path.getsize(p) for p in files_to_send)
            sent_overall = 0
            
            # Speed calc
            start_time = time.time()
            last_calc_time = start_time
            bytes_since_last_calc = 0

            s.settimeout(30)
            for p in files_to_send:
                fname = sanitize_filename(os.path.basename(p))
                fsize = os.path.getsize(p)
                md5 = compute_md5(p)
                metadata = f"{fname}{SEPARATOR}{fsize}{SEPARATOR}{md5}"
                print(f" Sending metadata: {metadata}")
                if not is_socket_valid(s):
                    raise Exception("Socket became invalid before sending metadata")
                s.sendall(metadata.encode() + b'\n')
                time.sleep(0.1)
                resp = s.recv(64).decode(errors='ignore')
                print(f"  Received OFFSET response: {resp}")
                offset = 0
                if resp.startswith("OFFSET:"):
                    val = resp.split(":", 1)[1].strip()
                    if val == "FULL":
                        self.file_status.emit(fname, "Already present")
                        sent_overall += fsize
                        self.progress_updated.emit(int(sent_overall / total_bytes * 100))
                        continue
                    try:
                        offset = int(val)
                    except Exception:
                        offset = 0
                if offset > 0:
                    self.file_status.emit(fname, f"Resuming {offset} bytes")
                else:
                    if self.compress and fname.startswith("archive_") and fname.endswith(".zip"):
                        for orig_file in original_filenames:
                            orig_basename = os.path.basename(orig_file)
                            self.file_status.emit(orig_basename, "Sending")
                    else:
                        # Map back to original folder name for UI if possible
                        ui_name = folder_map.get(p, fname)
                        # If p was a zip we created, fname is 'Folder.zip'. folder_map[p] is 'Folder'.
                        # But wait, fname is sanitize_filename(basename(p)). 
                        # If p is .../Folder.zip, basename is Folder.zip.
                        # folder_map is indexed by p (full path).
                        # So this lookup works.
                        # BUT, if we emit 'Folder', and the UI expects 'Folder' (from table), it works.
                        # The receiver gets 'Folder.zip'.
                        self.file_status.emit(ui_name, "Sending")
                with open(p, "rb") as f:
                    f.seek(offset)
                    sent_overall += offset
                    while True:
                        data = f.read(CHUNK_SIZE)
                        if not data:
                            break
                        raw = data
                        
                        # Speed Calc
                        bytes_since_last_calc += len(raw)
                        now = time.time()
                        if now - last_calc_time >= 1.0:
                            speed_bps = bytes_since_last_calc / (now - last_calc_time)
                            speed_mbps = speed_bps / (1024 * 1024)
                            if speed_mbps < 0.1:
                                speed_str = f"{speed_bps/1024:.1f} KB/s"
                            else:
                                speed_str = f"{speed_mbps:.1f} MB/s"
                            
                            remaining_bytes = total_bytes - sent_overall
                            eta_seconds = remaining_bytes / speed_bps if speed_bps > 0 else 0
                            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
                            
                            self.transfer_stats.emit(speed_str, eta_str)
                            
                            last_calc_time = now
                            bytes_since_last_calc = 0
                        
                        crc = compute_crc32(data)
                        while self.paused:
                             if self.cancelled: break
                             s.sendall(CMD_KEEPALIVE)
                             time.sleep(1.0)
                        if self.cancelled:
                             s.sendall(CMD_ABORT)
                             raise Exception("Transfer stopped by sender")
                        if not is_socket_valid(s):
                            raise Exception("Socket became invalid during chunk transfer")
                        
                        # Send command byte + data + CRC
                        s.sendall(CMD_DATA + data + crc.to_bytes(4, 'big'))
                        
                        retries = 2
                        while retries > 0:
                            try:
                                readable, _, _ = select.select([s], [], [], 1.0)
                                if not readable:
                                    retries -= 1
                                    continue
                                resp2 = s.recv(5)
                                if not resp2:
                                    raise Exception("Receiver closed connection - check receiver logs for errors")
                                if resp2.startswith(b'RETRY'):
                                    data = raw
                                    crc = compute_crc32(data)
                                    print(f" Retrying chunk for {fname}, CRC: {hex(crc)}")
                                    s.sendall(CMD_DATA + data + crc.to_bytes(4, 'big'))
                                    continue
                                if resp2.startswith(b'OK'):
                                    break
                                if resp2.startswith(b'STOP_'):
                                    raise Exception("Transfer stopped by receiver")
                                raise Exception(f"Invalid chunk response: {resp2.hex()}")
                            except socket.timeout:
                                print(f"  Timeout receiving chunk response, retries left: {retries}")
                                retries -= 1
                        if retries == 0:
                            raise Exception("Failed to receive valid chunk response after retries")
                        sent_overall += len(raw)
                        pct_file = int((f.tell()) / fsize * 100) if fsize else 100
                        self.file_progress.emit(fname, pct_file)
                        self.progress_updated.emit(int(sent_overall / total_bytes * 100))
                    if self.compress and fname.startswith("archive_") and fname.endswith(".zip"):
                        for orig_file in original_filenames:
                            orig_basename = os.path.basename(orig_file)
                            self.file_status.emit(orig_basename, "Sent")
                    else:
                        self.file_status.emit(fname, "Sent")
                    print(f" Completed sending {fname}")
                s.settimeout(5)
                try:
                    readable, _, _ = select.select([s], [], [], 1.0)
                    if readable:
                        error_data = s.recv(64)
                        if error_data:
                            print(f"  Received error data from receiver after {fname}: {error_data.decode(errors='ignore')}")
                except Exception as e:
                    print(f"  Post-chunk check error for {fname}: {e}")
            s.settimeout(None)
            if not self.connected or not is_socket_valid(s):
                s.close()
                self.disconnect()
            else:
                self.connection_status.emit("Transfer complete.")
                self.progress_updated.emit(100)
                self.transfer_completed.emit()
                print(" Sender socket remains open for next transfer")
        except (ValueError, FileNotFoundError, PermissionError) as e:
            self.error_occurred.emit(str(e))
            print(f" Recoverable send error: {e}")
        except Exception as e:
            msg = str(e)
            if "Transfer stopped" in msg:
                 print(f"  {msg} (Soft Cancel)")
                 self.connection_status.emit("Transfer cancelled.")
                 self.progress_updated.emit(0)
                 return
            if self.active_socket is None and "closed" in msg.lower():
                 msg = "Transfer cancelled by user."
                 self.connection_status.emit(msg)
                 return
            self.error_occurred.emit(msg)
            print(f"  Sender Loop Error: {e}")
            self.connection_status.emit(f"Disconnected (error): {msg}")
            self.disconnect()
        finally:
            self.active_socket = None
            try:
                if temp_zip and os.path.exists(temp_zip):
                    os.remove(temp_zip)
            except Exception:
                pass
            self.paused = False
            self.cancelled = False
            # Clean up folder zips
            if hasattr(self, 'zips_to_cleanup'):
                for td in self.zips_to_cleanup:
                    try:
                        shutil.rmtree(td)
                        print(f" Cleaned up temp dir {td}")
                    except Exception as e:
                        print(f" Failed to cleanup temp dir {td}: {e}")
                self.zips_to_cleanup = []

    def send_chat_message(self, message):
        """Send a chat message to the connected receiver."""
        try:
            # Check connected sender socket OR active receiver socket
            target_socket = self.sock
            if not target_socket or not is_socket_valid(target_socket):
                 target_socket = self.active_socket
            
            if not target_socket or not is_socket_valid(target_socket):
                 raise Exception("Not connected")
                 
            # Check if busy sending files?
            # For simplicity, just try to send. If socket is busy, it might mix with file data 
            # (which is bad) but we assume UI handles disabling send during transfer.
            # Actually, we should check active_socket usage or lock.
            # if self.active_socket and self.active_socket == self.sock:
            #      pass

            msg = f"CHAT:{message}"
            target_socket.sendall(msg.encode())
            print(f" Sent chat message: {message}")
        except Exception as e:
            self.error_occurred.emit(f"Failed to send chat: {e}")

    def start(self):
        if self.mode in ['receive', 'both']:
            self.start_announcing()
            threading.Thread(target=self.receive, daemon=True).start()
            self.connection_status.emit(f"Receiver listening on {self.host}:{self.port}")
        if self.mode in ['send', 'both']:
            self.connection_status.emit("Ready to send.")
    def stop(self):
        self.stop_transfer()
        self._stop_event.set()
        self.disconnect()
        try:
            self.stop_announcing()
        except Exception:
            pass
    def receive(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(5)
            s.settimeout(1.0)
            print(f" Receiver listening on {self.host}:{self.port}")
            while not self._stop_event.is_set():
                try:
                    client, addr = s.accept()
                    client_ip = addr[0]
                    print(f" Incoming connection from {client_ip}")
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.incoming_connection.emit("Unknown", addr)
                    client.settimeout(10.0)
                    retries = 2
                    while retries > 0:
                        try:
                            data = client.recv(BUFFER_SIZE)
                            break
                        except socket.timeout:
                            retries -= 1
                            if retries == 0:
                                client.close()
                                self.connection_status.emit(f"Disconnected from {client_ip}: Handshake timeout")
                                continue
                    if not data:
                        client.close()
                        self.connection_status.emit(f"Disconnected from {client_ip}: Empty data")
                        continue
                    try:
                        msg = data.decode(errors='ignore')
                        print(f" Received: {msg}")
                    except Exception:
                        client.close()
                        self.connection_status.emit(f"Disconnected from {client_ip}: Invalid data")
                        continue
                    if msg.startswith(HANDSHAKE_REQUEST):
                        sender_name = msg.split(":", 1)[1] if ":" in msg else "Unknown"
                        print(f" Requesting connection approval for {sender_name}")
                        logging.debug(f"Received HANDSHAKE_REQUEST from {sender_name} ({client_ip})")
                        self._pending_client = client
                        print(f" Emitting connection_requested signal for {sender_name}")
                        self.connection_requested.emit(sender_name, self)
                    else:
                        client.close()
                        self.connection_status.emit(f"Disconnected from {client_ip}: Unexpected data")
                except socket.timeout:
                    continue
                except Exception as e:
                    try:
                        client.close()
                    except Exception:
                        pass
                    self.error_occurred.emit(str(e))
                    self.connection_status.emit(f"Connection error with {client_ip}: {e}")
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connection_status.emit(f"Receiver error: {e}")
        finally:
            try:
                s.close()
            except Exception:
                pass
    def start_transfer(self, client):
        """Start file transfer on the client socket after handshake. Loop for multiple transfers."""
        try:
            self.active_socket = client # Allow sending chat
            while not self._stop_event.is_set():
                transfer_received = self._receive_transfer(client)
                if not transfer_received:
                    break
                # Only print if we actually did something or if verbose? 
                # The loop returns True on timeout (idle), so printing here spams logs.
                # print(" Receiver ready for next transfer on same connection") 
        except Exception as e:
            self.error_occurred.emit(str(e))
            print(f"  Transfer error: {e}")
        finally:
            self.active_socket = None
            try:
                client.close()
                print(" Client socket closed")
            except Exception:
                pass
    def submit_permission_response(self, client, approved):
        """Called by UI to provide response to transfer request."""
        if client in self.pending_transfers:
            self.pending_transfers[client]['approved'] = approved
            self.pending_transfers[client]['event'].set()
        else:
            print(" Warning: Received permission response for unknown or expired client")
    def _receive_transfer(self, client):
        """Receive files from the sender. Blocks until permission received from UI."""
        try:
            # Use a short timeout to check for data, but don't crash if idle
            # This allows the connection to stay alive for chat or subsequent transfers
            client.settimeout(2.0)
            try:
                # BLOCKING RECV (with 2s timeout)
                initial = client.recv(BUFFER_SIZE).decode(errors='ignore')
            except socket.timeout:
                # Connection is idle (user reading chat?), keep alive!
                return True
            except BlockingIOError:
                return True
            
            # Reset timeout for actual data transfer
            client.settimeout(15.0)
            if not initial:
                print(" Connection closed by sender (graceful)")
                return False
            
            # Check for Chat Message
            if initial.startswith("CHAT:"):
                try:
                    msg_content = initial.split(":", 1)[1]
                    # We don't have the sender name easily here unless we saved it from handshake
                    sender_name = "Peer" 
                    self.chat_received.emit(sender_name, msg_content)
                    print(f"  Received chat: {msg_content}")
                    return True # Keep loop logic alive
                except Exception as e:
                    print(f" Error parsing chat: {e}")
                    return True

            try:
                num_files = int(initial.strip())
                print(f"  Receiving {num_files} files")
            except ValueError:
                # Could be a partial read or garbage?
                print(f"  Invalid header received: {initial[:20]}...")
                return False # Break connection on protocol error
            client.settimeout(None)
            evt = threading.Event()
            self.pending_transfers[client] = {'event': evt, 'approved': False}
            print(f"  Requesting permission to receive {num_files} file(s)")
            self.transfer_permission_requested.emit(num_files, client)
            print("  Waiting for user permission...")
            evt.wait()
            if client not in self.pending_transfers:
                return False
            approved = self.pending_transfers[client]['approved']
            del self.pending_transfers[client]
            return self._receive_files(client, num_files, approved)
        except Exception as e:
            if "Transfer stopped" in str(e):
                 print(f"  {e} (Soft Cancel)")
                 self.connection_status.emit("Transfer cancelled.")
                 return True
            self.error_occurred.emit(str(e))
            print(f"  Transfer error: {e}")
            return False
    def _receive_files(self, client, num_files, approved):
        """Receive the actual files after permission."""
        try:
            client.settimeout(30)
            client.setblocking(True)
            self.active_socket = client
            if not approved:
                print(" Transfer denied by user")
                client.sendall(b"TRANSFER_DENIED\n")
                self.connection_status.emit("Transfer denied")
                return True
            print(f" Transfer approved, receiving {num_files} files")
            client.sendall(b"TRANSFER_APPROVED\n")
            for _ in range(num_files):
                retries = 2
                while retries > 0:
                    try:
                        meta = client.recv(BUFFER_SIZE).decode(errors='ignore')
                        break
                    except socket.timeout:
                        retries -= 1
                        print(f"  Retrying metadata recv, retries left: {retries}")
                        if retries == 0:
                            raise Exception("Timeout receiving metadata")
                if not meta:
                    raise Exception("Connection closed by sender during metadata")
                print(f"  Received metadata: {meta}")
                try:
                    filename, filesize, md5 = meta.split(SEPARATOR)
                    filesize = int(filesize)
                    md5 = md5.strip().lower()
                except ValueError:
                    raise Exception(f"Invalid metadata format: {meta}")
                if self.save_dir:
                    os.makedirs(self.save_dir, exist_ok=True)
                    receiving_path = os.path.join(self.save_dir, filename)
                else:
                    receiving_path = filename
                self.file_metadata.emit(filename, filesize)
                print(f"  Writing to: {receiving_path}")
                existing = 0
                if os.path.exists(receiving_path):
                    existing = os.path.getsize(receiving_path)
                    if existing >= filesize:
                        client.sendall(b"OFFSET:FULL\n")
                        self.file_status.emit(filename, "Already present")
                        continue
                client.sendall(f"OFFSET:{existing}\n".encode())
                bytes_received = existing
                self.file_status.emit(filename, "Receiving")
                
                # Receiver Speed Calc
                start_time = time.time()
                last_calc_time = start_time
                bytes_since_last_calc = 0
                
                with open(receiving_path, "ab") as f:
                    chunk_retry_count = 0
                    max_retries = 3
                    while bytes_received < filesize:
                        if self.paused:
                            time.sleep(0.2)
                            continue
                        
                        # ... select ...
                        
                        # (Assume read/write happens here)
                        
                        # Inject calc logic here after write? No, this is replacing the whole logic?
                        # The replace block is too big/complex to do inline safely without context.
                        # I will target the inner loop start

                        client.settimeout(15.0)
                        readable, _, _ = select.select([client], [], [], 1.0)
                        if not readable:
                            if self.cancelled:
                                 client.sendall(b'STOP_')
                                 raise Exception("Transfer stopped by receiver")
                            continue
                        bytes_remaining = filesize - bytes_received
                        next_chunk_size = min(bytes_remaining, CHUNK_SIZE)
                        packet_size = 1 + next_chunk_size + 4
                        cmd = recv_n_bytes(client, 1)
                        if not cmd:
                             raise Exception("Connection closed waiting for command")
                        if cmd == CMD_ABORT:
                             raise Exception("Transfer aborted by sender")
                        elif cmd == CMD_KEEPALIVE or cmd == CMD_PAUSE:
                             print("  Sender paused/keepalive...")
                             continue
                        elif cmd != CMD_DATA:
                             print(f"  Unknown command: {cmd}")
                             raise Exception(f"Protocol error: Unexpected command {cmd}")
                        rest_len = next_chunk_size + 4
                        chunk = recv_n_bytes(client, rest_len)
                        if not chunk:
                             raise Exception("Connection closed during data body")
                        encrypted_data = chunk[:-4]
                        rec_crc = int.from_bytes(chunk[-4:], 'big')
                        if self.cancelled:
                             client.sendall(b'STOP_')
                             raise Exception("Transfer stopped by receiver")
                        if compute_crc32(encrypted_data) != rec_crc:
                            chunk_retry_count += 1
                            if chunk_retry_count >= max_retries:
                                raise Exception(f"CRC failed after {max_retries} retries")
                            client.sendall(b"RETRY")
                            print(f" Sent RETRY for chunk - CRC mismatch (retry {chunk_retry_count}/{max_retries})")
                            continue
                        chunk_retry_count = 0
                        client.sendall(b"OK")
                        data = encrypted_data
                        f.write(data)
                        f.flush()
                        bytes_received += len(data)

                        # Speed Calc (Receiver)
                        bytes_since_last_calc += len(data)
                        now = time.time()
                        if now - last_calc_time >= 1.0:
                            speed_bps = bytes_since_last_calc / (now - last_calc_time)
                            speed_mbps = speed_bps / (1024 * 1024)
                            if speed_mbps < 0.1:
                                speed_str = f"{speed_bps/1024:.1f} KB/s"
                            else:
                                speed_str = f"{speed_mbps:.1f} MB/s"
                            
                            remaining_bytes = filesize - bytes_received
                            eta_seconds = remaining_bytes / speed_bps if speed_bps > 0 else 0
                            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
                            
                            self.transfer_stats.emit(speed_str, eta_str)
                            
                            last_calc_time = now
                            bytes_since_last_calc = 0

                        if bytes_received >= filesize:
                            print(f"  Completed! Received {bytes_received}/{filesize} bytes")
                            self.file_progress.emit(filename, 100)
                            self.progress_updated.emit(100)
                            self.file_status.emit(filename, "Received")
                            break
                        pct = int(bytes_received / filesize * 100)
                        self.file_progress.emit(filename, pct)
                        self.progress_updated.emit(pct)
                print(f"  Exited chunk receive loop for {filename}")
            return True
        except Exception as e:
            if "Transfer stopped" in str(e):
                 print(f"  {e} (Soft Cancel)")
                 self.connection_status.emit("Transfer cancelled.")
                 self.progress_updated.emit(0)
                 return True
            if self.active_socket is None:
                 print("  Transfer loop exited due to cancellation")
            else:
                 self.error_occurred.emit(str(e))
                 print(f"  Transfer error: {e}")
            return False
        finally:
            self.active_socket = None
            self.paused = False
            self.cancelled = False