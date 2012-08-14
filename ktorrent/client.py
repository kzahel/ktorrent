import logging
import bencode
import hashlib
import binascii
from uuid import uuid4
from torrent import Torrent
from connection import Connection
from session import Session
from settings import Settings
from urlparse import urlparse

class Client(object):
    instances = []

    @classmethod
    def instance(cls):
        return cls.instances[0]

    def do_trackers(self):
        for hash,torrent in self.torrents.iteritems():
            if torrent.tracker_on():
                torrent.do_trackers()

    def peer_think(self):
        for hash,torrent in self.torrents.iteritems():
            torrent.peer_think()

    @classmethod
    def tick(cls):
        # updates torrent download/upload rates
        return
        # only do this for pushing updates -- we actually use polling

        for client in cls.instances:
            allchanges = {}
            for hash, torrent in client.torrents.iteritems():
                changes = torrent.update_attributes()
                #logging.info('tor update attrs got changes %s' % changes)
                if changes:
                    allchanges[hash] = changes
            if allchanges:
                for id, session in client.sessions.iteritems():
                    # no -- only do this when session requests an update!
                    
                    session.process_changes({'torrent':allchanges})

    def notify_sessions(self, **kwargs):
        for session in self.sessions:
            session.notify(**kwargs)

    def add_torrent(self, hash):
        torrent = Torrent.instantiate(hash)
        if hash not in self.torrents:
            self.torrents[hash] = torrent
            # notify any sessions
            #self.notify_sessions(added={'btapp/torrent':torrent})
            #Session.notify(client=self, added=torrent)
        return True

    def remove_torrent(self, hash):
        torrent = Torrent.instantiate(hash)
        if hash in self.torrents:
            torrent = self.torrents[hash]
            del self.torrents[hash]
            torrent.remove() #causes connections to close and other bookkeeping

    def add_torrent_any(self, s):
        # adds magnet link or uri or hash
        parsed = urlparse(s)
        logging.info('add torrent %s' % s)
        if parsed.scheme == 'magnet':
            args = parsed.path[1:].split('&')
            sep = [a.split('=') for a in args]
            d = dict( (s[0], s[1]) for s in sep )
            hash = d['xt'].split(':')[-1]# urn:btih:{{hash}}
            logging.warn('adding infohash parsed from magnet uri %s' % hash)
            rawhash = binascii.unhexlify(hash)
            self.add_torrent(rawhash)
            return True
        elif parsed.scheme == '':
            if len(s) == 40:
                hash = binascii.unhexlify(s)
                return self.add_torrent(hash)
            else:
                logging.error('bad add uri %s' % s)
        else:
            self.http_client.fetch(s, self.added_torrent_url)
            return True
            #logging.error('add by url not supported %s' % s)
            #return False

    def added_torrent_url(self, response):
        if response.code == 200:
            meta = bencode.bdecode(response.body)
            infohash = hashlib.sha1(bencode.bencode(meta['info'])).digest()
            torrent = Torrent.instantiate(infohash)
            if not torrent.meta:
                # update?
                torrent.update_meta(meta)
                torrent.save_metadata()
            self.add_torrent(torrent.hash)
            #torrent.start()

        

    def __repr__(self):
        return '<Client %s>' % self.id

    @classmethod
    def resume(cls):
        Settings.load()
        clients = Settings.get('clients')
        if clients:
            cls.instances = [cls(d) for d in clients]
        else:
            cls.instances = [cls()]

    @classmethod
    def save_settings(cls):
        for h,t in Torrent.instances.iteritems():
            t.save_quick_resume()
            t.save_attributes()
        d = [{'torrents': [str(hash) for hash in c.torrents],
              'id': c.id} for c in cls.instances]
        Settings.set('clients',d)
        Settings.flush()

    def __init__(self, data=None):
        self.torrents = {}
        self.sessions = {}
        self.torrent_althashes = {}
        if data:
            self.id = data['id']
            if 'torrents' in data:
                self.torrents = dict( (t,Torrent.instantiate(t)) for t in data['torrents'] if len(t) == 20 )
                for hash,t in self.torrents.iteritems():
                    t.get_bitmask(force_create=False) # force a load of metadata from .torrent files
                    #t.load_attributes() # done in the init
        else:
            self.id = str(uuid4()).split('-')[0]


    def connect(self, host, port, hash):
        #logging.info('CONNECT! %s' % self)
        if hash not in self.torrents:
            self.add_torrent(hash)
        connection = Connection.initiate(host,port,hash)
        connection.set_client(self)
        
    def handle_connection(self, stream, address, callback):
        # todo: fix not doing fast resume on bitmask
        logging.info('client Handle conn! %s' % self)
        connection = Connection(stream, address, callback, has_connected=True)
        connection.set_client(self)
        
    def value_changed(self, d):
        pass
        
Torrent.Client = Client
