'''
args: <port>
python API_Engine.py 4444

GET [/status] -> status
GET [/game] -> map
GET [/players] -> players -> [{"alias":alias,"level":level},...]
GET [/] -> map + players -> {"map":map, "players":players}
'''

from common_utils import *

import sys, json

import flask

import sqlite3

#==================================================

ADDR = ("0.0.0.0", int(sys.argv[1]))

FDATA_DB = "../data/db.db"
FKEYS_SSL = ("../keys/cert.pem", "../keys/key.pem")

MSG_DBNOTEXISTS = ":/ Tenemos problemas"
MSG_GAMESTARTED = ":) Partida en curso"
MSG_GAMENOTSTARTED = ":( No hay partida en curso"

DEBUG = False
#==================================================

def exists():
    return exists_table_db(FDATA_DB, "gameplay")


def get(key):
    res = rundb(FDATA_DB,
        """
        SELECT key, value
        FROM gameplay
        WHERE key="{}"
        """.format(key)
    )
    return json.loads(res.fetchall()[0][1])


with MyFlask.APIREST(name="engine", addr=ADDR, ssl_context=FKEYS_SSL) as server:
    @server.route("/gameplay/status")
    def send_status():
        if DEBUG: print(MyFlask.APIREST.getAddr(), "Solicita GET sobre /gameplay/status")
        if not exists():
            return MyFlask.APIREST.send(MSG_DBNOTEXISTS)
        return MyFlask.APIREST.send(MSG_GAMESTARTED if get("status") else MSG_GAMENOTSTARTED)

    @server.route("/gameplay/game")
    def send_map():
        if DEBUG: print(MyFlask.APIREST.getAddr(), "Solicita GET sobre /gameplay/game")
        if not exists():
            return MyFlask.APIREST.send(MSG_DBNOTEXISTS)
        return MyFlask.APIREST.send(get("map"))

    @server.route("/gameplay/players")
    def send_players():
        if DEBUG: print(MyFlask.APIREST.getAddr(), "Solicita GET sobre /gameplay/players")
        if not exists():
            return MyFlask.APIREST.send(MSG_DBNOTEXISTS)
        return MyFlask.APIREST.send([
            {
                "alias":player["alias"],
                "alive":player["level"]!=1,
                "level":player["totallevel"],
                "pos":player["pos"]
            } for player in get("players")
        ])

    @server.route("/gameplay")
    def send_all():
        if DEBUG: print(MyFlask.APIREST.getAddr(), "Solicita GET sobre /gameplay")
        if not exists():
            return MyFlask.APIREST.send(MSG_DBNOTEXISTS)
        return MyFlask.APIREST.send({"map":send_map().json,"players":send_players().json})