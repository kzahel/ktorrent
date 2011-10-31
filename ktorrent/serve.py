import tornado.ioloop
import tornado.options
import tornado.netutil
import tornado.httpserver
import tornado.web
import logging
from tornado.options import define, options
from torrent import Torrent

define('debug',default=True, type=bool)
define('verbose',default=1, type=int)
define('host',default='10.10.90.24', type=str)
define('datapath',default='/home/kyle/virtualbox-shared/ktorrent', type=str)
define('port',default=8030, type=int)
define('frontend_port',default=9030, type=int)
define('static_path',default='/home/kyle/ktorrent/static', type=str)
define('resume_file',default='/home/kyle/ktorrent/resume.dat', type=str)
define('template_path',default='/home/kyle/ktorrent/templates', type=str)

define('outbound_piece_limit',default=20, type=int)

define('piece_request_timeout',default=10, type=int)

tornado.options.parse_command_line()
settings = dict( (k, v.value()) for k,v in options.items() )

from util import MetaStorage
MetaStorage.sync()

from ktorrent.connection import Connection
if options.debug:
    import pdb


class BTApplication(object):
    def __init__(self, routes, **settings):
        self.routes = routes
        self.settings = settings
        if self.settings.get("debug"):
            import tornado.autoreload # not workin :-(
            tornado.autoreload.start()

    def __call__(self, request):
        #logging.info('%s got request %s' % (self, request))
        if request.type in routes:
            handler_cls = routes[request.type]
            handler_cls(self, request).handle()
        else:
            logging.error('cannot handle request %s' % [request.type, request.payload])
            request.connection.stream.close()

    def log_request(self, handler):
        request_time = 1000.0 * handler.request.request_time()
        logging.info("%s %.2fms", 
                     handler._request_summary(), request_time)

from ktorrent.handlers import BitmaskHandler,\
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
    PieceHandler

routes = { 'BITFIELD': BitmaskHandler,
           'UTORRENT_MSG': UTHandler,
           'PORT': PortHandler,
           'HAVE': HaveHandler,
           'INTERESTED': InterestedHandler,
           'NOT_INTERESTED': NotInterestedHandler,
           'CHOKE': ChokeHandler,
           'UNCHOKE': UnChokeHandler,
           'REQUEST': RequestHandler,
           'CANCEL': CancelHandler,
           'PIECE': PieceHandler
           }

from ktorrent.frontend import IndexHandler, StatusHandler

frontend_routes = [
    ('/?', IndexHandler),
    ('/?', tornado.web.StaticFileHandler),
    ('/statusv2?', StatusHandler)
]

application = BTApplication(routes, **settings)

class BTProtocolServer(tornado.netutil.TCPServer):
    def __init__(self, request_callback, io_loop=None):
        tornado.netutil.TCPServer.__init__(self, io_loop)
        self.request_callback = request_callback

    def handle_stream(self, stream, address):
        Connection(stream, address, self.request_callback)

ioloop = tornado.ioloop.IOLoop()

frontend_application = tornado.web.Application(frontend_routes, **settings)
frontend_server = tornado.httpserver.HTTPServer(frontend_application, io_loop=ioloop)
frontend_server.bind(options.frontend_port, '')
frontend_server.start()
logging.info('started frontend server')

btserver = BTProtocolServer(application, io_loop=ioloop)
btserver.bind(options.port, '')
btserver.start()
logging.info('started btserver')

from ktorrent.download import DownloadSession

tornado.ioloop.PeriodicCallback( Connection.make_piece_request, 1000 * 5, io_loop=ioloop ).start()
tornado.ioloop.PeriodicCallback( Connection.get_metainfo, 1000 * 1, io_loop=ioloop ).start()
tornado.ioloop.PeriodicCallback( Connection.cleanup_old_requests, 1000 * 1, io_loop=ioloop ).start()
ioloop.start()
