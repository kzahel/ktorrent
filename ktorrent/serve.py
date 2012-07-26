import tornado.ioloop
import tornado.options
import tornado.netutil
import tornado.httpserver
import tornado.web
import functools
import time
import logging
import os
from hashlib import sha1
import bencode
from tornado.options import define, options
from torrent import Torrent
home = os.getenv("HOME")
define('debug',default=True, type=bool)
define('asserts',default=True, type=bool)
define('verbose',default=1, type=int)
define('host',default='10.10.90.24', type=str)

define('port',default=8030, type=int)
define('frontend_port',default=10000, type=int)
define('datapath',default=os.path.join(home,'ktorrent/data'), type=str)
define('static_path',default=os.path.join(home,'ktorrent/static'), type=str)
define('resume_file',default=os.path.join(home,'ktorrent/resume.dat'), type=str)
define('template_path',default=os.path.join(home,'ktorrent/templates'), type=str)

define('startup_connect_to', default='', type=str)
define('startup_connect_torrent', default='', type=str)
define('startup_connect_to_hash', default='', type=str)
define('startup_exit_on_close', default=False, help='quit program when connection closes', type=bool)

#define('outbound_piece_limit',default=1, type=int)
define('outbound_piece_limit',default=20, type=int)
define('piece_request_timeout',default=10, type=int)

tornado.options.parse_command_line()
settings = dict( (k, v.value()) for k,v in options.items() )

from util import MetaStorage
MetaStorage.sync()
from tornado.autoreload import add_reload_hook
import signal
import sys

from connection import Connection
from client import Client
if options.debug:
    import pdb
ioloop = tornado.ioloop.IOLoop()
ioloop.install()
#print 'new ioloop',ioloop

class BTApplication(object):
    def __init__(self, routes, **settings):
        self.routes = routes
        self.settings = settings
        if True or self.settings.get("debug"):
            pass
            #print 'importing autoreload'
            #import tornado.autoreload # not workin :-(
            #tornado.autoreload.start()

    def __call__(self, request):
        #logging.info('%s got request %s' % (self, request))
        if request.type in routes:
            handler_cls = routes[request.type]
            handler_cls(self, request).handle()
        else:
            logging.error('cannot handle request %s' % [request.type, request.payload])
            request.connection.stream.close()

    def log_request(self, handler):
        if options.verbose > 1:
            request_time = 1000.0 * handler.request.request_time()
            logging.info("%s %.2fms", 
                         handler._request_summary(), request_time)

from handlers import BitmaskHandler,\
    UTHandler,\
    NullHandler,\
    HaveHandler,\
    ChokeHandler,\
    InterestedHandler,\
    PortHandler,\
    UnChokeHandler,\
    NotInterestedHandler,\
    RequestHandler,\
    CancelHandler,\
    PieceHandler,\
    HaveAllHandler

routes = { 'BITFIELD': BitmaskHandler,
           'UTORRENT_MSG': UTHandler,
           'PORT': PortHandler,
           'HAVE': HaveHandler,
           'HAVE_ALL': HaveAllHandler,
           'INTERESTED': InterestedHandler,
           'NOT_INTERESTED': NotInterestedHandler,
           'CHOKE': ChokeHandler,
           'UNCHOKE': UnChokeHandler,
           'REQUEST': RequestHandler,
           'CANCEL': CancelHandler,
           'PIECE': PieceHandler
           }

from frontend import IndexHandler, StatusHandler, APIHandler, PingHandler, VersionHandler, BtappHandler, PairHandler, request_logger

frontend_routes = [
    ('/?', IndexHandler),
    ('/static/.?', tornado.web.StaticFileHandler),
    ('/gui/pingimg', PingHandler),
    ('/gui/pair/?', PairHandler),
    ('/version/?', VersionHandler),
    ('/statusv2/?', StatusHandler),
    ('/api', APIHandler),
    ('/btapp/?', BtappHandler)
]

application = BTApplication(routes, **settings)

Client.resume()
client = Client.instances[0]

add_reload_hook( lambda: Client.save_settings() )

def got_interrupt_signal(signum=None, frame=None):
    logging.info('got quit signal ... saving quick resume')
    Client.save_settings()
    #Torrent.save_quick_resume()
    sys.exit()

signal.signal(signal.SIGINT, got_interrupt_signal)

class BTProtocolServer(tornado.netutil.TCPServer):
    def __init__(self, request_callback, io_loop=None):
        tornado.netutil.TCPServer.__init__(self, io_loop)
        self.request_callback = request_callback

    def handle_stream(self, stream, address):
        client.handle_connection(stream, address, self.request_callback)
        #Connection(stream, address, self.request_callback)

Connection.ioloop = ioloop
Connection.application = application
settings['log_function'] = request_logger
frontend_application = tornado.web.Application(frontend_routes, **settings)
frontend_server = tornado.httpserver.HTTPServer(frontend_application, io_loop=ioloop)
try:
    frontend_server.bind(options.frontend_port, '')
    frontend_server.start()
    logging.info('started frontend server')
except:
    logging.error('could not start frontend server')

btserver = BTProtocolServer(application, io_loop=ioloop)
btserver.bind(options.port, '')
btserver.start()
logging.info('started btserver')

tornado.ioloop.PeriodicCallback( Connection.make_piece_request, 1000 * 5, io_loop=ioloop ).start()
tornado.ioloop.PeriodicCallback( Connection.get_metainfo, 1000 * 1, io_loop=ioloop ).start() # better to make event driven
tornado.ioloop.PeriodicCallback( Client.tick, 1000 * 1, io_loop=ioloop ).start()
tornado.ioloop.PeriodicCallback( Connection.cleanup_old_requests, 1000 * 1, io_loop=ioloop ).start()

#testhash = '0EB7F828D4E097FDB1ADE74186528CD31DFC1A3C'
#testhash = '084F42A339A41E78692BFE8930BCFFF8A17DB18C'
#testhash = '875CA32E6B730F628D2EB7E312D289DC8E54768C'
testhash = '084F42A339A41E78692BFE8930BCFFF8A17D0000'
#Connection.initiate('ec2-107-22-42-93.compute-1.amazonaws.com',43858,testhash)
#Connection.initiate('10.10.90.191',,testhash)
#Connection.initiate('10.10.90.242',8030,testhash)

#import random
#randomhash = random.choice(MetaStorage.keys())
#logging.info('random hash %s' % randomhash)

startuphash = None
if options.startup_connect_torrent:
    logging.info('startup connect torrent! %s' % options.startup_connect_torrent)
    fo = open( options.startup_connect_torrent )
    torrentdata = bencode.bdecode( fo.read() )
    startuphash = sha1( bencode.bencode( torrentdata['info'] ) ).hexdigest()
    MetaStorage.data[ startuphash.upper() ] = str(options.startup_connect_torrent)
    MetaStorage.sync()

if options.startup_connect_to:
    host,port = options.startup_connect_to.split(':')
    port = int(port)
    if not startuphash:
        if options.startup_connect_to_hash:
            startuphash = options.startup_connect_to_hash
        else:
            #purisma = '27689B76CDA08C9E21ACD9584CDB90AA82C63676'
            purisma = 'FC59F2D267DA5480F0FAF37373C54F59CB5A980E'
            startuphash = purisma
    fn = functools.partial(client.connect, host, port, startuphash)
    ioloop.add_timeout( time.time() + 1, fn )
    #client.connect(host,port,startuphash)

ioloop.start()
