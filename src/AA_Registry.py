'''
args: <port>
python AA_Registry.py 2222

client.send_msg("Create"|"Update"|"Delete")
client.send_obj(("user","password"))
if Update:
    client.send_obj(("newuser","newpassword"))
client.recv_msg() -> MSGOPRE
'''

from common_utils import *

import sys
from dataclasses import dataclass

import socket

import sqlite3

#==================================================

ADDR = ("", int(sys.argv[1]))

FDATA_DB = "../data/db.db"

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
    password: str


def create_db_ifnotexists():
    rundb(FDATA_DB,
        """
        CREATE TABLE IF NOT EXISTS users(
            alias VARCHAR[50] PRIMARY KEY,
            password VARCHAR[50] NOT NULL
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
    return None if user is None else User(*user)

def create_user_db(user):
    if select_user_db(user.alias) is not None:
        return False

    rundb(FDATA_DB,
        """
        INSERT INTO users
        VALUES (?, ?)
        """
        ,(user.alias, user.password)
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
        ,(user.alias, user.password, alias)
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
    return user_fetch is not None and user_fetch.password == user.password

#==================================================

with MySocket("TCP", ADDR) as server:
    create_db_ifnotexists()

    while True:
        conn, direc = server.accept()
        op = server.recv_msg()
        user = User(*server.recv_obj())
        print(direc, "Solicita", op, "sobre", user)

        if op == "Create":
            iscreated = create_user_db(user)
            server.send_msg(
                MSGOP_CREATED if iscreated
                else MSGERROP_ALREADY_EXISTS
            )
            if iscreated:
                print(direc, "Ha creado el usuario")

        elif op == "Update":
            newuser = User(*server.recv_obj())
            if user_correct_login_db(user):
                if newuser != user:
                    isupdated = update_user_db(user.alias, newuser)
                    server.send_msg(
                        MSGOP_UPDATED if isupdated
                        else MSGERROP_ALREADY_EXISTS
                    )
                    if isupdated:
                        print(direc, "Ha cambiado el usuario a", newuser)
                else:
                    server.send_msg(MSGERROP_ALREADY_EXISTS)
            else:
                server.send_msg(MSGERROP_NOT_EXISTS)

        elif op == "Delete":
            if user_correct_login_db(user):
                isdeleted = delete_user_db(user.alias)
                server.send_msg(
                    MSGOP_DELETED if isdeleted
                    else MSGERROP_NOT_EXISTS
                )
                if isdeleted:
                    print(direc, "Ha eliminado el usuario")
            else:
                server.send_msg(MSGERROP_NOT_EXISTS)

        else:
            server.send_msg(MSGERROP_ERROR)

        conn.close()