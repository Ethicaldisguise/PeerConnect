import socket as soc
import signal
import pickle
from collections import deque
import requests
from src.core import *
from src.avails.container import CustomSet
from src.avails.textobject import SimplePeerText
import src.avails.remotepeer as rp
import src.avails.constants as const
import json
import subprocess


IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
PUBLIC_IP = '8.8.8.8'
SERVERPORT = 45000
SERVER_SOCKET = soc.socket(IP_VERSION, PROTOCOL)
print('::starting server')
EXIT = threading.Event()
LIST = CustomSet()
# LIST.add(rp.RemotePeer(username='temp', port=25006, ip='1.1.11.1', status=1))


def get_local_ip1():
    ip = ""
    s = soc.socket(IP_VERSION, PROTOCOL)
    s.settimeout(0.5)
    try:
        s.connect((PUBLIC_IP, 80))
        ip = s.getsockname()[0]
    except soc.error as e:
        print(f"::got {e} trying another way")
        ip = soc.gethostbyname(soc.gethostname())
    finally:
        print(f"Local IP: {ip}")
        s.close()
        return ip


def get_local_ip() -> str:
    if const.IP_VERSION == soc.AF_INET:
        with soc.socket(const.IP_VERSION, soc.SOCK_DGRAM) as config_soc:
            config_soc.settimeout(3)
            try:
                config_soc.connect(('1.1.1.1', 80))
                config_ip, _ = config_soc.getsockname()
            except soc.error as err:
                print("got error at getip() :", err)
                config_ip = soc.gethostbyname(soc.gethostname())
                if const.LINUX or const.DARWIN:
                    config_ip = subprocess.getoutput("hostname -I")
    else:
        config_ip = "::1"
        try:
            response = requests.get('https://api64.ipify.org?format=json')
            if response.status_code == 200:
                data = response.json()
                config_ip = data['ip']
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as err:
            print("got error at getip() :", err)
            config_ip = soc.getaddrinfo(soc.gethostname(), None, const.IP_VERSION)[0][4][0]

    print("Local IP: ", config_ip)
    return config_ip


def givelist(client: soc.socket, userobj: rp.RemotePeer):
    if not isinstance(client, soc.socket):
        raise TypeError('client must be a socket')
    client.send(struct.pack('!Q', len(LIST)))
    for peers in LIST:
        peers.serialize(client)
    LIST.add(userobj)
    print('::sent list to client :', client.getpeername())
    print('::new list :', LIST)
    return


def sendlist(client: soc.socket, ):
    """Another implementation of sending a list not in use currently"""
    _l = struct.pack('!I', len(LIST))
    client.send(_l)
    client.sendall(pickle.dumps(LIST))


def validate(client: soc.socket):
    try:
        _newuser = rp.deserialize(client)
        print(':got new user :', _newuser, 'status :', _newuser.status)
        if _newuser.status == 0:
            print('::removing user :', _newuser)
            LIST.discard(_newuser)
            print("new list :", LIST)
            return True
        LIST.discard(_newuser, False)
        SimplePeerText(client, const.SERVER_OK).send()
        threading.Thread(target=givelist, args=(client, _newuser)).start()
        return True
    except soc.error as e:
        print(f'::got {e} closing connection')
        client.close() if client else None
        return False


def getip():

    if IP_VERSION == soc.AF_INET6:
        response = requests.get('https://api64.ipify.org?format=json')
        if response.status_code == 200:
            data = response.json()
            config_ip = data['ip']
            return config_ip, SERVERPORT
    config_ip = get_local_ip()

    return config_ip, SERVERPORT


def sync_users():
    while not EXIT.is_set():
        if len(LIST) == 0:
            time.sleep(5)
            continue
        que = deque(LIST)
        filtered_changes = LIST.getchanges()
        while que:
            peer: rp.RemotePeer = que.popleft()
            active_user_sock = soc.socket(IP_VERSION, PROTOCOL)
            active_user_sock.settimeout(5)
            try:
                active_user_sock.connect(peer.req_uri)
                SimplePeerText(active_user_sock, const.SERVER_PING).send()
            except soc.error as e:
                print(f'::got EXCEPTION {e} closing connection with :', peer)
                peer.status = 0
                LIST.sync_remove(peer)
                continue
            if len(filtered_changes) == 0:
                active_user_sock.send(struct.pack('!Q', 0))
            else:
                give_changes(active_user_sock, filtered_changes)
        time.sleep(5)


def give_changes(active_user_sock: soc.socket, changes: deque):
    # print(f'::give_changes called :{active_user_sock.getpeername()}', changes)
    try:
        with active_user_sock:
            # active_user_sock.send(struct.pack('!Q', len(changes)))
            # for _peer in changes:
            #     _peer.serialize(active_user_sock)
            active_user_sock.send(struct.pack('!Q', 0))
    except soc.error as e:
        print(f'::got {e} for active user :', active_user_sock.getpeername())


def start_server():
    global SERVER_SOCKET, SERVERPORT
    SERVER_SOCKET.setsockopt(soc.SOL_SOCKET, soc.SO_REUSEADDR, 1)
    const.THIS_IP, SERVERPORT = getip()
    SERVER_SOCKET.bind((const.THIS_IP, SERVERPORT))
    SERVER_SOCKET.listen()
    print("Server started at:\n>>", SERVER_SOCKET.getsockname())

    while not EXIT.is_set():
        readable, _, _ = select.select([SERVER_SOCKET], [], [], 0.001)
        if SERVER_SOCKET in readable:
            client, addr = SERVER_SOCKET.accept()
            print("A connection from :", addr)
            validate(client)


def endserver(signum, frame):
    print("\nExiting from server...")
    EXIT.set()
    SERVER_SOCKET.close()
    return


def getlist(lis):
    return


if __name__ == '__main__':
    signal.signal(signal.SIGINT, endserver)
    start_server()
