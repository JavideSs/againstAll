'''
args: -ar <AA_Registry-ip>:<AA_Registry-port> -ae <AA_Engine-ip>:<AA_Engine-port> -ak <kafka-ip>:<kafka-port(29093)>
python AA_Player.py -ar "https://localhost:2220" -ae "localhost:3333" -ak "localhost:29093"
'''

from common_utils import *

import time, json

import socket

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

import requests

import curses, curses.panel

#==================================================

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("-ar", "--registryaddr", required=True, type=str)
ap.add_argument("-ae", "--engineaddr", required=True, type=str)
ap.add_argument("-ak", "--kafkaaddr", required=True, type=str)
ap.add_argument("-ms", "--mapsize", default=20, type=int)
args = vars(ap.parse_args())

registry_with_apirest = lambda: args["registryaddr"].startswith("http")

ADDR__REGISTRY = args["registryaddr"] if registry_with_apirest() else getaddr(args["registryaddr"])
ADDR__ENGINE = getaddr(args["engineaddr"])
ADDR__KAFKA = args["kafkaaddr"]

TIMEREFRESH = 0.01

MAPSIZE = args["mapsize"]

MSGEXCEPT_CONNREGISTRY = "Error, servidor registro no disponible"
MSGEXCEPT_CONNENGINE = "Error, servidor motor no disponible"
MSGEXCEPT_CONNKAFKA = "Error, servidor de colas no disponible"

BANNER = r"""
   /\   _   _. o ._   _ _|_    /\  | |
  /--\ (_| (_| | | | _>  |_   /--\ | |
        _|
"""

#==================================================

class MyCurses():
    def clear(screen, drawcmd):
        screen.clear()
        drawcmd()
        screen.refresh()


    def log(screen, x,y, text):
        screen.addstr(y,x, text, MyCurses.Style.fromStr("log_error" if text.startswith("Error") else "log"))
        screen.refresh()


    class Style():
        def init_pairs():
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_CYAN)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
            curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)

        def none():
            return 0
        def btn_accept():
            return curses.color_pair(1) | curses.A_BOLD
        def btn_cancel():
            return curses.color_pair(2) | curses.A_BOLD
        def default():
            return curses.color_pair(3) | curses.A_BOLD
        def log():
            return curses.color_pair(4)
        def log_error():
            return curses.color_pair(5)

        def fromStr(text):
            return vars(MyCurses.Style)[text]()


    class Form():
        def __init__(self, screen, x,y):
            self.pos = 0
            self.items = []

            self.screen = screen.subwin(y,x)
            self.screen.keypad(True)
            self.screen.nodelay(True)

        def addText(self, text, style="none"):
            self.items.append({
                "type": "text",
                "text": text,
                "style": MyCurses.Style.fromStr(style)
            })

        def addBtn(self, text, func, andexit=True, style="none"):
            self.items.append({
                "type": "btn",
                "text": text,
                "func": func,
                "andexit": andexit,
                "style": MyCurses.Style.fromStr(style)
            })

        def addEntry(self, text, default="", style="none"):
            self.items.append({
                "type": "entry",
                "text": text,
                "input": " "+default,
                "style": MyCurses.Style.fromStr(style)
            })

        def getEntries(self):
            return {item["text"]: item["input"] for item in self.items if item["type"] == "entry"}

        def __refresh(self):
            self.screen.refresh()

        def refresh(self):
            self.navigate(0)
            for i, item in enumerate(self.items):
                mode = curses.A_REVERSE if i == self.pos else curses.A_NORMAL
                self.screen.addstr(i,0, item["text"], mode | item["style"])
                if item["type"] == "entry":
                    self.screen.addstr(i,len(item["text"]), " :", mode | item["style"])
                    self.screen.addstr(i,len(item["text"])+3, item["input"], item["style"])

            self.__refresh()

        def navigate(self, n):
            self.pos = (self.pos + n) % len(self.items)
            while self.items[self.pos]["type"] == "text": self.pos+=1

        def mainloop(self):
            while True:
                time.sleep(TIMEREFRESH)
                key = self.screen.getch()

                if key in (curses.KEY_ENTER, ord("\n")):
                    item = self.items[self.pos]

                    if item["type"] == "btn":
                        if item["func"] == "break":
                            break
                        entries_values = self.getEntries()
                        if any(entries_values):
                            item["func"](entries_values)
                        else:
                            item["func"]()
                        if item["andexit"]:
                            break

                    elif item["type"] == "entry":
                        curses.curs_set(1)
                        curses.echo(True)
                        self.screen.addstr(self.pos,len(item["text"])+3, " "*len(item["input"]))
                        self.input = self.screen.derwin(self.pos,len(item["text"])+3)
                        item["input"] = self.input.getstr().decode()
                        curses.echo(False)
                        curses.curs_set(0)

                elif key in (curses.KEY_UP, curses.KEY_DOWN):
                    def update(self, mode):
                        item = self.items[self.pos]
                        self.screen.addstr(self.pos,0, item["text"], mode | item["style"])
                        if item["type"] == "entry":
                            self.screen.addstr(self.pos,len(item["text"]), " :", mode | item["style"])

                    update(self, curses.A_NORMAL)
                    self.navigate(-1 if key == curses.KEY_UP else 1)
                    update(self, curses.A_REVERSE)

                self.__refresh()
            self.screen.nodelay(False)


    class Board():
        def __init__(self, screen, x,y, size):
            self.size = size
            self.xgridcol = lambda x: x*3
            self.ygridlin = lambda y: y
            self.grids = set()

            self.screen = screen.subwin(2+self.ygridlin(size),2+self.xgridcol(size), y,x)

        def __refresh(self):
            self.screen.refresh()

        def refresh(self, borderstyle):
            self.screen.attron(borderstyle)
            self.screen.border()
            self.screen.attroff(borderstyle)

            for grid in self.grids:
                self.drawGrid(*grid, new=False)

            self.__refresh()

        def drawGrid(self, x,y, value, style, new=True):
            self.screen.addstr(1+self.ygridlin(y),1+self.xgridcol(x), " ", style)
            self.screen.addstr(1+self.ygridlin(y),1+self.xgridcol(x)+1, value, style)
            self.screen.addstr(1+self.ygridlin(y),1+self.xgridcol(x)+2, " ", style)

            if new:
                self.grids.add((x,y, value, style))

            self.__refresh()

        def splash(self, text, style, timeout=0):
            if not "\n" in text:
                x = round(self.size/2)*3 - round(len(text)/2) -1
                y = round(self.size/2) -1 -1
                splash = curses.newwin(1+2,len(text)+2, 6+y,1+x)
            else:
                splash = curses.newwin(len(text.splitlines())+2,self.size-2, 6,1)

            splash.addstr(1,1, text, style)
            panel = curses.panel.new_panel(splash)
            curses.panel.update_panels()
            self.__refresh()

            def hidepanel():
                panel.hide()
                curses.panel.update_panels()
                self.__refresh()

            if timeout>0:
                time.sleep(timeout)
                hidepanel()

            return hidepanel

#==================================================

class PlayerGame():
    def init_pairs(self):
        self.color_pairs = {"p":[], "M":[], "A":[], " ":[]}

        offset_color = 90
        #bg sector1
        curses.init_color(offset_color, 100, 100, 200)
        curses.init_color(offset_color+1, 50, 50, 150)
        #bg sector2
        curses.init_color(offset_color+2, 100, 200, 200)
        curses.init_color(offset_color+3, 100, 150, 150)
        #bg sector3
        curses.init_color(offset_color+4, 200, 100, 200)
        curses.init_color(offset_color+5, 150, 100, 150)
        #bg sector4
        curses.init_color(offset_color+6, 200, 200, 100)
        curses.init_color(offset_color+7, 150, 150, 100)

        offset = 10
        stride_object_collection = 8
        for color_id in (offset_color,offset_color+2,offset_color+4,offset_color+6):
            #Player grid
            pair_id = color_id-offset_color + offset
            curses.init_pair(pair_id, curses.COLOR_WHITE, color_id)
            curses.init_pair(pair_id+1, curses.COLOR_WHITE, color_id+1)
            self.color_pairs["p"].append((pair_id,pair_id+1))
            #Mine grid
            pair_id = color_id-offset_color + offset + stride_object_collection
            curses.init_pair(pair_id, curses.COLOR_RED, color_id)
            curses.init_pair(pair_id+1, curses.COLOR_RED, color_id+1)
            self.color_pairs["M"].append((pair_id,pair_id+1))
            #Food grid
            pair_id = color_id-offset_color + offset + stride_object_collection*2
            curses.init_pair(pair_id, curses.COLOR_GREEN, color_id)
            curses.init_pair(pair_id+1, curses.COLOR_GREEN, color_id+1)
            self.color_pairs["A"].append((pair_id,pair_id+1))
            #Empty grid
            pair_id = color_id-offset_color + offset + stride_object_collection*3
            curses.init_pair(pair_id, curses.COLOR_WHITE, color_id)
            curses.init_pair(pair_id+1, curses.COLOR_WHITE, color_id+1)
            self.color_pairs[" "].append((pair_id,pair_id+1))

    def refresh(self):
        self.board.refresh(MyCurses.Style.fromStr("none"))

    def drawBanner(screen):
        curses.init_pair(9, curses.COLOR_CYAN, curses.COLOR_BLACK)
        style = curses.color_pair(9) | curses.A_BOLD
        screen.addstr(BANNER, style)
        screen.refresh()

    def keyToDirec(key):
        if key == ord("w"):
            return "N"
        elif key == ord("s"):
            return "S"
        elif key == ord("a"):
            return "W"
        elif key == ord("d"):
            return "E"
        elif key == ord("q"):
            return "NW"
        elif key == ord("e"):
            return "NE"
        elif key == ord("z"):
            return "SW"
        elif key == ord("x"):
            return "SE"
        else:
            return None

    def __init__(self, screen, x,y, username):
        self.username = username
        self.actualmap = None

        self.screen = screen
        self.init_pairs()

        self.board = MyCurses.Board(screen, x,y, MAPSIZE)
        self.refresh()

        self.producer = MyKafka.SecureProducer(
            addr = ADDR__KAFKA
        )

        self.consumer = MyKafka.SecureConsumer(
            addr = ADDR__KAFKA,
            topic = "map",
        )

    def getActualMap(self):
        return self.actualmap

    def setMap(self, _map):
        for j, row in enumerate(_map):
            for i, value in enumerate(row):
                SECTORSIZE = MAPSIZE/2
                sector = 0 if i<SECTORSIZE and j<SECTORSIZE else \
                    1 if i<SECTORSIZE and j>=SECTORSIZE else \
                    2 if j<SECTORSIZE else 3
                light = (i+j)%2

                if type(value) is list: #Is player
                    style = curses.color_pair(self.color_pairs["p"][sector][light])
                    if value[0][0].startswith("NPC"): #Is NPC
                        self.board.drawGrid(i,j, str(value[0][1]), style)
                    elif value[0][0] == self.username: #Is Himself
                        self.board.drawGrid(i,j, value[0][0][0].upper(), style | curses.A_BOLD)
                    else:
                        self.board.drawGrid(i,j, value[0][0][0], style)
                else:
                    style = curses.color_pair(self.color_pairs[value][sector][light])
                    self.board.drawGrid(i,j, value, style)

        self.actualmap = _map
        self.screen.refresh()

    def getLivePlayers(self):
        for row in self.actualmap:
            for value in row:
                if type(value) is list:
                    for player in value:
                        yield player

    def drawLeaderboard(self):
        msg = "Player -> Level\n"
        for player in self.getLivePlayers():
            if not player[0].startswith("NPC"):
                msg += "  {player} -> {level}\n".format(player=player[0].capitalize()[:5], level=player[1])
        fhidepanel = self.board.splash(msg, MyCurses.Style.fromStr("none"))
        while self.screen.getch() != ord("h"): continue
        fhidepanel()

    def isAlive(self):
        for player in list(self.getLivePlayers()):
            if player[0] == self.username:
                return True
        return False

    def isEnded(self):
        liveplayers = list(self.getLivePlayers())
        return not len(liveplayers)>1 or not self.isAlive()

    def drawGameOver(self, iswinner):
        if iswinner:
            msg = "Ganaste! :)"
            style = MyCurses.Style.fromStr("log")
        else:
            msg = "Perdiste! :("
            style = MyCurses.Style.fromStr("log_error")
        self.board.splash(msg, style, 5)

    def wait(self):
        self.board.splash("Esperando la partida", MyCurses.Style.fromStr("none"))
        return next(self.consumer).value

    def start(self):
        self.screen.nodelay(True)

        while True:
            time.sleep(TIMEREFRESH)

            key = self.screen.getch()

            if key == ord("h"):
                self.drawLeaderboard()
                continue

            direc = PlayerGame.keyToDirec(key)
            if direc is not None:
                self.producer.send("move", key=self.username, value=direc)

            msg = self.consumer.poll_msg()
            if msg:
                if msg.key == "end":
                    self.drawGameOver(self.username in msg.value["winners"])
                    break

                newmap = msg.value
                self.setMap(newmap)

                if self.isEnded():
                    self.drawGameOver(self.isAlive())
                    break

        self.producer.close()
        self.consumer.close()

        self.screen.nodelay(False)

#==================================================

def join_game(screen, username, client):
    def join():
        MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
        game = PlayerGame(screen, 0,5, username)
        game.refresh()
        client.send_msg("Ready")
        initmap = game.wait()
        game.setMap(initmap)
        game.start()

    MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
    form = MyCurses.Form(screen, 2,5)
    form.addText("¿Estas listo?", style="default")
    form.addBtn("Empezar", join, style="btn_accept")
    form.addBtn("Cancelar", client.close, style="btn_cancel")
    form.refresh()
    form.mainloop()


def check_account(username, passwd):
    if not len(username.strip()) or not len(passwd.strip()):
        return False, "Error. Rellene los campos"
    if not username.isalnum():
        return False, "Error. El Alias debe ser alfanumerico"
    return True, "OK"


def login_game(screen):
    def login(values):
        username, passwd = values["Usuario"],values["Contraseña"]
        is_valid_account, msg_check_account = check_account(username, passwd)
        if is_valid_account:
            try:
                with MySecureSocket("TCP", ADDR__ENGINE) as client:
                    client.send_obj((username, passwd))
                    msg_login = client.recv_msg()
                    MyCurses.log(screen, 0,0, msg_login)
                    time.sleep(2)
                    if not msg_login.startswith("Error"):
                        join_game(screen, username, client)
            except socket.error as e:
                MyCurses.log(screen, 0,0, toprint_exception(MSGEXCEPT_CONNENGINE, e))
                time.sleep(2)
            except MyKafka.KafkaError as e:
                MyCurses.log(screen, 0,0, toprint_exception(MSGEXCEPT_CONNKAFKA, e))
                time.sleep(2)
        else:
            MyCurses.log(screen, 0,0, msg_check_account)
            time.sleep(2)

    MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
    form = MyCurses.Form(screen, 2,5)
    form.addEntry("Usuario", style="default")
    form.addEntry("Contraseña", style="default")
    form.addBtn("Unirse a la partida", login, style="btn_accept")
    form.addBtn("Cancelar", "break", style="btn_cancel")
    form.refresh()
    form.mainloop()


def registry(screen, values, op):
    username, passwd = values["Usuario"],values["Contraseña"]
    is_valid_account, msg_check_account = check_account(username, passwd)
    if is_valid_account:
        if registry_with_apirest():
            try:
                requests_disable_warning()
                if op == "Create":
                    res = requests.post(ADDR__REGISTRY, verify=False,
                        json={"alias":username, "password":passwd}
                    )
                elif op == "Update":
                    res = requests.patch(ADDR__REGISTRY, verify=False,
                        json={"alias":username, "password":passwd,
                              "newalias":values["Nuevo alias"], "newpassword":values["Nueva contraseña"]}
                    )
                elif op == "Delete":
                    res = requests.delete(ADDR__REGISTRY, verify=False,
                        json={"alias":username, "password":passwd}
                    )
                MyCurses.log(screen, 0,0, res.text)
            except requests.exceptions.RequestException as e:
                MyCurses.log(screen, 0,0, toprint_exception(MSGEXCEPT_CONNREGISTRY, e))
        else:
            try:
                with MySecureSocket("TCP", ADDR__REGISTRY) as client:
                    client.send_msg(op)
                    client.send_obj((username, passwd))
                    if op == "Update":
                        client.send_obj((values["Nuevo alias"],values["Nueva contraseña"]))
                    MyCurses.log(screen, 0,0, client.recv_msg())
            except socket.error as e:
                MyCurses.log(screen, 0,0, toprint_exception(MSGEXCEPT_CONNREGISTRY, e))
    else:
        MyCurses.log(screen, 0,0, msg_check_account)
    time.sleep(2)


def create_account(screen):
    MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
    form = MyCurses.Form(screen, 2,5)
    form.addEntry("Usuario", style="default")
    form.addEntry("Contraseña", style="default")
    form.addBtn("Crear cuenta", lambda values: registry(screen, values, "Create"), style="btn_accept")
    form.addBtn("Cancelar", "break", style="btn_cancel")
    form.refresh()
    form.mainloop()


def edit_account(screen):
    MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
    form = MyCurses.Form(screen, 2,5)
    form.addEntry("Usuario", style="default")
    form.addEntry("Contraseña", style="default")
    form.addEntry("Nuevo alias", style="default")
    form.addEntry("Nueva contraseña", style="default")
    form.addBtn("Editar cuenta", lambda values: registry(screen, values, "Update"), style="btn_accept")
    form.addBtn("Cancelar", "break", style="btn_cancel")
    form.refresh()
    form.mainloop()


def delete_account(screen):
    MyCurses.clear(screen, lambda: PlayerGame.drawBanner(screen))
    form = MyCurses.Form(screen, 2,5)
    form.addEntry("Usuario", style="default")
    form.addEntry("Contraseña", style="default")
    form.addBtn("Eliminar cuenta", lambda values: registry(screen, values, "Delete"), style="btn_accept")
    form.addBtn("Cancelar", "break", style="btn_cancel")
    form.refresh()
    form.mainloop()


def check_terminal_support(stdscreen):
    if curses.ncurses_version.major<6 or (curses.ncurses_version.major==6 and curses.ncurses_version.minor<1):
        raise Exception("Se necesita una version de curses superior a la 6.1")

    if not curses.has_colors():
        raise Exception("La terminal no soporta colores")
    if not curses.can_change_color():
        raise Exception("La terminal no soporta cambio de colores")

    terminal_size = stdscreen.getmaxyx()
    if terminal_size[0]<27 or terminal_size[1]<62:
        raise Exception("El espacio de terminal debe ser al menos 27x62")


def main(stdscreen):
    check_terminal_support(stdscreen)
    curses.curs_set(0)
    curses.start_color()
    MyCurses.Style.init_pairs()

    while True:
        MyCurses.clear(stdscreen, lambda: PlayerGame.drawBanner(stdscreen))
        form = MyCurses.Form(stdscreen, 2,5)
        form.addBtn("Iniciar sesion", lambda: login_game(stdscreen), style="btn_accept")
        form.addBtn("Crear cuenta", lambda: create_account(stdscreen), style="btn_accept")
        form.addBtn("Editar cuenta", lambda: edit_account(stdscreen), style="btn_accept")
        form.addBtn("Eliminar cuenta", lambda: delete_account(stdscreen), style="btn_cancel")
        form.addBtn("Salir", exit, style="btn_cancel")
        form.refresh()
        form.mainloop()

curses.wrapper(main)