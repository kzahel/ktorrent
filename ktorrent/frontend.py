import tornado.web
import logging
import urllib
from connection import Connection
from tornado.websocket import WebSocketHandler
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
from tornado.ioloop import IOLoop
ioloop = IOLoop.instance()
from proxytorrent import ProxyTorrent
from tracker import Tracker

class BaseHandler(tornado.web.RequestHandler):
    def writeout(self, args):
        if 'callback' in self.request.arguments:
            self.set_header('Content-Type','text/javascript')
            try:
                self.write( '%s(%s)' % (self.get_argument('callback'), json.dumps(args, indent=2)) )
            except:
                import pdb; pdb.set_trace()
        else:
            self.write(args)


class IndexHandler(BaseHandler):
    def get(self):
        pass###
import binascii
class StatusHandler(BaseHandler):
    def get(self):
        attrs = {}

        attrs.update( dict( 
                clients = [ (c, dict( (binascii.hexlify(h), t) for h,t in c.torrents.iteritems() )) for c in Client.instances ],
                trackers = Tracker.instances,
                connections = Connection.instances,
                torrents = dict( (binascii.hexlify(h), {'torrent':t, 'conns':t.connections,'attrs':t._attributes}) for h,t in Torrent.instances.iteritems() ),
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
        


import collections
from tornado.iostream import _merge_prefix

class APIHandler(BaseHandler):
    def get(self): return self.post();

    def post(self):
        self.write( dict( foo = 23 ) )


class APIUploadHandler(BaseHandler):
    def get(self): pass


class APIUploadWebSocketHandler(WebSocketHandler):
  msgtypes = {'c':'create-session',
              'p':'payload'}
  msgencodings = {'j': 'json',
                  'r': 'raw'}


  def open(self):
      """ web socket used for sending file data for upload.
      q: request based or push based?

      seems to make sense to have this server make requests for the
      pieces using a torrent-like protocol. only metadata does not
      exist yet.

      browser client initiates websocket with array of files and their
      lengths application then makes requests for pieces. browser
      client keeps initiating connection with the session id and
      responding to upload requests.

      q: can filereader seek? or are reads sequential? likely only
      sequential, in which case request-response does not make much
      sense. better to sequentially write data as it comes in.

      hash as the data comes in, before it is written to disk (speedier)

      it may not be possible to do that easily because torrent
      metadata files may have to be alphabetically ordered

      need to keep a map of paths in the torrent to paths on disk --
      actually, we never get the local disk path. that's the whole
      problem. everything has to be duplicated. If only we were able
      to find the file on disk. Perhaps in some cases, we will be able
      to... does the OS provide a nice API for searching for a file?
      windows, osx may...

      seeding may want to be very smart and detect moved files. if
      file is the right size and one contained piece has a valid hash,
      that seems good enough.
      
      --- a while ago had an idea of a torrent metadata type that
          stores a bunch of torrents, like a whole season or a show or
          something



      """

      self.read_buf = collections.deque()
      self.handshaking = True
      self.is_closed = False
      if options.verbose > 10:
          logging.info( "WebSocket opened" )

      self.stream_adapter = WebSocketIOStreamAdapter(self)

      # ask for a session id
      # packets send like {sessid, fileno, offset, len}

  def on_message(self, message):
      if options.verbose > 10:
          logging.info('got ws message %s' % [ message ])
      self.read_buf.append(message)

      if self.handshaking:
          if options.verbose > 10:
              logging.info('conn adopt')
          conn = Connection.adopt_websocket(self)
          self.handshaking = False
      else:
          if options.verbose > 10:
              logging.info('try read callback')
          self.stream_adapter.try_read_callback()
          # conn.new_websocket_message( message )

  def get_read_buf_sz(self):
      val = sum(map(len, self.read_buf))
      if options.verbose > 10:
          logging.info('check read buf sz %s, %s' % (val, self.read_buf))
      return val

  def on_close(self):
      self.is_closed = True
      self.stream_adapter.run_close_callback()

def request_logger(handler):
    if options.verbose > 1:
        logging.info('finished handler %s' % handler)

from tornado.util import bytes_type, b

class WebSocketIOStreamAdapter(object):
    def __init__(self, handler):
        self._read_callback = None
        self.handler = handler
        self._close_callback = None

    def run_close_callback(self):
        if self._close_callback: self._close_callback()

    def set_close_callback(self, callback):
        self._close_callback = callback

    def read_bytes(self, num, callback):
        if options.verbose > 10:
            logging.info('%s read bytes %s' % (self, num))
        assert not self._read_callback, 'already reading'
        self._read_callback = callback
        self._read_callback_num = num
        self.try_read_callback()

    def consume_from_buffer(self, num):
        _merge_prefix(self.handler.read_buf, num)
        data = self.handler.read_buf.popleft()
        return data

    def try_read_callback(self):
        if options.verbose > 10:
            logging.info('try read callback')
        if self._read_callback:
            if self.handler.get_read_buf_sz() >= self._read_callback_num:
                data = self.consume_from_buffer(self._read_callback_num)
                if options.verbose > 10:
                    logging.info('consumed data %s' % [data])
                callback = self._read_callback
                self._read_callback = None
                self._read_callback_num = None
                callback( data )

    def write(self, msg, callback=None):
        #data = bytearray(msg)
        #logging.info('writing back msg %s' % [data])
        self.handler.write_message(msg, binary=True) # make sure it's binary...
        # callback immediately
        if callback:
            ioloop.add_callback( callback )

    def closed(self):
        return self.handler.is_closed

    def writing(self):
        return False
