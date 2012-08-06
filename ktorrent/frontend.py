import tornado.web
import logging
import urllib
from connection import Connection
from torrent import Torrent
from client import Client
from session import Session
from peer import Peer
import json
from cgi import escape
import signal
import pdb
import sys
from tornado.options import options

from proxytorrent import ProxyTorrent

class BaseHandler(tornado.web.RequestHandler):
    def writeout(self, args):
        if 'callback' in self.request.arguments:
            self.set_header('Content-Type','text/javascript')
            self.write( '%s(%s)' % (self.get_argument('callback'), json.dumps(args, indent=2)) )
        else:
            self.write(args)


class IndexHandler(BaseHandler):
    def get(self):
        pass###

class StatusHandler(BaseHandler):
    def get(self):
        attrs = {}

        attrs.update( dict( 
                clients = [ (c, c.torrents) for c in Client.instances ],
                connections = Connection.instances,
                torrents = dict( (h, {'torrent':t, 'conns':t.connections,'attrs':t._attributes}) for h,t in Torrent.instances.iteritems() ),
                peers = Peer.instances.values()
                            ) )
        def custom(obj):
            return escape(str(obj))

        self.write('<html><body><pre>')
        self.write( json.dumps( attrs, indent=2, sort_keys = True, default=custom ) )
#        options['colorize'].set(colorval)
        self.write('</pre><script src="/static/repl.js"></script>')
        self.write('<p><input style="width:100%" name="input" autocomplete="off" type="text" onkeydown="keydown(this, event);" /></p><div id="output" style="border:1px solid black; margin: 1em"></div>')
        command = """     Connection.initiate(host,port,startuphash) """
        self.write('<pre>%s</pre>' % command)
        self.write('</body></html>')

    #@require_basic_auth
    def post(self):
        qs = self.get_argument('qs',None)
        #colorval = options['colorize'].value()
        #options['colorize'].set(False)
        if qs:
            try:
                try:
                    result = eval(qs)
                    try:
                        return self.write(result.__repr__())
                    except:
                        return self.write(str(result))
                except SyntaxError:
                    exec(qs)
                    self.write('')
            except Exception, e:
                import traceback
                self.write( traceback.format_exc() )
                #return self.write(str(e))
        #options['colorize'].set(colorval)

class VersionHandler(BaseHandler):
    def get(self):
        args = {'name':'ktorrent','version':'0.1'}
        
        self.writeout(args)

def decode_func_args(s):
    # turns a string of the form 'btapp/add/torrent(["http://featuredcontent.utorrent.com/torrents/CountingCrows-BitTorrent.torrent"])/'
    # into { 'path': 'btapp/add/torrent', 'args': [...] }
    p = s[:s.index('(')]
    a = s[ s.index('(')+1 : len(s)-2 ]
    return { 'path': p, 'args': json.loads(a) }

class BtappHandler(BaseHandler):
    def get(self):
        if 'pairing' in self.request.arguments:
            key = self.get_argument('pairing')
            # validate pairing key

            if 'type' in self.request.arguments:
                if 'session' in self.request.arguments:
                    session = Session.get(self.get_argument('session'))
                    if session:
                        if self.get_argument('type') == 'update':
                            self.writeout( session.get_update() )
                        elif self.get_argument('type') == 'function':
                            queries = self.get_argument('queries')
                            qargs = json.loads(queries)
                            args = [urllib.unquote(arg) for arg in qargs]
                            decoded = [decode_func_args(a) for a in args]
                            for fnargs in decoded:
                                self.writeout( session.handle_function(fnargs) )
                                return
                        else:
                            self.writeout( { 'no':'huh' } )
                        # validate session
                        #self.writeout( [ {'add': {'btapp':{'torrent':{'aotheu':{'hello':23}}}} } ] )
                    else:
                        self.set_status(404)
                else:
                    #logging.info('no session id in args -- %s, %s' % (self.request.uri, self.request.arguments))
                    session = Session.create(Client.instances[0])
                    self.writeout( {'session':session.id} )
            else:
                self.writeout( { 'hey':'whatup' } )
        else:
            self.set_status(403)

class PairHandler(BaseHandler):
    def get(self):
        key = '0'*40
        self.write('%s("%s")' % (self.get_argument('callback'), key))

class PingHandler(BaseHandler):
    image = [66, 77, 66, 0, 0, 0, 0, 0, 0, 0, 62, 0, 0, 0, 40, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0,\
                 0, 1, 0, 1, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,\
                 0, 0, 0, 0, 0, 0, 255, 255, 255, 0, 128, 0, 0, 0]


    def get(self):
        self.set_header('Content-Type','image/x-ms-bmp')
        self.write( ''.join(map(chr,PingHandler.image)) )


class ProxyHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        client = Client.instances[0]
        sid = self.get_argument('sid')
        file = int(self.get_argument('file'))

        torrent = None
        for hash, t in client.torrents.iteritems():
            if t.sid == sid:
                torrent = t
                break

        if torrent:
            file = torrent.get_file(file)
            ProxyTorrent.register( file, self )
            # self.write('found torrent %s' % torrent)
        else:
            self.write('torrent not found')
        



class APIHandler(BaseHandler):
    def get(self): return self.post();

    def post(self):
        self.write( dict( foo = 23 ) )

def request_logger(handler):
    if options.verbose > 1:
        logging.info('finished handler %s' % handler)
