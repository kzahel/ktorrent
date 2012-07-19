import tornado.web
import logging
from ktorrent.connection import Connection
from ktorrent.torrent import Torrent
import json
from cgi import escape
import signal
import pdb
import sys


def got_interrupt_signal(signum=None, frame=None):
    logging.info('got quit signal ... saving quick resume')
    Torrent.save_quick_resume()
    sys.exit()

signal.signal(signal.SIGINT, got_interrupt_signal)

class BaseHandler(tornado.web.RequestHandler):
    pass

class IndexHandler(BaseHandler):
    def get(self):
        pass

class StatusHandler(BaseHandler):
    def get(self):
        attrs = {}

        attrs.update( dict( connections = Connection.instances,
                            torrents = Torrent.instances
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

class APIHandler(BaseHandler):
    def get(self): return self.post();

    def post(self):
        self.write( dict( foo = 23 ) )
