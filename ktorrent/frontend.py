import tornado.web
import logging
import urllib
from connection import Connection
from tornado.websocket import WebSocketHandler
from tornado import iostream
from torrent import Torrent
from client import Client
from session import Session
from peer import Peer
import json
from cgi import escape
import signal
import socket
import base64
import pdb
import sys
import binascii
from tornado.options import options
from tornado.ioloop import IOLoop
from proxytorrent import ProxyTorrent
from tracker import Tracker
from util import hexlify

class BaseHandler(tornado.web.RequestHandler):
    def __init__(self, *args, **kwargs):
        self.ioloop = IOLoop.instance()
        tornado.web.RequestHandler.__init__(self, *args,**kwargs)
        
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
        logging.info('unhandled route')

from apidefs import TorrentDef

class GUIHandler(BaseHandler):
    def get(self):
        client = Client.instance()

        if 'list' in self.request.arguments:
            torrents = []
            for h,t in client.torrents.iteritems():
                hash = hexlify(h)
                r = [None for _ in range(len(TorrentDef.coldefs))]
                r[TorrentDef.coldefnames['hash']] = hash

                t_attrs = t.get_attributes()

                for key in t_attrs:
                    if key in TorrentDef.coldefnames:
                        r[TorrentDef.coldefnames[key]] = t_attrs[key]
                torrents.append(r)
            self.writeout(torrents)
        elif 'action' in self.request.arguments:

            action = self.get_argument('action')
            if action == 'getsettings':
                rows = []
                rows.append(['bind_port', 0, options.port, {}])
                ret = {'settings':rows}
                self.writeout(ret)



class StatusHandler(BaseHandler):
    def get(self):
        attrs = {}


        if 'proxy' in self.request.arguments:

            attrs.update( dict( 
                    incoming_proxy_ws = WebSocketIncomingProxyHandler.instances,
                    incoming_tcp_listener = IncomingConnectionListenProxy.byport,
                    udp_proxy = [[p, p.socks] for p in WebSocketUDPProxyHandler.instances],
                    ws_proxy = WebSocketProxyHandler.instances,
                    ))
        else:
            attrs.update( dict( 
                    clients = [ (c, dict( (hexlify(h), t) for h,t in c.torrents.iteritems() )) for c in Client.instances ],
                    trackers = Tracker.instances,
                    ws_prot = WebSocketProtocolHandler.instances,
                    connections = Connection.instances,
                    torrents = dict( (binascii.hexlify(h), {'torrent':t, 'conns':t.connections,'attrs':t._attributes}) for h,t in Torrent.instances.iteritems() ),
                    peers = [dict( (str(k),v) for k,v in Peer.instances_compact.items() ), dict( (hexlify(k),v) for k,v in Peer.instances_peerid.items() )]
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
        torrent = None
        file = int(self.get_argument('file','0'))
        if 'hash' in self.request.arguments:
            torrent_hash = binascii.unhexlify(self.get_argument('hash'))
            if torrent_hash in client.torrents:
                torrent = client.torrents[torrent_hash]
        else:
            sid = self.get_argument('sid')
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
import time
from tornado.iostream import _merge_prefix

class APIHandler(BaseHandler):
    def get(self): return self.post();

    def post(self):
        self.write( dict( foo = 23 ) )

from tornado import gen

class BaseWebSocketHandler(WebSocketHandler):
    def __init__(self, *args, **kwargs):
        self.ioloop = IOLoop.instance()
        WebSocketHandler.__init__(self, *args,**kwargs)

    def do_close(self, reason=None):
        if not self.request.connection.stream.closed():
            logging.info('%s manually close, %s' % (self, reason))
            self.close(reason)
        else:
            logging.info('%s try close (already closed), %s' % (self, reason))


class WebSocketProxyHandler(BaseWebSocketHandler):
    instances = []
    connect_timeout = 10

    def open(self):
        self.instances.append(self)

        self.username = self.get_argument('username','notsent')
        self.fd = self.request.connection.stream.socket.fileno()
        self._read_buffer = collections.deque()
        self.handshaking = True
        self.is_closed = False
        self._nobinary = 'flash' in self.request.arguments

        parts = self.get_argument('target').split(':')
        self.target_host = str(parts[0])
        self.target_port = int(parts[1])
        logging.info('%s ws proxy open' % self)        

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

        self.target_stream = iostream.IOStream(s, io_loop=self.ioloop)
        self.target_stream._always_callback = True
        self.target_stream._buffer_grown_callback = self.target_has_new_data
        self.target_stream.set_close_callback( self.target_stream_closed )
        if 'timeout' in self.request.arguments:
            timeout = int(self.get_argument('timeout')) / 1000.0
        else:
            timeout = WebSocketProxyHandler.connect_timeout
        self.connect_timeout = self.ioloop.add_timeout( time.time() + timeout, self.check_target_connected )
        self.addr = (self.target_host, self.target_port)
        #self.addr = ('110.174.252.130', 20862)
        #self.addr = ('84.215.241.100',53566 )
        #logging.info('connecting to target %s, %s' % self.addr)
        self.target_stream.connect(self.addr, callback=self.connected_to_target )

    def __repr__(self):
        return "<WS_BT:%s,%s->%s:%s>" % (self.username, self.fd, self.target_host, self.target_port)

    def target_stream_closed(self):
        if self.ws_connection and not self.ws_connection.stream.closed():
            self.do_close("endpoint closed")

    def target_has_new_data(self):
        #logging.warn('target has new data! %s' % self.target_stream._read_buffer)
        #logging.warn('target has new data! %s' % len(self.target_stream._read_buffer))
        while len(self.target_stream._read_buffer) > 0:
            chunk = self.target_stream._read_buffer.popleft()
            #logging.info('writing data to websocket %s' % len(chunk) )
            if len(self.request.connection.stream._write_buffer) > 1:
                logging.error('%s have data in write buffer! slow down read!' % self)
                self.target_stream._clear_io_state()
                #ioloop.add_timeout( time.time() + 1, ...
                assert( not self.target_stream._write_callback )
                self.request.connection.stream._write_callback = self.resume_target_read

            if self._nobinary:
                self.write_message( base64.b64encode(chunk) )
            else:
                self.write_message( chunk, binary=True )

    def resume_target_read(self):
        logging.info('%s resume read!' % self)
        self.target_stream._add_io_state(self.ioloop.READ)
        
    def check_target_connected(self):
        if self.target_stream._connecting:
            #logging.error('timeout connecting!')
            self.do_close("endpoint timeout")

    def connected_to_target(self):
        self.ioloop.remove_timeout( self.connect_timeout )
        if self.target_stream.error:
            self.do_close("error connecting")
            return
            #import pdb; pdb.set_trace()
        #logging.info('connected to target!')
        #self.target_stream._add_io_state(ioloop.READ)
        self.try_flush()

    def on_message(self, msg):
        if (self._nobinary or type(msg) == type(u'')):
            msg = base64.b64decode(msg)
        self.try_flush()
        #logging.info('ws proxy message %s' % [msg])
        if not self.target_stream._connecting and not self.target_stream.closed():
            #logging.info('writing data to target_stream %s, %s' % (len(msg),time.time() ))
            if len(self.target_stream._write_buffer) > 0:
                logging.error('target stream has write buffer!')
            self.target_stream.write(msg)
        else:
            self._read_buffer.append(msg)

    def try_flush(self):
        if self.target_stream._connecting:
            return
        while len(self._read_buffer) > 0:
            chunk = self._read_buffer.popleft()
            #logging.info('writing data to target_stream %s' % [chunk] )
            #logging.info('writing data to target_stream %s, %s' % (len(chunk),time.time() ))
            if not self.target_stream.closed():
                self.target_stream.write( chunk )
            #self.target_stream._add_io_state(ioloop.READ)

    def on_close(self):
        self.instances.remove(self)

        self._read_buffer = None
        logging.info('%s on close' % self)
        if not self.target_stream.closed():
            self.target_stream.close()


class WebSocketProtocolHandler(BaseWebSocketHandler):
    instances = []

    def open(self):
        self.instances.append(self)
        self.read_buf = collections.deque()
        self.handshaking = True
        self.is_closed = False
        self.flash = 'flash' in self.request.arguments
        if options.verbose > 10:
            logging.info( "WebSocket opened" )
            self.stream_adapter = WebSocketIOStreamAdapter(self, flash=self.flash)

    def on_message(self, message):
        if options.verbose > 10:
            logging.info('got ws message %s' % [ message ])
        if self.flash:
            self.read_buf.append(base64.b64decode(message))
        else:
            self.read_buf.append(message)

        if self.handshaking:
            if options.verbose > 10:
                logging.info('conn adopt')
            conn = Connection.adopt_websocket(self.stream_adapter)
            self.handshaking = False
        else:
            if options.verbose > 10:
                logging.info('try read callback')
            self.stream_adapter.try_read_callback()

    def get_read_buf_sz(self):
        val = sum(map(len, self.read_buf))
        if options.verbose > 10:
            logging.info('check read buf sz %s, %s' % (val, self.read_buf))
        return val

    def on_close(self):
        self.instances.remove(self)
        if options.verbose > 10:
            logging.info( "WebSocket closed" )
        self.is_closed = True
        self.stream_adapter.run_close_callback()


def request_logger(handler):
    if options.verbose > 1:
        logging.info('finished handler %s' % handler)

from tornado.util import bytes_type, b

class WebSocketIOStreamAdapter(object):
    """ pretends to be iostream instance used by connection.py """

    def __init__(self, handler, flash=False):
        self._read_callback = None
        self.handler = handler
        self.flash = flash
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
        if self.flash:
            self.handler.write_message(base64.b64encode(msg), binary=False) # make sure it's binary...
        else:
            self.handler.write_message(msg, binary=True) # make sure it's binary...
        # callback immediately
        if callback:
            self.ioloop.add_callback( callback )

    def closed(self):
        return self.handler.is_closed

    def writing(self):
        return False

import tornado.netutil

def dassert(tval, msg=None):
    if not tval:
        logging.error('assertion fail, %s' % msg)
        import pdb; pdb.set_trace()
        

class IncomingConnectionListenProxy(tornado.netutil.TCPServer):
    start_port = 32000
    end_port = 65000
    byport = {}
    bytoken = {}

    def __init__(self, port, io_loop=None):
        self._check_ws_incoming = None
        self.ioloop = io_loop
        self.incoming_queue = []
        self.websocket_handler = None
        self.error = False
        self.port = port
        self._closing = False
        tornado.httpserver.TCPServer.__init__(self, io_loop=io_loop)
        try:
            self.listen(self.port)
            logging.info('%s listening' % self)
        except:
            self.error = True

        self.token = sha1(str(random.random())).hexdigest()[:8]
        self.byport[self.port] = self
        self.bytoken[self.token] = self

    def __repr__(self):
        return "<ListTCPSvr(%s):%s>" % (self.websocket_handler, self.port)

    def notify_websocket_handler_closed(self, wshandler):
        # websocket holding onto this listening connection died... if
        # no new connection claims us in a bit, then close it down and
        # shut down the incoming queue.

        if self._closing:
            return

        logging.warn('notify incoming ws closed, install timeout')
        if self._check_ws_incoming:
            self.ioloop.remove_timeout( self._check_ws_incoming )
        self._check_ws_incoming = self.ioloop.add_timeout( time.time() + 5, self.check_had_no_ws_handler )

        #dassert( wshandler == self.websocket_handler )
        if self.websocket_handler:
            self.websocket_handler = None

    def handle_stream(self, stream, address):
        logging.info("%s handle stream from %s" % (self, [address]))
        self.incoming_queue.append( (stream, address) )
        self.try_handoff()

    def notify_incoming_closed(self):
        return

    def check_had_no_ws_handler(self):
        self._closing = True
        logging.warn("%s CLOSE -- no connected ws in 5 sec" % self)
        del self.byport[self.port]
        del self.bytoken[self.token]
        self.stop()
        for item in self.incoming_queue:
            stream = item[0]
            if not stream.closed():
                stream.close()

            
    def try_handoff(self):        
        if self.websocket_handler and self.incoming_queue:
            logging.info('%s HANDOFF -- had incoming conn!' % self)
            incoming_conn = self.incoming_queue.pop(0)
            self.websocket_handler.handle_incoming_stream( *incoming_conn )
            self.websocket_handler = None # dont need to use this guy anymore
        #logging.info("NEW INCOMING STREAM %s" % [stream, address])
        # pipe this stream into the websocket (handler)
        #self.handler.handle_incoming_stream(stream, address)
        #self.check_timeout = ioloop.add_timeout( time.time() + 10, self.check_close )

    def add_websocket_handler(self, handler):
        if self._check_ws_incoming:
            self.ioloop.remove_timeout( self._check_ws_incoming )
        self._check_ws_incoming = None


        if self.websocket_handler:
            logging.error('%s already have websocket handler!' % self)
            # XXX --- what to do?
        self.websocket_handler = handler
        self.try_handoff()

from hashlib import sha1
import random
class WebSocketIncomingProxyHandler(BaseWebSocketHandler):
    instances = []
    """ act as a listening socket for me """

    def open(self):
        logging.info('incoming proxy open')
        self.instances.append(self)

        self.listen_port = None
        self.listen_proxy = None
        self._should_have_listen_proxy = True
        self.incoming_stream = None

        self.username = self.get_argument('username','notsent')
        self.version = self.get_argument('v','notsent')

        if 'token' in self.request.arguments:
            token = self.get_argument('token')
            if token in IncomingConnectionListenProxy.bytoken:
                logging.info('%s resumed listen by token' % self)
                self.listen_proxy = IncomingConnectionListenProxy.bytoken[token]
                self.listen_proxy.add_websocket_handler(self)
                return
            else:
                self._should_have_listen_proxy = False
                self.do_close('not a valid token')
                logging.info('%s invalid token %s' % (self, token))
                return
            
        i = IncomingConnectionListenProxy.start_port
        while i < IncomingConnectionListenProxy.end_port:
            if i not in IncomingConnectionListenProxy.byport:
                break
            i += 1
        if i == IncomingConnectionListenProxy.end_port:
            self.do_close('no ports available')
            return

        self.listen_port = i
        logging.info("%s INCOMING PROXY OPEN %s" % (self, self.listen_port))

        if self.listen_port in IncomingConnectionListenProxy.byport:
            self.listen_proxy = IncomingConnectionListenProxy.byports[self.listen_port]
        else:
            self.listen_proxy = IncomingConnectionListenProxy(self.listen_port, self.ioloop)
            self.write_message({'port':self.listen_proxy.port, 'token':self.listen_proxy.token})

        if self.listen_proxy.error:
            self.do_close('port listen error')
            return

        self.listen_proxy.add_websocket_handler(self)

    def __repr__(self):
        remote_addr = ':'.join(map(str,self.request.connection.address))
        return "<WS_IncProx:%s,%s,v:%s,%s,(inc_stream:%s)>" % (remote_addr, self.username, self.version, self.listen_port, self.incoming_stream)

    def send_notification(self, address):
        logging.info('%s send new connected address %s' % (self, [address]))
        if self.request.connection.stream.closed():
            logging.warn('%s cannot send new connected notification, ws was closed (close incoming stream)' % self)
            #import pdb; pdb.set_trace()
            self.incoming_stream.close()
        else:
            self.write_message( {'address':address } )

    def handle_incoming_stream(self, stream, address):
        logging.info("%s got a new incoming connection at %s" % (self, [address]))
        if stream.closed():
            logging.error('handle incoming stream on closed stream??')
            return
        self.incoming_stream = stream
        self.incoming_stream.set_close_callback( self.on_incoming_close )
        self.incoming_stream._buffer_grown_callback = self.handle_incoming_stream_chunk
        self.incoming_stream._add_io_state(self.ioloop.READ)
        self.send_notification(address)

    def on_incoming_close(self):
        logging.error('%s incoming stream close' % self)
        if not self.request.connection.stream.closed():
            self.do_close('incoming stream closed')
        #self.listen_proxy.notify_incoming_closed()

    def incoming_stream_resume_read(self):
        self.incoming_stream._add_io_state(self.ioloop.READ)

    def handle_incoming_stream_chunk(self):
        data = self.incoming_stream._read_buffer

        #logging.info("GOT CHUNK %s" % len(data))

        if len(self.request.connection.stream._write_buffer) > 1:
            logging.warn('%s throttle write' % self)
            # stop reading on incoming stream if the write to the websocket is congested
            self.incoming_stream._clear_io_state()
            self.incoming_stream._write_callback = self.incoming_stream_resume_read

        # WARNING!! EXCEPTIONS HERE DO NOT LOG ERRORS! (ioloop handle_read etc catch generic "Exception")
        while len(self.incoming_stream._read_buffer) > 0:
            chunk = self.incoming_stream._read_buffer.popleft()
            # TODO -- check _read_buffer_size ... it's getting out of sync!
            self.write_message(chunk, binary=True)

    def on_close(self):
        if self._should_have_listen_proxy and not self.listen_proxy:
            import pdb; pdb.set_trace()
        self.instances.remove(self)
        logging.warn('%s close' % self)
        if self.listen_proxy: 
            self.listen_proxy.notify_websocket_handler_closed(self)

        if self.incoming_stream:
            logging.warn('%s closing incoming stream too' % self)
            self.incoming_stream.close()

    def websocket_resume_read(self):
        self.request.connection.stream._add_io_state(self.ioloop.READ)

    def on_message(self, msg):
        if self.incoming_stream.closed():
            logging.error('on_message, but websocket was closed? weird')
            return

        #logging.info("INCOMING PROXY MSG %s" % [ msg ] )
        # send back to incoming stream
        if not self.incoming_stream:
            self.do_close('no incoming stream to write to!')
            return
            
        if len(self.incoming_stream._write_buffer) > 1:
            logging.warn('%s throttle read' % self)
            # writing to incoming stream is congested, so slow down read from websocket
            self.request.connection.stream._clear_io_state()
            self.request.connection.stream._write_callback = self.websocket_resume_read

        self.incoming_stream.write(msg)

import bencode
import functools
import tornado.ioloop

class UDPSockWrapper(object):
    def __init__(self, socket, in_ioloop=None):
        self.socket = socket
        self._state = None
        self._read_callback = None
        self.ioloop = in_ioloop or IOLoop.instance()

    def __repr__(self):
        return "<UDPSockWrap:%s,rc:%s>" % (self.socket.fileno(), self._read_callback)

    def _add_io_state(self, state):
        if self._state is None:
            self._state = tornado.ioloop.IOLoop.ERROR | state
            #with stack_context.NullContext():
            self.ioloop.add_handler(
                self.socket.fileno(), self._handle_events, self._state)
        elif not self._state & state:
            self._state = self._state | state
            self.ioloop.update_handler(self.socket.fileno(), self._state)

    def send(self,msg):
        return self.socket.send(msg)

    def recv(self,sz):
        return self.socket.recv(sz)
    
    def close(self):
        self.socket.close()

    def read_chunk(self, callback, timeout=4):
        self._read_callback = callback
        self._read_timeout = self.ioloop.add_timeout( time.time() + timeout, self.check_read_callback )
        self._add_io_state(self.ioloop.READ)

    def check_read_callback(self):
        if self._read_callback:
            # XXX close socket?
            #data = self.socket.recv(4096)
            self._read_callback(None, error='timeout');

    def _handle_read(self):
        if self._read_timeout:
            self.ioloop.remove_timeout(self._read_timeout)
        if self._read_callback:
            try:
                data = self.socket.recv(4096)
            except:
                # conn refused??
                data = None
            self._read_callback(data);
            self._read_callback = None

    def _handle_events(self, fd, events):
        if events & self.ioloop.READ:
            self._handle_read()
        if events & self.ioloop.ERROR:
            logging.error('%s event error' % self)
    


class WebSocketUDPProxyHandler(BaseWebSocketHandler):
    """ open relay for sendingi/receiving UDP data, with websocket frontend """
    instances = []

    def open(self):
        self.instances.append(self)

        self.socks = {}
        logging.error("%s udp proxy open" % self)

    def __repr__(self):
        return "<WS_UDPProxy(rem:%s)>" % ':'.join(map(str,self.request.connection.address))

    def get_sock(self, num):
        return self.socks[num]['sock']

    def on_close(self):
        self.instances.remove(self)

        for k,data in self.socks.iteritems():
            data['sock'].close()
        self.socks = None

    def on_message(self, raw):
        msg = bencode.bdecode(raw)
        #logging.info("%s RPC %s" % (self, [msg]))
        if msg['method'] == 'newsock':
            udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udpsock.setblocking(False)
            try:
                udpsock.connect(tuple(msg['args'][0]))
            except socket.gaierror:
                logging.error('no internet.. send error')
                return
            self.socks[ udpsock.fileno() ] = {'sock': UDPSockWrapper(udpsock)}
            self.send_message( { 'id': msg['id'], 'newsock': udpsock.fileno() } )
        elif msg['method'] == 'sock_close':
            if 'sock' not in msg:
                self.shutdown_with_error('invalid input')
                return


            self.get_sock(msg['sock']).close()
            del self.socks[msg['sock']]
            #self.socks[msg['sock']]
        elif msg['method'] == 'send':
            if 'sock' not in msg:
                self.shutdown_with_error('invalid input')
                return

            self.get_sock(msg['sock']).send( msg['args'][0] )
        elif msg['method'] == 'recv':
            if 'sock' not in msg:
                self.shutdown_with_error('invalid input')
                return

            if self.socks[msg['sock']]['sock']._read_callback:
                logging.error('already reading!')
            # session id?
            #logging.info('%s trying to read from sock' % self)
            sock = self.socks[msg['sock']]['sock']
            sock.read_chunk( functools.partial(self.got_data, msg['sock'], msg['id']) )
            #ioloop.add_handler(msg['sock'], functools.partial(self.got_data, msg['sock'], msg['id']), ioloop.READ)
        # read message

    def shutdown_with_error(self, message):
        self.send_message( { 'error': message } )
        #import pdb; pdb.set_trace()
        for sock in self.socks:
            self.socks['sock'].close()

    def send_message(self, data):
        #logging.info('%s respond w msg %s' % (self, [data]))
        self.write_message( bencode.bencode( data ), binary=True )
        
    def got_data(self, insocknum, id, data, error=None):
        if data is None:
            # timeout
            logging.info('%s reading from udp sock, error: %s' % (self, error))
            msg = { 'sock': insocknum, 'id': id, 'error': 'timeout' }
            #logging.info('%s fd %s TIMEOUT read' % (self, insocknum))
            self.ioloop.remove_handler(insocknum)
        else:
            #logging.info('%s fd %s GOT DATA of len %s' % (self, insocknum, len(data)))
            msg = { 'sock': insocknum, 'id': id, 'data': data }
        #self.socks[insocknum]['read_timeout'] = None
        self.send_message( msg )
