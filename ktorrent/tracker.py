from tornado import gen
from tornado import httpclient
import bencode
import binascii
import time
import urllib

from util import decode_peer

class TrackerResponse(object):
    def __repr__(self):
        return '<TrackerResponse %s>' % (self.data if self.data else 'Error:%s'%self.httpresponse.code)
    def __init__(self, httpresponse, data=None):
        self.httpresponse = httpresponse
        self.error = httpresponse.code != 200
        self.data = data

import logging

class Tracker(object):
    http_client = None
    instances = {}

    def get_key(self):
        return self.url

    @classmethod
    def instantiate(cls, url, infohash):
        key = '%s-%s' % (binascii.hexlify(infohash), url)
        if key in cls.instances:
            instance = cls.instances[key]
        else:
            instance = cls(url, infohash)
            cls.instances[key] = instance
        return instance

    def __init__(self, url, infohash):
        self.key = '%s-%s' % (binascii.hexlify(infohash), url)
        self.infohash = infohash
        self.url = url
        self.last_announce = None
        self.min_interval = None
        self.interval = None
        self.peerdata = None

    def can_announce(self):
        if not self.last_announce:
            return True
        else:
            if self.min_interval:
                return time.time() - self.last_announce > self.min_interval
            elif self.interval:
                return time.time() - self.last_announce > self.interval
            else:
                return True
        
    @gen.engine
    def announce(self, callback=None):
        logging.info('%s announcing' % self)
        if not self.http_client:
            Tracker.http_client = httpclient.AsyncHTTPClient()

        if not self.can_announce():
            if callback:
                callback(None)

        self.last_announce = time.time()

        response = yield gen.Task( self.http_client.fetch, '%s?info_hash=%s&compact=1' % (self.url, urllib.quote(self.infohash) ) )

        if response.code == 200:
            data = bencode.bdecode(response.body)

            peerdata = []
            if 'peers' in data:
                for i in range(len(data['peers'])/6):
                    decoded = decode_peer( data['peers'][i*6:(i+1)*6] )
                    if decoded[1] != 0:
                        peerdata.append( decoded )


            if 'min interval' in data:
                self.min_interval = data['min interval']

            if 'interval' in data:
                self.interval = data['interval']

            self.peerdata = peerdata

            toreturn = {'response':data, 'peers':peerdata}

            Tracker.Torrent.instantiate(self.infohash).notify_peers(peerdata)

            if callback:
                callback(TrackerResponse(response, toreturn))
        else:
            if callback:
                callback(TrackerResponse(response))
