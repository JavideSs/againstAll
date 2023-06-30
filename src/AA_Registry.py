'''
args: <sock_port> <api_port>
python AA_Registry.py 2222 2220

- WITH SOCKETS:
client.send_msg("Create"|"Update"|"Delete")
client.send_obj(("user","password"))
if Update:
    client.send_obj(("newuser","newpassword"))
client.recv_msg() -> MSGOPRE

- WITH APIREST:
POST <- body{"alias":alias, "password":password} -> MSGOPRE
PATCH <- body{"alias":alias, "password":password, "newalias":newalias, "newpassword":newpassword} -> MSGOPRE
DELETE <- body{"alias":alias, "password":password} -> MSGOPRE
'''

from common_utils import *

import sys, threading
from dataclasses import dataclass

import socket
import flask

import sqlite3

#==================================================

ADDR_SOCK = ("", int(sys.argv[1]))
ADDR_API = ("0.0.0.0", int(sys.argv[2]))

FDATA_DB = "../data/db.db"
FDATA_LOG = "../data/registry.log"
FKEYS_SSL = ("../keys/cert.pem", "../keys/key.pem")

MSGOP_CREATED = "Usuario creado"
MSGOP_UPDATED = "Usuario actualizado"
MSGOP_DELETED = "Usuario eliminado"
MSGERROP_ALREADY_EXISTS = "Error. El usuario ya existe"
MSGERROP_NOT_EXISTS = "Error. La cuenta no coincide con ninguna registrada"
MSGERROP_ERROR = "Error. Operacion no permitida"

#==================================================

@dataclass
class User:
    alias: str
    password: str | tuple[str,str]


def create_db_ifnotexists():
    rundb(FDATA_DB,
        """
        CREATE TABLE IF NOT EXISTS users(
            alias VARCHAR[50] PRIMARY KEY,
            password TEXT NOT NULL
        )
        """
    )

def select_user_db(alias):
    res = rundb(FDATA_DB,
        """
        SELECT alias, password
        FROM users
        WHERE alias = ?
        """
        ,(alias,)
    )
    user = res.fetchone()
    return None if user is None else User(user[0], json.loads(user[1]))

def create_user_db(user):
    if select_user_db(user.alias) is not None:
        return False

    rundb(FDATA_DB,
        """
        INSERT INTO users
        VALUES (?, ?)
        """
        ,(user.alias, json.dumps(hashpasswd(user.password)))
    )
    return True

def update_user_db(alias, user):
    if select_user_db(alias) is None:
        return False
    rundb(FDATA_DB,
        """
        UPDATE users
        SET alias = ?, password = ?
        WHERE alias = ?
        """
        ,(user.alias, json.dumps(hashpasswd(user.password)), alias)
    )
    return True

def delete_user_db(alias):
    if select_user_db(alias) is None:
        return False

    rundb(FDATA_DB,
        """
        DELETE
        FROM users
        WHERE alias = ?
        """
        ,(alias,)
    )
    return True

def user_correct_login_db(user):
    user_fetch = select_user_db(user.alias)
    if user_fetch is None:
        return False
    salt, hash = user_fetch.password
    return hash == hashpasswd(user.password, salt)[1]

#==================================================

def registry(direc, op, user, newuser=None):
    logging.info(str(direc) + " Solicita " + op + " sobre " + str(user))

    if op == "Create":
        iscreated = create_user_db(user)
        if iscreated:
            logging.info(str(user) + " se ha creado")
        return MSGOP_CREATED if iscreated else MSGERROP_ALREADY_EXISTS

    elif op == "Update":
        if user_correct_login_db(user):
            if newuser != user:
                isupdated = update_user_db(user.alias, newuser)
                if isupdated:
                    logging.info(str(user) + " se ha actualizado a " + str(newuser))
                return MSGOP_UPDATED if isupdated else MSGERROP_ALREADY_EXISTS
            else:
                return MSGERROP_ALREADY_EXISTS
        else:
            return MSGERROP_NOT_EXISTS

    elif op == "Delete":
        if user_correct_login_db(user):
            isdeleted = delete_user_db(user.alias)
            if isdeleted:
                logging.info(str(user) + " se ha eliminado")
            return MSGOP_DELETED if isdeleted else MSGERROP_NOT_EXISTS
        else:
            return MSGERROP_NOT_EXISTS

    else:
        return MSGERROP_ERROR

#==================================================

def with_sockets():
    with MySecureSocket("TCP", ADDR_SOCK) as server:
        while True:
            conn, direc = server.accept(cert=FKEYS_SSL)

            op = server.recv_msg()
            user = User(*server.recv_obj())
            newuser = User(*server.recv_obj()) if op == "Update" else None
            res = registry(direc, op, user, newuser)

            server.send_msg(res)
            conn.close()


def with_apirest():
    def rule():
        direc = MyFlask.APIREST.getAddr()
        method = flask.request.method
        body = flask.request.json

        if method == "POST": op = "Create"
        elif method == "PATCH": op = "Update"
        elif method == "DELETE": op = "Delete"
        user = User(body["alias"], body["password"])
        newuser = User(body["newalias"], body["newpassword"]) if op == "Update" else None
        res = registry(direc, op, user, newuser)

        return res

    with MyFlask.APIREST(name="registry", addr=ADDR_API, ssl_context=FKEYS_SSL) as server:
        server.add_url_rule("/", methods=["POST", "PATCH", "DELETE"], view_func=lambda: rule())

#==================================================

create_db_ifnotexists()

logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    handlers=(logging.FileHandler(FDATA_LOG), logging.StreamHandler(sys.stdout)))

threading.Thread(target=with_apirest, daemon=True).start()
with_sockets()