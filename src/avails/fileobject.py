import tqdm
from pathlib import Path

from src.core import *
from src.avails.textobject import PeerText
from src.avails.remotepeer import RemotePeer


class PeerFile:
    def __init__(self, controlflag=threading.Event(), path: str = '', is_dir=False, obj=None,
                 recv_soc: socket.socket = None, chunk_size: int = 1024 * 512,
                 error_ext: str = '.invalid'):
        self.reciever_obj: RemotePeer = obj
        self._lock = threading.Lock()
        self.control_flag: threading.Event = controlflag
        self.chunk_size = chunk_size
        self.is_dir = is_dir
        self.error_extension = error_ext
        self.sock = None
        if path == '':
            self.sock = recv_soc
            self.filename = ''
            self.file_size = 0
            return

        self.path = Path(path).resolve()

        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        if self.path.is_dir():
            raise NotADirectoryError(f"Cannot send a directory: {self.path}")

        if not self.path.is_file():
            raise IsADirectoryError(f"Not a regular file: {self.path}")

        self.filename = self.path.name
        self.file_size = self.path.stat().st_size
        self.raw_size = struct.pack('!Q', self.file_size)

    def send_meta_data(self) -> Union[bool, None]:

        with self._lock:
            self.sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.chunk_size)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.chunk_size)

            try:
                if self.control_flag.is_set():
                    return
                self.sock.connect(self.reciever_obj.uri)
                PeerText(self.sock, (const.CMD_RECV_DIR if self.is_dir else const.CMD_RECV_FILE), byteable=False).send()
                PeerText(self.sock, self.filename).send()
                self.sock.sendall(self.raw_size)
                return PeerText(self.sock, const.CMD_FILESOCKET_HANDSHAKE).send()
            except Exception as e:
                print(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                # error_log(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                return False

    def recv_meta_data(self) -> bool:

        with self._lock:
            try:
                self.filename = PeerText(self.sock).receive().decode(const.FORMAT)
                self.file_size = struct.unpack('!Q', self.sock.recv(8))[0]
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.chunk_size)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.chunk_size)
                return PeerText(self.sock).receive(cmpstring=const.CMD_FILESOCKET_HANDSHAKE)
            except Exception as e:
                print(f'::got {e} at avails\\fileobject.py from self.recv_meta_data() closing connection')
                # error_log(f'::got {e} at core\\__init__.py from self.recv_meta_data() closing connection')
                return False

    def send_file(self):
        """
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self._lock:
            try:
                send_progress = tqdm.tqdm(range(self.file_size), f"::sending {self.filename[:20]} ... ", unit="B"
                                          , unit_scale=True, unit_divisor=1024)
                for data in self.__chunkify__():    # send the file in chunks
                    self.sock.sendall(data)
                    send_progress.update(len(data))
                send_progress.close()
                # activity_log(f'::sent file to {self.sock.getpeername()}')
                print("::file sent: ", self.filename, " to ", self.sock.getpeername())
                return True
            except Exception as e:
                error_log(f'::got {e} at core\\__init__.py from self.send_file() closing connection')
                return False
            finally:
                self.sock.close()

    def recv_file(self):
        """
        Receives the file contents from the sender.

        Returns:
            bool: True if the file was received successfully, False otherwise.
        """
        with self._lock:
            try:
                # received_bytes = 0
                progress = tqdm.tqdm(range(self.file_size), f"::receiving {self.filename[:20]}... ", unit="B",
                                     unit_scale=True,
                                     unit_divisor=1024)
                with open(os.path.join(const.PATH_DOWNLOAD, self.__validatename__(self.filename)), 'wb') as file:
                    while (not self.control_flag.is_set()) and (data := self.sock.recv(self.chunk_size)):
                        file.write(data)
                        progress.update(len(data))
                progress.close()
                print()
                activity_log(f'::received file {self.filename} :: from {self.sock.getpeername()}')
                return True
            except Exception as e:
                error_log(f'::got {e} at avails\\fileobject.py from self.recv_file() closing connection')
                self.sock.close()
                self.__file_error__()
                return False

    def __file_error__(self):
        """
            Handles file errors by renaming the file with an error extension.
        """
        with self._lock:
            os.rename(self.filename, self.filename + self.error_extension)
            self.filename += self.error_extension
        return True

    def __chunkify__(self):
        with open(self.path, 'rb') as file:
            while (not self.control_flag.is_set()) and (chunk := file.read(self.chunk_size)):
                yield chunk

    def __validatename__(self, file_addr: str):
        """
            Ensures a unique filename if a file with the same name already exists.

            Args:
                file addr (str): The original filename.

            Returns:
                str: The validated filename, ensuring uniqueness.
        """
        base, ext = os.path.splitext(file_addr)
        counter = 1
        new_file_name = file_addr
        while os.path.exists(os.path.join(const.PATH_DOWNLOAD, new_file_name)):
            new_file_name = f"{base}({counter}){ext}"
            counter += 1
        self.filename = os.path.basename(new_file_name)
        self.name_length = len(self.filename)
        return new_file_name

    def __len__(self):
        """
            Returns the file size.
        """
        return self.file_size

    def __str__(self):
        """
            Returns the filename.
        """
        return self.filename

    def hold(self):
        self.control_flag.set()


# ++++++++++++++++--------------------------------------------------------------------------------------------------++++++++++++++++


def calculate_buffer_size(file_size):
    # Define the minimum and maximum buffer sizes
    min_buffer_size = 64 * 1024  # 64 KB
    max_buffer_size = 1024 * 1024  # 1 MB

    # Define the minimum and maximum file sizes
    min_file_size = 0  # Smallest file size
    max_file_size = 1024 * 1024 * 1024  # 1 GB (adjust as needed)

    # Calculate the buffer size based on the file size
    if file_size <= min_file_size:
        return min_buffer_size
    elif file_size >= max_file_size:
        return max_buffer_size
    else:
        # Linear scaling between min and max buffer sizes
        buffer_size = min_buffer_size + (max_buffer_size - min_buffer_size) * (file_size - min_file_size) / (
                max_file_size - min_file_size)
        return int(buffer_size)