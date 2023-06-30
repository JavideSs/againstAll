/*
index.html?addr=https://<API_Engine-ip>:<API_Engine-port>

index.html?addr=https://localhost:4444
*/

//==================================================

const search_params = new URLSearchParams(window.location.search);

if (search_params.has("addr")){
    var addr = search_params.get("addr").toString();

    window.onload = main;

    var interval_id = setInterval(main, 1000);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden)
            clearInterval(interval_id);
        else
            interval_id = setInterval(main, 1000);
    });
}
else
    alert("Indica la dirección!");

//==================================================

function main(){
    /*
    fetch(addr+"/gameplay/game")
    .then(res => res.json())
    .then(map => drawMap(map))

    fetch(addr+"/gameplay/players")
    .then(res => res.json())
    .then(players => drawLeaderboard(players))
    */

    fetch(addr+"/gameplay/status")
    .then(res => res.json())
    .then(status => {
        if (status.startsWith(":)")){
            fetch(addr+"/gameplay/game")
            .then(res => res.json())
            .then(map => drawMap(map))

            fetch(addr+"/gameplay/players")
            .then(res => res.json())
            .then(players => drawLeaderboard(players))
        }
        else{
            alert(status);
        }
    })
    .catch(error => alert(error.message));
}

//==================================================

const html_board = document.getElementById("board");

const sectorcolors = [
    ["100,100,200","50,50,150"],
    ["100,200,200","100,150,150"],
    ["200,100,200","150,100,150"],
    ["200,200,100","150,150,100"]
];

function drawMap(map){
    const sectorsize = map.length/2;

    //Remove last map
    while (html_board.hasChildNodes()) {
        html_board.removeChild(html_board.lastChild);
    }

    //Add new map
    for (const [i,row] of map.entries()){
        for (const [j,value] of row.entries()){
            const sector = i<sectorsize && j<sectorsize ? 0 :
                i<sectorsize && j>=sectorsize ? 1 :
                j<sectorsize ? 2 : 3;
            const light = (i+j)%2;

            var div = document.createElement("div");
            div.className = "grid";
            div.style.cssText += `
                background-color: rgb(${sectorcolors[sector][light]});
            `;

            if (value instanceof Array){ //Is player
                if (value[0].startsWith("NPC")) //Is NPC
                    div.textContent = "🤖";
                else
                    div.textContent = value[0][0].toUpperCase();

                div.style.cssText += `
                    color: white;
                    font-size: 30px;
                `;

                div.addEventListener("click", (event) => {
                    const popup = document.createElement("div");
                    popup.className = "popup";
                    popup.textContent = value.join(", ");

                    const boundingRect = event.target.getBoundingClientRect();
                    popup.style.cssText += `
                        top: ${boundingRect.top+5}px;
                        left: ${boundingRect.left+5}px;
                    `;
                    document.body.appendChild(popup);

                    setTimeout(() => {
                        document.body.removeChild(popup);
                    }, 3000);
                });
            }
            else
                switch (value){
                    case "M":
                        div.textContent = "💣"; break;
                    case "A":
                        div.textContent = "🍏"; break;
                    default: break;
                }

            html_board.appendChild(div);
        }
    }
}

//==================================================

const html_leaderboard = document.getElementById("leaderboard");

function drawLeaderboard(players){
    players.sort((a, b) => b.level - a.level);

    //Remove last leaderboard
    while (html_leaderboard.rows.length){
        html_leaderboard.deleteRow(-1);
    }

    //Add new leaderboard
    for (const [i,player] of players.entries()){
        var tr = html_leaderboard.insertRow(-1);

        var td_index = tr.insertCell(0);
        td_index.innerHTML = i+1+".";
        var td_alias = tr.insertCell(1);
        td_alias.innerHTML = !player.alias.startsWith("NPC") ?
            player.alias :
            "NPC en (" + player.pos + ")";

        if (player.level == -1){ //Dead
            let style = `
                color: gray;
                opacity: 0.5;
                text-align: center;
            `;
            tr.style.cssText += style;
            td_alias.style.cssText += style + `
                text-decoration: line-through;
            `;
            td_alias.colSpan = 2;
        }
        else{
            let td_level = tr.insertCell(2);
            td_level.innerHTML = player.level;
        }
    }
}