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
SERVER_PORT = 7890

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
    #for i, game in enumerate(games):
    #    if game['owned']:
    #        owned.append(game)
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
    print(('url: "%s"' % url))
    r = requests.get(url = url, params = dict()) 
    print(('status: %d' % r.status_code))
    if r.status_code != 200:
        return []
    return r.json() 

def run_app(games, players):
    print(('P: %d' % players))
    ownd = trim(games, players)
    print(('own: %d' % len(ownd)))
    selected = select_weighted(ownd)
    print(('selected: %d' % len(selected)))
    return selected

def MakeHandlerClassFromArgv():
    '''
    Class Factory to wrap variables in Custom Handler.
    '''
    class ScrambleServer(http.server.BaseHTTPRequestHandler, object):

        #
        # POST
        #
        def do_POST(self):
            #self.send_header('Content-Type', 'application/xml')
            self.send_response(200)
            self.end_headers()

            self.wfile.write('<?xml version="1.0" encoding="UTF-8"?><foo>hello</foo>'.encode('utf-8'))

        def hidden(self):
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length).decode('utf-8')
            user = None
            players = 3

            encoding = self.headers['Content-Type']
            print(('ENCODING: %s' % encoding))
            if encoding == 'application/x-www-form-urlencoded':
                print('It is twilio')
                requested = urllib.parse.parse_qs(body)
                try:
                    body = ''.join(requested['Body'])
                except KeyError:
                    body = ''

            print(('BODY: "%s"' % body))
            parts = body.split()
            print(('PARTS: %s' % parts))

            resp = MessagingResponse()
            if len(parts) < 1:
                msg = resp.message('FORMAT: "USER PLAYERS(OPTIONAL)')
                self.wfile.write(str(resp).encode('utf-8'))
                return
            if len(parts) >= 1:
                user = str(parts[0])
            if len(parts) >= 2:
                try:
                    players = int(parts[1])
                except ValueError:
                    msg = resp.message('BAD NUMBER FOR PLAYERS: "USER PLAYERS<INT>(OPTIONAL)')
                    self.wfile.write(str(resp).encode('utf-8'))
                    return

            selections = run_app(fetch_games(user), players)
            if len(selections) < 1:
                msg = resp.message('NO GAMES')
            else:
                for entry in selections:
                    name, link = entry.split(',')
                    msg = resp.message(name)
                    #msg.media(link)
            print(('RESP: %s' % resp))
            self.wfile.write(str(resp).encode('utf-8'))

    # return the whole inline class
    return ScrambleServer

def runServer(server_class=http.server.HTTPServer,
        handler_class=http.server.BaseHTTPRequestHandler,
        port=SERVER_PORT):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def main():
    port = SERVER_PORT
    try:
        port = int(sys.argv[2])
    except IndexError:
        pass
    HandlerClass = MakeHandlerClassFromArgv()
    runServer(handler_class=HandlerClass, port=port)

if __name__ == '__main__':
    main()
