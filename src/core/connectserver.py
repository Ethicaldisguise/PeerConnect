import queue
import socket

from src.core import *
from src.core import requests_handler
from src.avails.textobject import SimplePeerText
import src.avails.useables as use
import src.avails.remotepeer as remote_peer


End_Safe = threading.Event()
Error_Calls = 0
connection_status = False


def initial_list(no_of_users: int, initiate_socket):
    global End_Safe, Error_Calls
    ping_queue = queue.Queue()
    for _ in range(no_of_users):
        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            while not End_Safe.is_set() and initiate_socket not in readable:
                readable, _, _ = select.select([initiate_socket], [], [], 0.001)
                continue
            _nomad:remote_peer.RemotePeer = remote_peer.deserialize(initiate_socket)
            ping_queue.put(_nomad)
            use.start_thread(_target=requests_handler.signal_active_status, _args=(ping_queue,))
            use.echo_print(False, f"::User received from server : {_nomad}")
        except socket.error as e:
            error_log('::Exception while receiving list of users at connect server.py/initial_list, exp:' + str(e))
            if not e.errno == 10054:
                continue

            end_connection_with_server()
            time.sleep(5)
            if not ping_queue.empty():
                server_log(f"::Server disconnected received some users retrying ...", 4)
                list_error_handler()
            return False
    initiate_socket.close()
    return True


def list_error_handler():
    pass


def get_list_from(initiate_socket: socket.socket):
    const.PAGE_HANDLE_CALL.wait()
    global End_Safe, Error_Calls
    while not End_Safe.is_set():
        readable, _, _ = select.select([initiate_socket], [], [], 0.001)
        if initiate_socket not in readable:
            continue
        raw_length = initiate_socket.recv(8)
        length = struct.unpack('!Q', raw_length)[0]
        return initial_list(length, initiate_socket)


def list_from_forward_control(list_owner:remote_peer.RemotePeer):
    with const.LOCK_PRINT:
        use.echo_print(False, '::Connection redirected by server to : ', list_owner.req_uri)
    list_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
    list_connection_socket.connect(list_owner.req_uri)
    SimplePeerText(list_connection_socket, const.REQ_FOR_LIST, byte_able=False).send()
    use.start_thread(_target=get_list_from, _args=(list_connection_socket,))
    return True if list_connection_socket else False


def initiate_connection():
    global End_Safe, Error_Calls,connection_status
    call_count = 0
    use.echo_print(True, "::Connecting to server")
    while not End_Safe.is_set():
        try:
            server_connection_socket = setup_connection()
            if SimplePeerText(server_connection_socket).receive(cmp_string=const.SERVER_OK):
                server_log('::Connection accepted by server at initiate_connection/connect server.py ', 2)
                use.echo_print(False, '::Connection accepted by server')
                connection_status = True
                use.start_thread(_target=get_list_from, _args=(server_connection_socket,))
            else:
                recv_list_user = remote_peer.deserialize(server_connection_socket)
                return list_from_forward_control(recv_list_user)
            return True
        except (ConnectionRefusedError, TimeoutError, ConnectionError):
            if call_count >= const.MAX_CALL_BACKS:
                use.echo_print(True, "\n::Ending program server refused connection")
                return False
            call_count += 1
            print(f"\r::Connection refused by server, retrying... {call_count}", end='')
            if End_Safe.is_set():
                return False
        except KeyboardInterrupt:
            return False
        except Exception as exp:
            server_log(f'::Connection fatal ... at server.py/initiate_connection, exp : {exp}', 4)
            use.echo_print(False, f"::Connection fatal ... at server.py/initiate_connection, exp : {exp}")
            break
    return False


def setup_connection():
    server_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
    server_connection_socket.settimeout(const.SERVER_TIMEOUT)
    server_connection_socket.connect((const.SERVER_IP, const.PORT_SERVER))
    const.THIS_OBJECT.serialize(server_connection_socket)
    return server_connection_socket


def end_connection_with_server():
    global End_Safe
    End_Safe.set()
    try:
        const.THIS_OBJECT.status = 0
        if connection_status is False:
            return
        with socket.socket(const.IP_VERSION, const.PROTOCOL) as EndSocket:
            EndSocket.connect((const.SERVER_IP, const.PORT_SERVER))
            const.THIS_OBJECT.serialize(EndSocket)
        print("::sent leaving status to server")
        return True
    except Exception as exp:
        server_log(f'::Failed disconnecting from server at {__name__}/{__file__}, exp : {exp}', 4)
        return False
