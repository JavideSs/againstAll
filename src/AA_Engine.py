'''
args: -p <port> -ak <kafka-ip>:<kafka-port(29093)>
python AA_Engine.py -p 3333 -ak "localhost:29093"

- FOR PLAYER
client.send_obj(("user","password"))
client.recv_msg() -> MSGOPRE
client.send_msg("Ready")
client.with_kafka.recv() -> "start": Initial Map

- FOR NPC
client.with_kafka.send("alias": ".")
client.with_kafka.recv() -> "alias": Map

thread1:
    while move:
        client.with_kafka.send("alias": "direction")
thread2:
    while any player move:
        client.with_kafka.recv() -> "anyalias": Map
    if timeout:
        client.with_kafka.recv() -> "end":{"winner:[anyalias,]"}
'''

from common_utils import *

import sys, threading, time, random, json

import socket

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

#==================================================

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("-p", "--port", required=True, type=int)
ap.add_argument("-ak", "--kafkaaddr", required=True, type=str)
ap.add_argument("-ms", "--mapsize", default=20, type=int)
ap.add_argument("-mp", "--maxplayers", default=20, type=int)
ap.add_argument("-t", "--gametimeout", default=6000, type=int)
args = vars(ap.parse_args())

ADDR = ("", args["port"])
ADDR__KAFKA = args["kafkaaddr"]

FDATA_WEATHERS = "../data/weathers.csv"
FKEY_OPENWEATHER_KEY = "../keys/openweather.key"
FDATA_DB = "../data/db.db"
FKEYS_SSL = ("../keys/cert.pem", "../keys/key.pem")

MAPSIZE = args["mapsize"]
MAXPLAYERS = args["maxplayers"]
GAME_TIMEOUT = args["gametimeout"]

if MAXPLAYERS<10 or MAPSIZE<10 or GAME_TIMEOUT<0:
    raise Exception("Parametros de juego imposibles")
if MAPSIZE%2:
    raise Exception("El mapa debe ser con un tamaño par")
if MAXPLAYERS > MAPSIZE:
    raise Exception("No caben tantos jugadores en el mapa")

MSGJOIN = "Usuario unido a la partida"

MSGERRJOIN_NOT_EXISTS = "Error. La cuenta no coincide con ninguna registrada"
MSGERRJOIN_ALREADY_JOINED = "Error. Usuario ya unido a la partida"
MSGERRJOIN_MAXPLAYERS = "Error. Maximo de usuarios permitidos en la partida"

MSGEXCEPT_CONNWEATHER = "Servidor de tiempo no disponible. Intentado de nuevo en 5s..."
MSGEXCEPT_CONNKAFKA = "Servidor de colas no disponible"

#==================================================

import requests
class Requests():

    @staticmethod
    def get_cities(n):
        import csv

        with open(FKEY_OPENWEATHER_KEY) as f:
            OPENWEATHER_KEY = f.read()
        UNITS = "metric"
        URL = "https://api.openweathermap.org/data/2.5/weather?appid={key}&units={units}&q={city}"

        with open(FDATA_WEATHERS) as f:
            weathers = list(csv.reader(f, delimiter=";"))

        cities = set()
        while len(cities) < n:
            city = random.choice(weathers)[0]
            if city not in cities:
                cities.add(city)
                res = requests.get(URL.format(key=OPENWEATHER_KEY, units=UNITS, city=city))
                temp = json.loads(res.text)["main"]["temp"]
                yield {"city":city, "temperature":temp}


class Player():
    def __init__(self, alias, level):
        self.alias = alias
        self.pos = Cell(-1, -1)
        self.level = level

    def __str__(self):
        return "Jugador " + self.alias + " con nivel " + str(self.getTotalLevel())

    def serialize(self):
        playerdict = vars(self).copy()
        playerdict["pos"] = playerdict["pos"].repr()
        playerdict["totallevel"] = self.getTotalLevel()
        return playerdict

    def deserialize(self, playerdict):
        for key, value in playerdict:
            if hasattr(self, key):
                setattr(self, key, value)
        self.pos = Cell(*self.pos)

    def getTotalLevel(self):
        return self.level

    def isAlive(self):
        return self.level != -1

    def die(self):
        self.level = -1

    def upLevel(self):
        pass


class HumanPlayer(Player):
    def __init__(self, alias=None, password=None):
        self.password = password
        super().__init__(alias, level=1)
        self.ef = random.randint(-10,10)
        self.ec = random.randint(-10,10)
        self.temperature = None

    def upLevel(self):
        self.level += 1

    def getTotalLevel(self):
        if self.temperature is None:
            return self.level
        elif self.temperature <= 10:
            return max(0, self.level + self.ef)
        elif self.temperature >= 25:
            return max(0, self.level + self.ec)
        else:
            return self.level


class NPC(Player):
    def __init__(self, alias=None):
        super().__init__(alias, level=random.randint(0,9))

    def __str__(self):
        return "NPC con nivel " + str(self.getTotalLevel())


class Direction():
    N = (0,-1)
    S = (0,1)
    W = (-1,0)
    E = (1,0)
    NW = (-1,-1)
    NE = (1,-1)
    SW = (-1,1)
    SE = (1,1)

    def fromStr(text):
        return vars(Direction)[text]


class Cell():
    MINE = "M"
    FOOD= "A"
    EMPTY = " "

    NOTPLAYER = (MINE, FOOD, EMPTY)

    def __init__(self, column, row):
        self.row = row
        self.column = column

    def __str__(self):
        return "({i},{j})".format(i=self.column, j=self.row)

    def __eq__(self, other):
        return self.column == other.getColumn() and self.row == other.getRow()

    def __add__(self, direc):
        return Cell(self.column+direc[0], self.row+direc[1])

    def repr(self):
        return (self.column, self.row)

    def getColumn(self):
        return self.column

    def getRow(self):
        return self.row

    def normalize(self, columnsize, rowsize):
        self.column %= columnsize
        if self.column == 0: self.column = columnsize
        self.row %= rowsize
        if self.row == 0: self.row = rowsize


class Map():
    '''
    ex:
        [[" ",["jms"],"M","A",["p1","p2"],"M"],...]
    '''
    SIZE = MAPSIZE
    SIZE_CITY = SIZE/2
    RAND_ROW_VALUES_PERCENTAGE = [
        (Cell.EMPTY, 0.7*SIZE),
        (Cell.MINE, 0.2*SIZE),
        (Cell.FOOD, 0.1*SIZE)
    ]

    def __init__(self, map, cities):
        self.map:list = map
        self.cities:list = cities

    def __str__(self):
        strmap = ""
        for row in self.map:
            strmap += "|"
            for value in row:
                strmap += str(value)
                strmap += "|"
            strmap += "\n"
        return strmap

    def newEmpty():
        map = [[" " for _ in range(Map.SIZE)] for _ in range(Map.SIZE)]
        cities = []
        return Map(map, cities)

    def newRand():
        map = []
        for _ in range(Map.SIZE):
            row = []
            for value, weight in Map.RAND_ROW_VALUES_PERCENTAGE:
                row.extend([value]*int(weight))
            while len(row) < Map.SIZE:
                row.append(Cell.EMPTY)
            random.shuffle(row)
            map.append(row)

        while True:
            try:
                cities = list(Requests.get_cities(4))
                break
            except socket.error as e:
                print(toprint_exception(MSGEXCEPT_CONNWEATHER, e))
                time.sleep(5)

        return Map(map, cities)

    def getMap(self):
        return self.map

    def getCities(self):
        return self.cities

    def getCell(self, cell):
        return self.map[cell.getRow()-1][cell.getColumn()-1]

    def setCell(self, cell, value):
        self.map[cell.getRow()-1][cell.getColumn()-1] = value

    def setValueCell(self, cell, value):
        if self.getCell(cell) in Cell.NOTPLAYER:
            self.setCell(cell, [value,])
        else:
            self.map[cell.getRow()-1][cell.getColumn()-1].append(value)

    def delValueCell(self, cell, value):
        self.map[cell.getRow()-1][cell.getColumn()-1].remove(value)

    def getTemperature(self, cell):
        if not self.cities:
            return None

        '''
        |0|1|
        |2|3|
        '''
        if cell.getRow() <= Map.SIZE_CITY:
            if cell.getColumn() <= Map.SIZE_CITY:
                sector = 0
            else:
                sector = 1
        else:
            if cell.getColumn() <= Map.SIZE_CITY:
                sector = 2
            else:
                sector = 3
        return self.cities[sector]["temperature"]


class Game():
    def __init__(self, map, players, starttime):
        self.map:Map = map
        self.players:dict[str,Player] = players
        self.starttime:float = starttime

    def __str__(self):
        strgame = str(self.map)
        for player in self.getPlayers():
            strgame += str(player) + "\n"
        return strgame

    def new():
        return Game(Map.newRand(), dict(), time.time())

    def load(file):
        if not exists_table_db(FDATA_DB, "gameplay"):
            return None

        res = rundb(file,
            """
            SELECT key, value
            FROM gameplay
            """
        )
        statusdb, starttimedb, mapdb, citiesdb, playersdb = (json.loads(i[1]) for i in res.fetchall())

        if not statusdb:
            return None

        map = Map(mapdb, citiesdb)

        players = {}
        for playerdb in playersdb:
            playerisnpc = playerdb["alias"].startswith("NPC")
            player = NPC() if playerisnpc else HumanPlayer()
            player.deserialize(playerdb.items())
            players[player.alias] = player

        starttime = time.time() - starttimedb

        return Game(map, players, starttime)

    def store(self, file, status=True):
        rundb(file,
            """
            CREATE TABLE IF NOT EXISTS gameplay(
                key VARCHAR[10] PRIMARY KEY,
                value TEXT
            )
            """
        )
        rundb(file,
            """
            INSERT OR REPLACE INTO gameplay
            VALUES ('status', ?), ('time', ?), ('map', ?), ('cities', ?), ('players', ?)
            """
            ,list(json.dumps(i) for i in (
                status,
                self.getTime(),
                self.map.getMap(),
                self.map.getCities(),
                [p.serialize() for p in self.players.values()]
            ))
        )

    def getMap(self):
        '''
        ex:
            [[" ",[("jms",3)],"M","A",[("p1",-2),("p2",1)],"M"],...]
        '''
        maptosend = Map.newEmpty().map
        for j, row in enumerate(self.map.getMap()):
            for i, value in enumerate(row):
                if type(value) is list:
                    maptosend[j][i] = [(p, self.players[p].getTotalLevel()) for p in value]
                else:
                    maptosend[j][i] = value
        return maptosend

    def getPlayers(self):
        return list(filter(lambda player: player.isAlive(), self.players.values()))

    def getTime(self):
        return time.time() - self.starttime

    def isEnded(self):
        alive_players = self.getPlayers()
        for player in alive_players:
            if isinstance(player, HumanPlayer):
                return len(alive_players) == 1
        return True

    def inProgress(self):
        return len(list(filter(lambda p: isinstance(p, HumanPlayer), self.getPlayers()))) > 1

    def getWinners(self):
        maxlevel = max([p.getTotalLevel() for p in self.getPlayers()])
        return list(filter(lambda p: p.getTotalLevel() == maxlevel, self.getPlayers()))

    def updatePlayer(self, player, pos):
        player.pos = pos
        player.temperature = self.map.getTemperature(pos)

    def newRandPlayer(self, player):
        while True:
            i = random.randint(1,Map.SIZE)
            j = random.randint(1,Map.SIZE)
            pos = Cell(i,j)

            if self.map.getCell(pos) == Cell.EMPTY:
                self.updatePlayer(player, pos)
                self.players[player.alias] = player
                self.map.setValueCell(pos, player.alias)
                break

    def move(self, playeralias, direc):
        if playeralias not in (p.alias for p in self.getPlayers()):
            return False

        player = self.players[playeralias]
        topos = (player.pos + direc)
        topos.normalize(Map.SIZE,Map.SIZE)
        self.update(player, topos)
        return True

    def update(self, player, topos):
        if len(self.map.getCell(player.pos)) == 1:
            self.map.setCell(player.pos, Cell.EMPTY)
        else:
            self.map.delValueCell(player.pos, player.alias)
        self.updatePlayer(player, topos)

        value = self.map.getCell(topos)
        if value == Cell.EMPTY:
            self.map.setValueCell(topos, player.alias)
        elif value == Cell.FOOD:
            self.map.setValueCell(topos, player.alias)
            player.upLevel()
        elif value == Cell.MINE:
            if isinstance(player, NPC):
                self.map.setValueCell(topos, player.alias)
            else:
                self.map.setCell(topos, Cell.EMPTY)
                player.die()
        else:
            self.map.setValueCell(topos, player.alias)
            self.fight(player)

    def fight(self, player1):
        for player2 in self.getPlayers():
            if player2.pos == player1.pos and player1.getTotalLevel() != player2.getTotalLevel():
                playertodel = min(player1, player2, key=lambda player: player.getTotalLevel())
                self.map.delValueCell(playertodel.pos, playertodel.alias)
                playertodel.die()

#==================================================

class ConnHumanPlayer(HumanPlayer):
    def __init__(self, conn, alias, password):
        self.conn = conn
        self.ready = False
        super().__init__(alias, password)

    def serialize(self):
        playerdict = super().serialize()
        playerdict.pop("conn")
        return playerdict

    def is_correct_login_db(self):
        res = rundb(FDATA_DB,
            """
            SELECT password
            FROM users
            WHERE alias = ?
            """
            ,(self.alias,)
        )
        data_fetch = res.fetchone()
        if data_fetch is None:
            return False
        salt, hash = json.loads(data_fetch[0])
        return data_fetch is not None and hash == hashpasswd(self.password, salt)[1]


def print_count(text, textargs, nreverselines):
    if nreverselines == -1:
        sys.stdout.write(text.format(*textargs))
        sys.stdout.write("\n")
    else:
        sys.stdout.write("\033[{n}A".format(n=nreverselines+1))
        sys.stdout.write(text.format(*textargs))
        sys.stdout.write("\033[{n}B".format(n=nreverselines+1))
        sys.stdout.write("\033[0G")
    sys.stdout.flush()

PRINT_USERS_JOIN = "Usuarios unidos: {0}/{1}"
PRINT_USERS_READY = "Usuarios listos: {0}/{1}"


def handle_player_join(conn, addr, server, players):
    player = ConnHumanPlayer(conn, *server.recv_obj(client=addr))

    if not player.is_correct_login_db():
        server.send_msg(MSGERRJOIN_NOT_EXISTS, client=addr)
        conn.close()
        return

    if any(p.alias == player.alias for p in players):
        server.send_msg(MSGERRJOIN_ALREADY_JOINED, client=addr)
        conn.close()
        return

    '''
    Two players can join at the same time,
    and the first reaches the MAXPLAYERS
    with an exception in the second.
    Is discarded by almost null probability
    and does not affect the system
    (can be controlled in the user)
    '''
    if len(players) == MAXPLAYERS:
        server.send_msg(MSGERRJOIN_MAXPLAYERS, client=addr)
        conn.close()
        return

    def print_count_users_join(players):
        print_count(PRINT_USERS_JOIN, (len(players), MAXPLAYERS), 1)

    def print_count_users_ready(players):
        users_ready = {p for p in players if p.ready}
        print_count(PRINT_USERS_READY, (len(users_ready), len(players)), 0)

    players.add(player)
    server.send_msg(MSGJOIN, client=addr)
    print_count_users_join(players)
    print_count_users_ready(players)

    try:
        server.recv_msg(client=addr) #Ready
    except socket.error:
        """
        user can join but not start
        """
        players.remove(player)
        print_count_users_join(players)
        print_count_users_ready(players)

    player.ready = True
    print_count_users_ready(players)

    users_ready = {p for p in players if p.ready}
    if len(users_ready) == len(players) >= 2:
        server.close()

#==================================================

def gameplay(*, game=None, players=None):
    producer = MyKafka.SecureProducer(
        addr = ADDR__KAFKA
    )

    consumer = MyKafka.SecureConsumer(
        addr = ADDR__KAFKA,
        topic = "move",
        group = "engine"
    )

    if not game:
        game = Game.new()

        for player in players:
            game.newRandPlayer(player)

        producer.send("map", key="start", value=game.getMap())
        print("Empieza el juego!\n")
    else:
        '''
        All moves when engine is down are discarded
        '''
        consumer.consume_topic()
        print("Se retoma la partida pendiente!")

    print(game)
    game.store(FDATA_DB)

    while True:
        msg = consumer.poll_msg()
        if msg:
            consumer.commit()

            playeralias, direc = msg.key, msg.value

            if direc == ".":
                if not game.inProgress():
                    continue
                print("NPC unido")
                game.newRandPlayer(NPC(playeralias))
            else:
                print(playeralias, "se mueve en la direcion", direc)
                res = game.move(playeralias, Direction.fromStr(direc))
                if not res:
                    continue

            print(game)
            producer.send("map", key=playeralias, value=game.getMap())
            game.store(FDATA_DB)

            if game.isEnded():
                break

        if game.getTime() >= GAME_TIMEOUT:
            producer.send("map", key="end", value={"winners":[p.alias for p in game.getWinners()]})
            print("Se agoto el tiempo")
            break

    producer.close()
    consumer.close()

    game.store(FDATA_DB, status=False)
    print("La partida ha terminado")
    for player in game.getWinners():
        print("Ha ganado", player)

#==================================================

oldgameplay = Game.load(FDATA_DB)
if oldgameplay:
    try:
        gameplay(game=oldgameplay)
    except MyKafka.KafkaError as e:
        print(toprint_exception(MSGEXCEPT_CONNKAFKA, e))

while True:
    res = input("Crear partida? (s/n): ")
    if res in ("n","N"):
        break
    if res not in ("s","S","y","Y"):
        continue

    print("Esperando jugadores...")

    with MySecureSocket("TCP", ADDR) as server:
        server.settimeout(0.1) #Any time

        print_count(PRINT_USERS_JOIN, (0, MAXPLAYERS), -1)
        print_count(PRINT_USERS_READY, (0, 0), -1)
        players = set()

        while True:
            try:
                conn, addr = server.accept(cert=FKEYS_SSL)
                threading.Thread(
                    target=handle_player_join,
                    args=(conn, addr, server, players),
                    name=addr[0],
                    daemon=True
                ).start()
            except socket.timeout:
                '''
                Linux fun:
                accept(), if is running, not gives an error if the server is closed
                settimeout and handle the exception to repeat the accept()
                '''
                continue
            except socket.error:
                '''
                Last player to accept closes the server
                accept() that was waiting gives an error
                '''
                break

    try:
        gameplay(players=players)
    except MyKafka.KafkaError as e:
        print(toprint_exception(MSGEXCEPT_CONNKAFKA, e))