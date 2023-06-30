import struct, pickle, json


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

#==================================================

class MyKafka():
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError

    fserializer = lambda v: json.dumps(v).encode("utf-8")
    fdeserializer = lambda v: json.loads(v.decode("utf-8"))

    class Producer(KafkaProducer):
        def __init__(self, addr):
            super().__init__(
                bootstrap_servers = addr,
                key_serializer = MyKafka.fserializer,
                value_serializer = MyKafka.fserializer,
            )

    class Consumer(KafkaConsumer):
        def __init__(self, addr, topic, poll_timeout=1000, group=None):
            super().__init__(
                topic,
                bootstrap_servers = addr,
                group_id = group,
                key_deserializer = MyKafka.fdeserializer,
                value_deserializer = MyKafka.fdeserializer,
                max_poll_records = 1,
                auto_offset_reset = "latest",
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