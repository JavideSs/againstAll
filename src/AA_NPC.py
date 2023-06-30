'''
args: -ak <kafka-ip>:<kafka-port(29092)>
python AA_NPC.py -ak "localhost:29092"
'''

from common_utils import *

import time, random, uuid, json

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

#==================================================

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("-ak", "--kafkaaddr", required=True, type=str)
ap.add_argument("-t", "--type", default="normal", choices=["normal","agresivo"])
ap.add_argument("-s", "--sleeptime", default=5, type=int)
args = vars(ap.parse_args())

ADDR__KAFKA = args["kafkaaddr"]

TYPE = args["type"]
SLEEPTIME = args["sleeptime"]

if SLEEPTIME < 0:
    raise Exception("Parametros de juego imposibles")

MSGEXCEPT_CONNKAFKA = "Servidor de colas no disponible"

#==================================================

class NPCGame():
    def __init__(self):
        self.username = "NPC"+str(uuid.uuid1())

        self.producer = MyKafka.Producer(
            addr = ADDR__KAFKA
        )

        self.consumer = MyKafka.Consumer(
            addr = ADDR__KAFKA,
            topic = "map",
        )

    def getLivePlayers(self):
        for row in self.actualmap:
            for value in row:
                if type(value) is list:
                    for player in value:
                        yield player

    def isAlive(self):
        for player in list(self.getLivePlayers()):
            if player[0] == self.username:
                return True
        return False

    def isEnded(self):
        liveplayers = list(self.getLivePlayers())
        humanplayers = list(filter(lambda player: not player[0].startswith("NPC"), liveplayers))
        return not len(humanplayers)>1 or not self.isAlive()

    def wait(self):
        self.producer.send("move", key=self.username, value=".")
        '''
        If the NPC cannot play, the map with it will not be received
        '''
        msg = next(self.consumer)
        self.actualmap = msg.value
        return msg.key == self.username

    def play(self):
        while True:
            '''
            Between the wait of time.sleep() there can be several moves
            only want the last one
            '''
            msg = self.consumer.last_kafka_msg()
            if msg:
                if msg.key == "end":
                    break

                self.actualmap = msg.value

            if self.isEnded():
                break

            direc = self.doDirec()
            print("Se mueve:", direc)
            self.producer.send("move", key=self.username, value=direc)

            time.sleep(SLEEPTIME)

        self.producer.close()
        self.consumer.close()


class RandomNPCGame(NPCGame):
    def do_direc():
        return random.choice(("N","S","W","E","NW","NE","SW","SE"))

    def __init__(self):
        super().__init__()

    def doDirec(self):
        return RandomNPCGame.do_direc()


class AggressiveNPCGame(NPCGame):
    def do_direc(target_coordinate, current_coordinate):
        delta_x = target_coordinate[0] - current_coordinate[0]
        delta_y = target_coordinate[1] - current_coordinate[1]

        if delta_x==0 and delta_y==0:
            self.random_count = 5

        if abs(delta_x) < abs(delta_y):
            if delta_y < 0:
                return "N"
            else:
                return "S"
        elif abs(delta_x) > abs(delta_y):
            if delta_x < 0:
                return "W"
            else:
                return "E"
        else:
            if delta_x<0 and delta_y<0:
                return "NW"
            elif delta_x>0 and delta_y<0:
                return "NE"
            elif delta_x<0 and delta_y>0:
                return "SW"
            else:
                return "SE"

    def __init__(self):
        super().__init__()

    def doDirec(self):
        def distance(coord1, coord2):
            return abs(coord1[0]-coord2[0]) + abs(coord1[1]-coord2[1])

        players = []
        for j, row in enumerate(self.actualmap):
            for i, value in enumerate(row):
                if type(value) is list:
                    for player in value:
                        if player[0] == self.username:
                            this_npc = ((i,j),player[1])
                            break
                        players.append(((i,j),player[1]))

        players = [p for p in players if p[1] < this_npc[1]]

        if not players:
            return RandomNPCGame.do_direc()

        near_player_coord = min(players, key=lambda player: distance(player[0], this_npc[0]))
        print("Voy a la coordenada", near_player_coord[0])
        return AggressiveNPCGame.do_direc(near_player_coord[0], this_npc[0])

#==================================================

npc = AggressiveNPCGame() if TYPE=="agresivo" else RandomNPCGame()

try:
    print("Esperando a jugar")
    if npc.wait():
        print("A jugar!")
        npc.play()
        print("Su partida ha acabado")
    else:
        print("No puede jugar, la partida ha acabado")
except MyKafka.KafkaError as e:
    print(toprint_exception(MSGEXCEPT_CONNKAFKA, e))