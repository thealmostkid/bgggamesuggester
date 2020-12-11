#!/usr/bin/env python 
import http.server
import heapq
import json
import random
import sys
import urllib.parse

import requests

from twilio.twiml.messaging_response import MessagingResponse

TOTAL_SELECTED = 5
DESCRIPTION = 'pick board games to play from your boardgamegeek collection'
HELP = 'FORMAT: "BGGUSER NUMPLAYERS(OPTIONAL) IMAGES(OPTIONAL)"'
HELP_CMD = 'usage'
IMAGES_CMD = 'images'

def game_weight(game, games):
    score = 0
    for g in games:
        # favor higher ranked games
        if game['rank'] < g['rank']:
            score += 1
        # favor less played games
        if game['numPlays'] < g['numPlays']:
            score += 1
    return score

def is_playable(game, players):
    return game['owned'] and game['minPlayers'] <= players and game['maxPlayers'] >= players

def trim(games, players):
    ownd = [ game for game in games if is_playable(game, players) ]
    expansions = list()
    for game in ownd:
        if 'expansions' in game:
            for expansion in game['expansions']:
                if is_playable(expansion, players):
                    expansion['rank'] = game['rank']
                    expansions.append(expansion)

    ownd.extend(expansions)
    return ownd

def select_weighted(games):
    results = []
    if len(games) < TOTAL_SELECTED:
        for game in games:
            results.append('%s,%s' % (game['name'], game['thumbnail']))
    else:
        weighted = list()
        for i, game in enumerate(games):
            for _ in range(game_weight(game, games)):
                weighted.append(i)
        selected = dict()
        while len(selected) < TOTAL_SELECTED:
            selected[random.choice(weighted)] = True
        for index in list(selected.keys()):
            game = games[index]
            results.append('%s,%s' % (game['name'], game['thumbnail']))
    return results

def select_random_sorted(games):
    selected = dict()
    while len(selected) < TOTAL_SELECTED:
        game = random.choice(games)
        selected[game['name']] = game
    h = []
    for game in list(selected.values()):
        heapq.heappush(h, (-1 * game_weight(game, list(selected.values())), game))

    results = []
    index = 1
    while True:
        try:
            (_, game) = heapq.heappop(h)
            results.append('%s,%s' % (game['name'], game['thumbnail']))
            index += 1
        except IndexError:
            break
    return results

def read_games(user):
    games = dict()
    try:
        with open('%s.json' % user) as f:
            games = json.load(f)
    except IOError:
        games = dict()
    return games

def fetch_games(user):
    url = 'https://bgg-json.azurewebsites.net/collection/%s?grouped=true' % user
    r = requests.get(url = url, params = dict()) 
    print(('BGG USER: %s STATUS: %d' % (user, r.status_code)))
    if r.status_code == 500:
        # if the collection is too big "grouped" fails
        url = 'https://bgg-json.azurewebsites.net/collection/%s' % user
        r = requests.get(url = url, params = dict()) 

    if r.status_code == 404:
        raise KeyError('unknown user %s' % user)
    if r.status_code != 200:
        return []
    body = r.json() 
    if 'message' in body:
        raise ValueError
    return body

def run_app(games, players):
    print(('FOUND: %d' % len(games)))
    ownd = trim(games, players)
    selected = select_weighted(ownd)
    return selected

def MakeHandlerClassFromArgv():
    '''
    Class Factory to wrap variables in Custom Handler.
    '''
    class BGGGameSuggesterServer(http.server.BaseHTTPRequestHandler, object):
        #
        # GET
        #
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()

            content = '''
<html>
<body>
<form action="/" method="post">
<label for="user">BGG User Name:</label>
<input type="text" id="user" name="user">
<br>
<label for="players">Number of Players:</label>
<input type="text" id="players" name="players">
<br>
<input type="hidden" id="images" name="images" value="images">
<input type="submit" value="Submit">
</form>
</body>
</html>
'''
            self.wfile.write(str(content).encode('utf-8'))

        #
        # POST
        #
        def do_POST(self):
            self.send_response(200)
            self.send_header('Content-type','application/xml')
            self.end_headers()

            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length).decode('utf-8')
            user = None
            players = 3

            print(('BODY: %s' % body))

            encoding = self.headers['Content-Type']
            if encoding == 'application/x-www-form-urlencoded':
                requested = urllib.parse.parse_qs(body)
                try:
                    body = ''.join(requested['Body'])
                except KeyError:
                    body = ''
                    if 'user' in requested:
                        body = ''.join(requested['user'])
                        if 'players' in requested:
                            body = ' '.join(body, ''.join(requsted['players']))
                        if 'images' in requested:
                            body = ' '.join(body, 'images')

            parts = body.split()

            resp = MessagingResponse()
            images = False
            if len(parts) < 1:
                resp.message(DESCRIPTION)
                resp.message(HELP)
                self.wfile.write(str(resp).encode('utf-8'))
                return
            if len(parts) >= 1:
                user = str(parts[0])
                if user.lower() == HELP_CMD.lower():
                    resp.message(DESCRIPTION)
                    resp.message(HELP)
                    self.wfile.write(str(resp).encode('utf-8'))
                    return
            if len(parts) >= 2:
                for cmd in parts[1:]:
                    if cmd.lower() == IMAGES_CMD.lower():
                        images = True
                    else:
                        try:
                            players = int(cmd)
                        except ValueError:
                            resp.message('BAD NUMBER FOR PLAYERS: "USER PLAYERS<INT>(OPTIONAL)')
                            resp.message(HELP)
                            self.wfile.write(str(resp).encode('utf-8'))
                            return

            selections = run_app(fetch_games(user), players)
            if len(selections) < 1:
                resp.message("No games with status \"owned\" found in %s's collection" % user)
                resp.message(DESCRIPTION)
                resp.message(HELP)
            else:
                for entry in selections:
                    name, link = entry.split(',')
                    if images:
                        resp.message().media(link)
                    else:
                        resp.message(name)
            self.wfile.write(str(resp).encode('utf-8'))

    # return the whole inline class
    return BGGGameSuggesterServer

def runServer(port, server_class=http.server.HTTPServer,
        handler_class=http.server.BaseHTTPRequestHandler
        ):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def main():
    port = 7890
    try:
        port = int(sys.argv[2])
    except IndexError:
        pass
    HandlerClass = MakeHandlerClassFromArgv()
    runServer(port, handler_class=HandlerClass)

if __name__ == '__main__':
    main()
