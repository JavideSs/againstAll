<style>
    .portada{
        text-align: center;
    }
    #asignatura {
        font-size: 15px;
        font-weight: bold;
    }
    #practica {
        font-size: 20px;
        font-weight: bold;
    }
    #titulo {
        font-size: 25px;
        color: lightgreen;
        font-weight: bold;
    }
</style>

<p class="portada" id="asignatura">SISTEMAS DISTRIBUIDOS</p>
<p class="portada" id="practica">- PRÁCTICA 1 -</p>
<p class="portada" id="titulo">SOCKETS, STREAMING DE EVENTOS, COLAS Y MODULARIDAD</p>
<p class="portada">Javier Mellado Sánchez 48800386K</p>
<p class="portada">Universidad de Alicante, 2022-2023</p>

---

<br><br>

# ÍNDICE

- [ÍNDICE](#índice)
- [INTRODUCCIÓN](#introducción)
- [FUNCIONAMIENTO](#funcionamiento)
  - [Registro](#registro)
  - [Partida](#partida)
- [ARQUITECTURA](#arquitectura)
  - [common\_utils](#common_utils)
  - [BASE DE DATOS](#base-de-datos)
  - [KAFKA](#kafka)
  - [AA\_WEATHER](#aa_weather)
    - [COMUNICACIÓN](#comunicación)
    - [PARÁMETROS](#parámetros)
  - [AA\_REGISTRY](#aa_registry)
    - [COMUNICACIÓN](#comunicación-1)
    - [PARÁMETROS](#parámetros-1)
  - [AA\_ENGINE](#aa_engine)
    - [COMUNICACIÓN](#comunicación-2)
    - [PARÁMETROS](#parámetros-2)
  - [AA\_PLAYER](#aa_player)
    - [PARÁMETROS](#parámetros-3)
  - [AA\_NPC](#aa_npc)
    - [PARÁMETROS](#parámetros-4)
- [DESPLIEGUE](#despliegue)
  - [CAÍDAS](#caídas)
- [COMENTARIOS](#comentarios)
  - [POSIBLES MEJORAS](#posibles-mejoras)

<br><br>
<!--<div style="page-break-after: always;"></div>-->

# INTRODUCCIÓN

Se implementa un juego distribuido multijugador online "AGAINST ALL".

Los jugadores, humanos o NPCs, se encuentran en un mapa dividido por ciudades y obstaculizado por minas, donde se alimentarán para subir de nivel y así poder matar a otros jugadores.

Cada ciudad tiene su propio clima,
pudiendo variar aleatoriamente hasta 10 puntos el nivel de los jugadores humanos.
- Se sufre efecto frío si Temperatura <= 10ºC.
- Se sufre efecto calor si Temperatura >= 25ºC.

El movimiento en el tablero es libre (N,S,W,E,NW,NE,SW,SE). Además, la geometría es esférica.

El juego acaba cuando termina el tiempo de partida o un jugador se proclama vencedor.

<br><br>
<!--<div style="page-break-after: always;"></div>-->

# FUNCIONAMIENTO

Para poner en contexto los requisitos de la práctica lo mejor es ver funcionamiento del sistema a nivel de usuario.

## Registro

Para que el jugador humano pueda entrar en partida previamente debe ser registrado.

Se tienen las opciones de crear perfil, editarlo y eliminarlo.

![registro](images/funcionamiento-registro.png)

![registro-crear](images/funcionamiento-registro-crear.png)

![registro-editar](images/funcionamiento-registro-editar.png)

![registro-eliminar](images/funcionamiento-registro-eliminar.png)

<br>

## Partida

El usuario debe iniciar sesión para entrar en la partida.

![partida](images/funcionamiento-partida.png)

![partida-unir](images/funcionamiento-partida-unir.png)

Una vez validado, tiene que confirmar que está listo para comenzar.

![partida-empezar](images/funcionamiento-partida-empezar.png)

Si la partida aún no ha comenzado, espera a que los demás jugadores estén listos.

![partida-esperar](images/funcionamiento-partida-esperar.png)

Cuando estén todos preparados, la partida se presenta en la pantalla.
Nuestro personaje está representado con la inicial de nuestro alias en mayúsculas.

![partida-inicial](images/funcionamiento-partida-inicial.png)

Cada sector, dividido por su color, representa una ciudad.

La partida se controla desde el teclado con:
- Tecla W: (N) Movimiento al norte.
- Tecla S: (S) Movimiento al sur.
- Tecla A: (W) Movimiento al oeste.
- Tecla D: (E) Movimiento al este.
- Tecla Q: (NW) Movimiento al noroeste.
- Tecla E: (NE) Movimiento al noreste.
- Tecla Z: (SW) Movimiento al suroeste.
- Tecla X: (SE) Movimiento al sureste.
- Tecla H: Tabla de clasificación.

Interesa coger el mayor número de alimentos posibles.

![partida-alimentar](images/funcionamiento-partida-alimentar1.png)
![partida-alimentar](images/funcionamiento-partida-alimentar2.png)

Si por desgracia pisamos una mina, moriremos.

![partida-morir](images/funcionamiento-partida-morir.png)
![partida-morir](images/funcionamiento-partida-morir-perder.png)
![partida-morir](images/funcionamiento-partida-morir-ganar.png)

En cualquier momento pueden unirse NPCs.
Tienen un nivel aleatorio fijo establecido inicialmente.
Los alimentos, minas y efectos del clima no les afecta.

![partida-npc](images/funcionamiento-partida-npc.png)

Si varios jugadores se encuentran en la misma casilla, luchan.
Gana aquel que tenga más nivel. Si empatan por tener el mismo nivel se quedan en la casilla.

Aunque en los ejemplos sólo hay dos jugadores, puede haber tantos como casillas libres haya en el mapa.

Como hemos visto en las capturas, los jugadores pueden ver la tabla de clasificaciones en cualquier momento, y al terminar su partida, se informa de si has ganado o perdido.

<br><br>
<!--<div style="page-break-after: always;"></div>-->

# ARQUITECTURA

El sistema es distribuido, se modularizan las funciones posibles en servicios.

<br>

## common_utils

Código en [src/common_utils.py](/src/common_utils.py).

Contiene un conjunto de utilidades comunes a todos los módulos para facilitar sus implementaciones.

Se extienden las clases de Kafka y se simplifica el manejo de un socket.

<br>

## BASE DE DATOS

Base de datos contenida en el archivo [data/db.db](/data/db.db).

Se ha decidido usar SQLite como motor por la simplicidad de la base de datos y la independencia entre sus tablas.

Existen dos tablas:
- "users": Registro de usuarios.

![db-users](images/arquitectura-db-users.jpg)

- gameplay: Variables sobre la última partida.

![db-gameplay](images/arquitectura-db-gameplay.jpg)

<br>

## KAFKA

Especificación del docker de kafka en [src/kafka.docker-compose.yml](/src/kafka.docker-compose.yml).

Kafka puede verse como una cola de mensajes de baja latencia masivamente escalable.

Como cliente en Python se ha usado [kafka-python](https://pypi.org/project/kafka-python/).
Hay unos métodos del consumidor necesarios pero no implementados, definidos en [common_utils.py](#common_utils):
- **sync()**: necesario para el correcto funcionamiento del consumidor.
- **consume_topic()**: necesario en el Engine para descartar movimientos de previas partidas no terminadas.
- **last_kafka_msg()**: necesario en el NPC para obtener el ultimo mapa si su movimiento es inteligente.

El problema es que dependen del timeout del poll, que depende a su vez de la máquina utilizada. Un valor de 1s da buenos resultados.

<br>

## AA_WEATHER

Código en [src/AA_Weather.py](/src/AA_Weather.py).

Servicio que proporciona el tiempo.

Utiliza el archivo [weathers.csv](/data/weathers.csv) para obtener ciudades con su temperatura (un clima).

Se queda a la escucha, por sockets, de que se hagan solicitudes para mandar climas aleatorios.

### COMUNICACIÓN
```
*Se establece la comunicación*
client.recv_obj()
```

### PARÁMETROS
`args: <port>`

<br>

## AA_REGISTRY

Código en [src/AA_Registry.py](/src/AA_Registry.py).

Servicio para el manejo de registros.

Se queda a la escucha, por sockets, de que se haga una solicitud sobre un usuario (registro).

La solicitud puede resultar en la creación de un perfil, en su edición o eliminación,
toda acción repercutida sobre la base de datos.
Devuelve un texto informando la resolución de la solicitud.

### COMUNICACIÓN

```
*Se establece la comunicación*
client.send_msg("Create"|"Update"|"Delete")
client.send_obj(("user","password"))
if Update:
    client.send_obj(("newuser","newpassword"))
client.recv_msg() -> MSGOPRE
```

### PARÁMETROS
`args: <port>`

<br>

## AA_ENGINE

Código en [src/AA_Engine.py](/src/AA_Engine.py).

Servicio para el manejo del juego.

Se queda a la escucha, por sockets, de que se haga el inicio de sesión de un usuario, devolviendo un texto informando de si ha podido unirse a la partida.
En caso afirmativo, el usuario pasa a ser un jugador de la partida, y la conexión se mantiene.

Puede recibir un mensaje de que el jugador está listo;
pero si, mientras no haya sido enviado, el usuario cierra la conexión, se descarta de la partida.
Una vez que todos los usuarios están listos (al menos 2 personas), la partida comienza.
En este punto se acaba la autenticación, los sockets son cerrados, no se volverán a utilizar.

Se crea una nueva partida si la anterior acabó.
El mapa es creado aleatoriamente, y los climas son solicitados al servicio Weather.

Comienza la comunicación a través de una cola Kafka.
Inicialmente se envía el mapa a todos los jugadores.
Durante toda la partida, el Engine consume los movimientos de los jugadores (el tópico "move"), donde la clave es el alias de quien ha movido y el valor la dirección, y se procesa en el juego.
Acto seguido se envía el nuevo mapa resultante (al tópico "map") a todos los jugadores como valor, indicando el alias de quien ha hecho el movimiento en la clave.
Todos los nuevos datos de la partida son guardados en la base de datos.

Se tiene en cuenta que en cualquier momento un NPC puede unirse a la partida.
Además, si la duración de la partida ha superado el tiempo estipulado, en lugar de un nuevo mapa, se envían los ganadores.

Al terminar la partida, da la opción para empezar otra.

Para una mayor compresión bastaría con ver el bucle principal:
```python
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
```

### COMUNICACIÓN
```
*Se establece la comunicación*

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
```

### PARÁMETROS

`args: -p <port> -aw <AA_Weather-ip>:<AA_Weather-port> -ak <kafka-ip>:<kafka-port(29092)>` \
`extras: -ms <mapsize> -mp <maxplayers> -t <gametimeout>`

<br>

## AA_PLAYER

Código en [src/AA_Player.py](/src/AA_Player.py).

Cliente de un jugador.

Puede comunicarse con Registry o Engine.

No es necesario explicar cómo funciona, su comunicación es inversa a la de los dos servicios.
Y la interacción con el usuario puede verse en el apartado de [funcionamiento](#funcionamiento).

La interfaz gráfica se ha hecho utilizando curses, una librería de control de terminal que permite la construcción de aplicaciones de interfaz de usuario de texto (TUI).

Para una mayor compresión bastaría con ver el bucle principal:
```python
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
```

### PARÁMETROS

`args: -ar <AA_Registry-ip>:<AA_Registry-port> -ae <AA_Engine-ip>:<AA_Engine-port> -ak <kafka-ip>:<kafka-port(29092)>` \
`extras: -ms <mapsize>`

<br>

## AA_NPC

Código en [src/AA_NPC.py](/src/AA_NPC.py).

Cliente de un NPC.

Se comunica directamente con Engine, sin necesidad de autenticarse.
Para ello, envía a la cola un mensaje de su unión.
Espera a recibir un mapa de vuelta, al que pertenecerá.
Desde ese momento su partida comienza.

Cada cierto tiempo, consume el último mapa, y hace un movimiento.
El movimiento depende del tipo de NPC especificado:
- Normal: Los movimientos son aleatorios.
- Agresivo: Los movimientos son inteligentes.
  Detecta al jugador más cercano que puede matar y se dirige hacia él.
  Si ninguno es detectado, el movimiento es aleatorio.

Para una mayor compresión bastaría con ver el bucle principal:
```python
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
```

### PARÁMETROS

`args: -ak <kafka-ip>:<kafka-port(29092)>` \
`args extras: -t type> -s sleeptime>`

<br><br>
<!--<div style="page-break-after: always;"></div>-->

# DESPLIEGUE

El sistema se ha escrito en Python, un lenguaje interpretado, por lo que no es necesaria la compilación para el despliegue.
Si bien, hay que contar con todas las dependencias para poder ejecutar cada módulo.
Se ha especificado un entorno virtual en [src/Pipfile](/src/Pipfile) para instalar todas las dependencias en sus respectivas versiones.

El intérprete de Python debe estar instalado, con el gestor de paquetes pip, y el módulo pipenv.
```
# Install pipenv if you do not have it
pip install pipenv

# Install dependencies
pipenv install

# Start pipenv environment
pipenv shell

# Service/client help
python <service>.py -h

# Run service/client
python <service>.py <params...>
```

- Para cada servicio hay que especificar el puerto de escucha.
- Para cada cliente hay que especificar a qué puerto se conectará.
- Puede ser que un servicio sea además un cliente de otro servicio, como es el caso con el Engine.

Para desplegar Kafka, al ser un servicio de terceros, hay que cumplir con sus requisitos, que pueden variar según el sistema.
Para evitarlo se ha dockerizado, de tal forma que sólo necesitaríamos instalar docker y docker-compose.

De igual manera, podría haberse servido un docker para cada servicio, pero realmente el sistema no es difícil de desplegarlo como para necesitarlo.

El sistema ha sido probado en Windows y Linux.
Evidentemente, el jugador necesita una terminal que soporte curses.

Ejecución básica de cada módulo:

![despliegue](images/despliegue.png)

Todo ha sido desplegado en la misma máquina, un desaprovecho del poder distributivo que tiene el sistema.
Podemos probarlo de forma distribuida de las siguientes maneras:
- En una red privada:
  - Podríamos conectarnos desde distintos ordenadores en una LAN.
  - Podríamos simular lo anterior configurando una VPN (red privada virtual). Por ejemplo, con [Hamachi](https://vpn.net/).
- En Internet:
  - Con servidores, abriendo los puertos a Internet.
  - Podríamos simular el redireccionamiento del localhost a Internet. Por ejemplo, con [ngrok](https://ngrok.com/).

Habría que cambiar la dirección localhost por la IP (privada o pública respectivamente) de la máquina.

Si tuviéramos el *escenario físico mínimo para el despliegue de la práctica* según el enunciado de la práctica:
- PC1 [192.168.56.11]
```bash
#! Cambiar en kafka.docker-compose.yml "localhost" por "192.168.56.11"
$ sudo docker-compose -f kafka.docker-compose.yml up
$ python AA_Wetaher.py 1111
```
- PC2 [192.168.56.12]
```bash
$ python AA_Engine.py -p 3333 -aw "192.168.56.11:1111" -ak "192.168.56.11:29092"
$ python AA_Registry.py 2222
```
- PC3 [192.168.56.13]
```bash
$ python AA_Player.py -ar "192.168.56.12:2222" -ae "192.168.56.12:3333" -ak "192.168.56.11:29092"
$ python AA_NPC.py -ak "192.168.56.11:29092"
```

<br>

## CAÍDAS

Si un módulo se cae, no interrumpe bruscamente la ejecución de los demás. Se informará o se esperará a que el módulo sea nuevamente recuperado.

Pueden pasar las siguientes situaciones:
- Engine si Weather está inactivo: Se le informa y espera a que se recupere. \
![caida-engine-weather](images/despliegue-caida-engine-weather.png)
- Engine si Kafka está inactivo: Nunca será el caso. Falla antes el Player, el Engine no puede llegar al punto de crear partida.
- Engine si Kafka no responde: No se reciben nuevos movimientos. No interrumpe nada.

- Player si Registry está inactivo: Se le informa. \
![caida-player-registry](images/despliegue-caida-player-registry.png)
- Player si Engine está inactivo: Se le informa. \
![caida-player-engine](images/despliegue-caida-player-engine.png)

- Player o NPC si Engine no responde: No se reciben nuevos mapas, descartando los movimientos. No interrumpe nada.
- Player o NPC si kafka no está activo: No se reciben ni envían nuevos mapas. No interrumpe nada.

- Módulos correspondientes si la base de datos no existe: Al comienzo de cada uno se comprueba, si es así, es creada.

Cada módulo caído se recupera fácilmente ejecutándolo de nuevo.

En el caso del Engine, la partida perdida debe ser recuperada;
por ello, en cada movimiento, es guardada en la base de datos.
De tal forma que si, al crear partida, se comprueba que existe una en curso guardada, se recupera.

![caida-engine](images/despliegue-caida-engine1.png)

![caida-engine](images/despliegue-caida-engine2.png)

El resultado es un sistema resiliente, con manejo de fallos y fácilmente recuperable.

<br><br>
<!--<div style="page-break-after: always;"></div>-->

# COMENTARIOS

Ha sido una práctica muy larga, pero el tiempo ha sido aprovechado.
Si bien el lenguaje de programación ya lo manejaba muy bien, se ha enfocado mucho en la lógica de llevar a cabo la partida,
y sobre todo, cómo combinar la de cada módulo por medio de conexiones. Es satisfactorio ver la sinergia de todo.

A partir de una especificación, se ha creado un sistema recorriendo cada fase del proyecto. No ha sido tarea fácil, pero se asemeja a un desarrollo real.

La práctica motiva a terminarla con un buen acabado al tratarse de una aplicación divertida y funcional fuera del contexto de la asignatura.

## POSIBLES MEJORAS

Algunas mejoras que aún pueden realizarse son:
- Avisar en el cliente cuando el Engine o Kafka ha caído.
- Descartar movimiento cuando Kafka ha caído.
- Utilizar un lenguaje compilado para los módulos cliente, así se facilita su distribución.