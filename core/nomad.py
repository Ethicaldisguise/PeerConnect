from core import *
from logs import *
from webpage import handle
from core import filemanager


class Nomad:
    currently_in_connection = {}
    LOOP_FLAG = True

    def __init__(self, ip='localhost', port=8088):
        with const.PRINT_LOCK:
            time.sleep(const.anim_delay)
            print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safe_stop = True
        const.REMOTE_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.REQ_PORT, status=1)
        self.peer_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.peer_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peer_sock.bind(self.address)

    def commence(self):
        with const.PRINT_LOCK:
            time.sleep(const.anim_delay)
            print("::Listening for connections at ", self.address)
        self.peer_sock.listen()
        const.PAGE_HANDLE_CALL.wait()
        while self.safe_stop:
            if not isinstance(self.peer_sock, socket.socket):
                continue
            readable, _, _ = select.select([self.peer_sock], [], [], 0.001)
            if self.peer_sock not in readable:
                continue
            try:
                initiate_conn, _ = self.peer_sock.accept()
                activity_log(f'New connection from {_[0]}:{_[1]}')
                with const.PRINT_LOCK:
                    print(f"New connection from {_[0]}:{_[1]}")
                Nomad.currently_in_connection[initiate_conn] = True
                use.start_thread(connectNew, args=(initiate_conn,))
            except (socket.error, OSError) as e:
                error_log(f"Socket error: {e}")

        return

    def end(self):
        self.safe_stop = False
        if Nomad:
            Nomad.currently_in_connection = dict.fromkeys(Nomad.currently_in_connection, False)
        self.peer_sock.close() if self.peer_sock else None
        with const.PRINT_LOCK:
            time.sleep(const.anim_delay)
            print("::Nomad Object Ended")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        try:
            self.end()
        except Exception as exp:
            return exp


def send(_to_user_soc:remote_peer.RemotePeer, _data: str):

    for _ in range(const.MAX_CALL_BACKS):

        try:
            send_ip = _to_user_soc.req_uri
            sender_soc = socket.socket(const.IP_VERSION, const.PROTOCOL)
            sender_soc.connect(send_ip)
            status = PeerText(sender_soc, _data).send()
            return status
        except socket.error as err:
            time.sleep(3)
            if err.errno == 10054:
                return False
            error_log(f"Error in sending data: {err}")
            with const.PRINT_LOCK:
                print(f"Error in sending data retrying... {err}")
            continue

    return False


def connectNew(_conn: socket.socket):
    while Nomad.currently_in_connection[_conn]:
        readable, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readable:
            continue
        connectNew_data = PeerText(_conn)
        connectNew_data.receive()
        with const.PRINT_LOCK:
            print('data from peer :', connectNew_data)
        if connectNew_data.compare(const.CMD_CLOSING_HEADER):
            disconnect_user(_conn)
            return True
        elif connectNew_data.compare(const.CMD_RECV_FILE):
            asyncio.run(handle.feed_user_data(connectNew_data, _conn.getpeername()[0]))
            threading.Thread(target=filemanager.file_reciever,args=(_conn,)).start()
        elif connectNew_data.raw_text:
            asyncio.run(handle.feed_user_data(connectNew_data, _conn.getpeername()[0]))

    return True


def disconnect_user(_conn):
    _conn.close()
    print("::Closing connection from disconnect_user() from core/nomad at line 153")
