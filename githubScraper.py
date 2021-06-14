#!/usr/bin/env python3

# =============================================================================================
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either version
# 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# This script must/should come together with a copy of the GNU General Public License. If not,
# access <http://www.gnu.org/licenses/> to find and read it.
#
# Author: Pedro Vernetti G.
# Name: 2dataset
#    Turns a text file into a shuffled sequence of its original words, all normalized and
#    casefolded IN-PLACE (so be careful, back things up...), also removing everything that
#    doesn't seem like a word in the strict sense (a sequence of letters, essentially)
#    If argument passed is " - ", it does the same thing to input received through a pipe
#    and prints the result to the standard output
#    (The frequency of each word remains the same through the process)
#
# #  In order to have this script working (if it is currently not), install its dependencies:
#    'pillow'
# =============================================================================================

import sys, re, requests, io, zipfile
from queue import SimpleQueue
from unicodedata import category as ucategory, normalize as unormalize
from codecs import lookup as codecLookup
from os import get_terminal_size as termSize, path
from random import shuffle
from pickle import dump as dumpPickle, load as loadPickle, PickleError

from bs4 import BeautifulSoup
from cchardet import detect as detectEncoding



def _userRepoZips( user, headers ):
    userURL = r'https://github.com/' + user
    try: page = requests.get(userURL, headers=headers, params={r'tab': r'repositories'})
    except: return []
    page = BeautifulSoup(page.content, r'lxml')
    userRepoURL = re.compile(r'^/' + re.escape(user) + r'/[\w._-]+$')
    repos = [a[r'href'] for a in page.find_all(r'a', {r'href': userRepoURL})]
    zipPath = r'/archive/refs/heads/master.zip'
    zips = [(r'https://github.com' + repoSubURL + zipPath) for repoSubURL in repos]
    return zips

def _userFollows( user, headers ):
    userURL = r'https://github.com/' + user
    try: page = requests.get(userURL, headers=headers, params={r'tab': r'following'})
    except: return []
    page = BeautifulSoup(page.content, r'lxml')
    userURL = re.compile(r'^/[a-z]([a-z-]*[a-z])$')
    users = []
    for follow in page.find_all(r'a', {r'href': userURL}):
        for user in follow.select(r'span[class*=Link--secondary]'):
            users += [user.get_text().strip()]
    return users



def _decoded( b ):
    try: actualEncoding = codecLookup(detectEncoding(b)[r'encoding'].casefold().strip()).name
    except: actualEncoding = r'utf-8'
    return b.decode(actualEncoding, r'ignore')

_unicodeJunk = {r'Cc', r'Cf', r'Co', r'Cs', r'Zl', r'Zp', r'Zs'}
_junkToSpace = dict.fromkeys(i for i in range(sys.maxunicode) if ((ucategory(chr(i)) in _unicodeJunk) and (i != 10)))
_junkToSpace = {cat:r' ' for cat in _junkToSpace}

def _normalized( s ):
    s = unormalize(r'NFC', s.translate(_junkToSpace).casefold())
    return (re.sub(r' +', r' ', s) + '\n\n')



previousStatsLineCount = 0

def _bulkStats( bulk, repo, users ):
    global previousStatsLineCount
    sys.stdout.write('\033[F\r' * previousStatsLineCount)
    sys.stdout.write(('\r' + (r' ' * termSize(0)[0]) + '\n') * previousStatsLineCount)
    sys.stdout.write('\033[F\r' * previousStatsLineCount)
    for ext in bulk:
        print((ext + ':\t'), len(bulk[ext]), r'characters of code (normalized)', flush=True)
    print('\nCurrently scraping:', repo, flush=True)
    print(r'Remaining users found for scraping:', len(users), flush=True)
    print('\x1B[1m[Press ctrl+C to finish]\x1B[0m', flush=True)
    previousStatsLineCount = len(bulk) + 4



headers = { r'User-Agent': r'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0',
            r'Referer': r'https://www.google.com/',
            r'Accept': r'text/html,application/xhtml+xml', }

codeFile = r'^.*\.([CcHh](\+\+|pp)?|[cejlrt]s|objc|[defmMPrRS]|p(y3?|[lm]|p|as|hp|s1)|s(h|ql|c(ala|ptd?)?)|'
codeFile += r'go|a(sp|d[bs])|c([bq]?l|lj[sc]?|ob(ra)?|py|yp)|li?sp|t(cl|bc)|j(ava|j)|(m|[eh]r)l|l?hs|'
codeFile += r'[rv]b|vhdl?|exs?|dart|applescript|f(or|90)|boo|[jt]sx|va(la|pi)|GAMBAS|(lit)?coffee|'
codeFile = re.compile(codeFile + r'fs([ix]|script)|jl|lua|m[dm]|w?asm|hx(ml)?|g(v|roov)?y|w(l|at)|b(at|tm)|cmd)$')

zipURL2Name = re.compile(r'^https?://github\.com/[a-z-]+/([^/]+)/archive/refs/heads/master\.zip')

users = sys.argv[1:]
knownUsers = set(users)
if (path.isfile(r'.knownGithubUsers')):
    with open(r'.knownGithubUsers', r'rb') as f:
        knownUsers |= loadPickle(f)
if (path.isfile(r'.unscrapedGithubUsers')):
    with open(r'.unscrapedGithubUsers', r'rb') as f:
        users += loadPickle(f)
bulk = dict()
while users:
    try:
        user = users.pop()
        _bulkStats(bulk, r'-', users)
        for anotherUser in _userFollows(user, headers):
            if (anotherUser not in knownUsers):
                knownUsers.add(anotherUser)
                users.append(anotherUser)
        for zipURL in _userRepoZips(user, headers):
            repoName = zipURL2Name.sub(r'\1', zipURL)
            _bulkStats(bulk, (user + r' -> ' + repoName), users)
            try:
                headers = requests.head(zipURL, headers=headers).headers
                if (int(headers[r'content-length']) > 4194304): continue # ignore downloads larger than 4MB
                repoZip = requests.get(zipURL, headers=headers)
                repoZip = zipfile.ZipFile(io.BytesIO(repoZip.content))
            except KeyboardInterrupt:
                raise KeyboardInterrupt
            except:
                continue
            repoTotals = dict()
            for file in repoZip.namelist():
                if (codeFile.match(file)):
                    ext = codeFile.search(file)[1].casefold().strip()
                    if (repoTotals.get(ext, 0) > 524288): continue # avoid getting ~512KB+ of samples from a single repo
                    code = _normalized(_decoded(repoZip.read(file)))
                    if (repoTotals.get(ext, None) is not None): repoTotals[ext] += len(code)
                    else: repoTotals[ext] = len(code)
                    if (bulk.get(ext, None)): bulk[ext] += code
                    else: bulk[ext] = code
                _bulkStats(bulk, (user + r' -> ' + repoName), users)
    except KeyboardInterrupt:
        break

users = list(set(users))
shuffle(users)
sys.stdout.write('\r' + (r' ' * 80) + '\nRemaining unscraped users: ')
for user in users: sys.stdout.write(user + r', ')
sys.stdout.write('\b\b  \n\n')
with open(r'.knownGithubUsers', r'wb') as f:
    dumpPickle(knownUsers, f, protocol=2)
with open(r'.unscrapedGithubUsers', r'wb') as f:
    dumpPickle(users, f, protocol=2)

for ext in bulk:
    try:
        open((r'githubCodeCorpora.' + ext), r'a').write(bulk[ext])
    except:
        print(r'Failed to write collected data to "githubCodeCorpora.' + ext + '"')
        continue
    loc = bulk[ext].count('\n')
    print(loc, r'LOC /', len(bulk[ext]), r'characters written to "' + (r'githubCodeCorpora.' + ext) + r'"')
