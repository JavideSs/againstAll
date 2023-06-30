from importlib import import_module

import struct, pickle, logging, json

import ssl, hashlib, secrets


def getaddr(arg):
    return (arg.split(":")[0], int(arg.split(":")[1]))


def toprint_exception(msg, error):
    return msg + " | EXCEPCION: " + type(error).__name__

#==================================================

import sqlite3

def rundb(dbfile, query, parameters=()):
    with sqlite3.connect(dbfile) as db:
        cur = db.cursor()
        res = cur.execute(query, parameters)
        db.commit()
    return res


def exists_table_db(db, tablename):
    return len(rundb(db,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='{}'".format(tablename)
    ).fetchall()) > 0


def hashpasswd(passwd, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hash = hashlib.sha256((passwd+salt).encode()).hexdigest()
    return (salt, hash)

#==================================================

class MyKafka():
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError

    fserializer = lambda v: json.dumps(v).encode("utf-8")
    fdeserializer = lambda v: json.loads(v.decode("utf-8"))

    class Producer(KafkaProducer):
        def __init__(self, addr, *args, **kwargs):
            super().__init__(
                bootstrap_servers = addr,
                key_serializer = MyKafka.fserializer,
                value_serializer = MyKafka.fserializer,
                *args, **kwargs
            )


    class Consumer(KafkaConsumer):
        def __init__(self, addr, topic, group=None, poll_timeout=1000, *args, **kwargs):
            super().__init__(
                topic,
                bootstrap_servers = addr,
                group_id = group,
                key_deserializer = MyKafka.fdeserializer,
                value_deserializer = MyKafka.fdeserializer,
                max_poll_records = 1,
                auto_offset_reset = "latest",
                *args, **kwargs
            )
            '''
            Kafka fun:
            The first received message have an indeterminate timeout
            '''
            self.poll_timeout = poll_timeout
            self.sync()

        def extract_kafka_msg(msg, primitive=True, i=-1):
            if not msg or not primitive:
                return msg

            def dictextractor(listfromdict, i=0):
                return list(listfromdict)[i]

            #There may be multiple messages on one poll()
            return dictextractor(msg.values())[i]

        def poll_msg(self, *args, **kargs):
            return MyKafka.Consumer.extract_kafka_msg(self.poll(*args, **kargs))

        def sync(self):
            self.poll(self.poll_timeout, update_offsets=False)

        def consume_topic(self):
            self.sync()
            self.seek_to_end()

        def consume_tokey_msg(self, stopkey, commit=True):
            while True:
                msg = self.poll_msg(timeout_ms=self.poll_timeout)
                if not msg:
                    return
                if commit:
                    self.commit()

                if msg.key == stopkey:
                    return msg.value

        def last_kafka_msg(self, commit=False):
            msg = {}
            while True:
                newmsg = self.poll_msg(timeout_ms=self.poll_timeout)
                if not newmsg:
                    break
                if commit:
                    self.commit()
                msg = newmsg
            return msg


    class SecureProducer(Producer):
        def __init__(self, addr, *args, **kwargs):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            super().__init__(
                addr = addr,
                security_protocol = "SSL",
                ssl_context = ctx,
                *args, **kwargs
            )


    class SecureConsumer(Consumer):
        def __init__(self, addr, topic, group=None, poll_timeout=1000, *args, **kwargs):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            super().__init__(
                addr = addr,
                topic = topic,
                group = group,
                poll_timeout = poll_timeout,
                security_protocol = "SSL",
                ssl_context = ctx,
                *args, **kwargs
            )

#==================================================

import socket

class MySocket(socket.socket):
    def __init__(self, type, addr):
        super().__init__(socket.AF_INET,
            socket.SOCK_DGRAM if type == "UDP"
            else socket.SOCK_STREAM)

        self.is_server = not len(addr[0])

        if self.is_server:
            self.bind(addr)
            self.listen()
            self.conn = {}
        else:
            self.connect(addr)
            self.conn = {"None":self}

    def accept(self):
        conn, client = super().accept()
        self.conn["None"] = conn
        self.conn[client] = conn
        return conn, client

    def close(self):
        for conn in self.conn.values():
            if conn != self:
                conn.close()
        self.conn, self.client = None, None
        super().close()

    def pack(data):
        packet_len = struct.pack("!I", len(data))
        return packet_len + data

    def send_msg(self, msg, client="None"):
        self.conn[client].sendall(MySocket.pack(msg.encode("utf-8")))

    def send_obj(self, obj, client="None"):
        self.conn[client].sendall(MySocket.pack(pickle.dumps(obj)))

    def recv_confirmed(conn, buf_len):
        buf = b""
        while len(buf) < buf_len:
            buf += conn.recv(buf_len-len(buf))
            if not buf:
                raise socket.error
        return buf

    def recvall(conn):
        buf_len = struct.unpack("!I", MySocket.recv_confirmed(conn,4))[0]
        return MySocket.recv_confirmed(conn, buf_len)

    def recv_msg(self, client="None"):
        return MySocket.recvall(self.conn[client]).decode("utf-8")

    def recv_obj(self, client="None"):
        return pickle.loads(MySocket.recvall(self.conn[client]))


class MySecureSocket(MySocket):
    def sslwrap_client(socket):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx.wrap_socket(socket, server_side=False)

    def sslwrap_server(socket, cert):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*cert)
        return ctx.wrap_socket(socket, server_side=True)

    def __init__(self, type, addr):
        super().__init__(type, addr)

        if not self.is_server:
            conn = MySecureSocket.sslwrap_client(self)
            self.conn = {"None":conn}

    def accept(self, cert):
        conn, client = super(MySocket, self).accept()
        conn = MySecureSocket.sslwrap_server(conn, cert)
        self.conn["None"] = conn
        self.conn[client] = conn
        return conn, client

#==================================================

def requests_disable_warning():
    import requests
    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

class MyFlask():
    mflask = import_module("flask")

    class APIREST():
        def __init__(self, name, addr, *args, **kwargs):
            MyFlask.mflask.cli.show_server_banner = lambda *args: None
            logging.getLogger("werkzeug").disabled = True
            self.name = name
            self.host, self.port = addr
            self.args, self.kwargs = args, kwargs

        def __enter__(self):
            self.app = MyFlask.mflask.Flask(self.name)
            return self.app

        def __exit__(self, *args):
            self.app.run(host=self.host, port=self.port, *self.args, **self.kwargs)

        def getAddr():
            return (
                MyFlask.mflask.request.remote_addr,
                MyFlask.mflask.request.environ.get("REMOTE_PORT")
            )

        def send(msg):
            res = MyFlask.mflask.jsonify(msg)
            res.headers["Access-Control-Allow-Origin"] = "*"
            return res