import bencode
from tornado.options import options
import os
import logging
import random
from hashlib import sha1
import math
import pdb
import struct
import constants
import time
import binascii
from tornado import gen
from bitcounter import BitCounter
import bencode
import binascii
from settings import Settings
from tracker import Tracker
from constants import tor_meta_codes, tor_meta_codes_r

from file import File
from piece import Piece

from util import hexlify

class Torrent(object):
    instances = {}

    attribute_keys = ['down_speed','progress','downloaded','size', 'peers', 'name', 'status', 'message']
    persist_keys = ['upload_limit','status','queue_position'] # store in the settings
    #bits: ['started', 'checking', 'start after check', 'checked', 'error', 'paused', 'queued', 'loaded']

    _default_attributes = {'status':0, 'queue_position':-1, 'upload_limit':0} # persist this...

    @classmethod
    def register_althash(cls, torrent):
        althash = torrent.hash
        realhash = sha1(torrent.meta_info).hexdigest()
        Settings.set(['torrent_althashes',realhash], althash)
        logging.info('set torrent althash')

    def peer_think(self):
        # think about our current list of peers, and if we'd rather be
        # doing something with other peers...
        for key,tracker in self.trackers.iteritems():
            if tracker.can_announce():
                tracker.announce(self.hash)

        if self.wants_more_peers():
            logging.info('wants more peers!')
            peer = self.get_random_peer()
            if peer:
                Torrent.Client.instance().connect( peer[0], peer[1], self.hash )

    def get_random_peer(self):
        for key,tracker in self.trackers.iteritems():
            if tracker.peerdata:
                return random.choice(tracker.peerdata)

    def notify_peers(self, peer_list):
        return
        # called when new peers are available (via a tracker)
        if peer_list:
            if self.wants_more_peers():
                peer = random.choice(peer_list)
                logging.info('add a peer! %s' % [peer])
                Torrent.Client.instance().connect( peer[0], peer[1], self.hash )
                #fn = functools.partial(client.connect, host, port, startuphash)
            
    def wants_more_peers(self):
        return len(self.connections) < 5 # and self.started()

    @gen.engine
    def do_trackers(self, callback=None):
        assert(len(self.hash) == 20)
        # talk to trackers in attempt to get peers
        if not self.started(): raise StopIteration
        if not self.meta: raise StopIteration

        if 'announce-list' in self.meta:
            tier1 = self.meta['announce-list'][0]
            for url in tier1:
                tracker = Tracker.instantiate(url, self.hash)
                self.trackers[tracker.get_key()] = tracker
                if tracker.can_announce():
                    result = yield gen.Task( tracker.announce )
                    logging.info('%s tracker announce got result %s' % ([self.hash], result))


    def __repr__(self):
        return '<Torrent %s (meta:%s, %s)>' % (hexlify(self.hash), True if self.meta else False, self.get_summary())

    def throttled(self):
        return False
        return self.bitcounter.recent() > self.max_dl_rate()

    def max_dl_rate(self):
        return 8192
        #return 16384 * 2
        #return 16384 * 1024

    def recheck(self):
        # re-checks all pieces
        pass

    def quick_recheck(self):
        # just checks files existing and file sizes
        pass

    def start(self):
        self.set_attribute('status', 1)

    def stop(self):
        self.set_attribute('status', 0)

    def dump_state(self):
        data =  {'stop': "[nf]()",
                 'start': "[nf]()",
                 'remove': "[nf](number)()",
                 'recheck': "[nf]()",
                 'add_peer':"[nf](string)(dispatch)",
                 'hash':hexlify(self.hash),
                 'properties':{'all':self.get_attributes()}}
        if self.meta:
            data['file'] = self.dump_file_state()
        return data

    def dump_file_state(self):
        d = {}
        for i in range(self.get_num_files()):
            file = self.get_file(i)
            d.update( file.dump_state() )
        return d

    def get_attributes(self):
        return dict( (k, self.get_attribute(k)) for k in self.attribute_keys )

    def get_summary(self):
        if self.bitmask:
            #if self.bitmask.count(0) == 1:
            #    import pdb; pdb.set_trace()
            return 'zeropieces:%s/%s' % (self.bitmask.count(0),
                                     len(self.bitmask))
        else:
            return 'no bitmask'

    def save_metadata(self):
        torrent_meta = self.meta
        filename = torrent_meta['info']['name'] + '.torrent'
        key = self.hash
        #key = self.hash.upper()
        Settings.set(['torrents',key,'filename'],filename)

        fo = open( os.path.join(options.datapath, filename), 'w')
        fo.write( bencode.bencode(torrent_meta) )
        fo.close()

    def load_metadata(self):
        try:
            filename = Settings.get(['torrents',self.hash,'filename'])
        except KeyError:
            return

        filepath = os.path.join(options.datapath, filename)
        if os.path.exists(filepath):
            fo = open( filepath )
            data = fo.read()
            self.meta = bencode.bdecode( data )
            fo.close()
        else:
            logging.error('%s missing on disk' % filepath)

    def load_quick_resume(self):
        try:
            return self.decode_bitmask(Settings.get(['torrents',self.hash,'bitmask']))
        except:
            pass

    def save_quick_resume(self):
        if self.bitmask:
            Settings.set(['torrents',self.hash,'bitmask'], self.encode_bitmask(self.bitmask))

    def encode_bitmask(self, arr):
        # to reduce size of settings file ...
        # encodes bitmask into bytes
        return arr

    def decode_bitmask(self, bytes):
        # decodes from bytes to array of 0,1's
        return bytes

    def save_attributes(self):
        saveattrs = {}
        for k in self._attributes:
            if self._attributes[k] != self._default_attributes[k]:
                saveattrs[k] = self._attributes[k]
        if saveattrs:
            Settings.set(['torrents',self.hash,'attributes'], saveattrs)

    def load_attributes(self):
        try:
            attributes = Settings.get(['torrents',self.hash,'attributes'])
            self._attributes.update( attributes )
        except:
            pass
            

    def cleanup_old_requests(self, conn, t=None):
        if t is None: t = time.time()

        for k,piece in self.pieces.iteritems():
            piece.cleanup_old_requests(conn, t)

    def remove(self):
        logging.info('remove torrent %s' % self)
        for conn in self.connections:
            logging.info('closing torrent connection %s' % conn)
            conn.shutdown(reason='torrent deleted')
        del self.instances[self.hash]

    def handle_bad_piece(self, piece):
        logging.error('BAD PIECE!')
        del self.pieces[piece.num]

    def handle_good_piece(self, piece, data):
        #logging.info('handle good piece!')
        del self.pieces[piece.num]
        self.bitmask[piece.num] = 1
        piece.write_data(data)

        if self.bitmask.count(0) == 0:
            logging.info('torrent is finished!')
            torrent_finished = True
            return torrent_finished

    def register_pieces_requested(self, request_data):
        #logging.info('%s register pieces requested %s' % (self, request_data))
        self.piece_consumers.append(request_data)
        for piece in request_data['pieces']:
            piece.add_listening_handler(request_data['handler'])

    def unregister_pieces_requested(self, request_data):
        self.piece_consumers.remove(request_data)

    def should_be_making_requests(self):
        return len(self.piece_consumers) > 0 or self.started()

    def get_high_priority_piece(self):
        toreturn = None
        toremove_consumers = []
        for piece_consumer in self.piece_consumers:
            toremove_pieces = []
            pieces = piece_consumer['pieces']
            if not pieces:
                toremove_consumers.append( piece_consumer )
                # remove this piece consumer and mark as done
                #logging.warn('remove this piece consumer')
                #piece_consumer['handler'].notify_all_pieces_complete() # wrong place, not necessary
            for piece in pieces:
                if piece.complete():
                    toremove_pieces.append(piece)
                else:
                    toreturn = piece
                    break
            for piece in toremove_pieces:
                pieces.remove(piece)
            if toreturn:
                break

        for piece_consumer in toremove_consumers:
            self.piece_consumers.remove(piece_consumer)

        return toreturn

    def get_lowest_piece_can_that_can_make_request(self, conn):
        start = 0
        while start < len(self.bitmask):
            try:
                i = self.bitmask.index(0, start)
            except ValueError:
                break
            if conn._remote_bitmask[i] == 1:
                piece = self.get_piece( i )
                if piece.make_request(conn, peek=True):
                    return piece
            start = i+1

    def get_lowest_incomplete_piece(self):
        try:
            i = self.bitmask.index(0)
            piece = self.get_piece( i )
            return piece 
        except:
            pass

    def get_file(self, filenum=0):
        if filenum in self.files:
            return self.files[filenum]
        else:
            file = File(self, filenum)
            self.files[filenum] = file
            return file

    def get_piece(self, piecenum):
        if piecenum in self.pieces:
            return self.pieces[piecenum]
        else:
            piece = Piece(self, piecenum)
            self.pieces[piecenum] = piece
            return piece

    def get_num_files(self):
        if self.is_multifile():
            return len(self.meta['info']['files'])
        else:
            return 1

    def get_num_pieces(self):
        return len(self.meta['info']['pieces'])/20

    def get_bitmask(self, resume=True, force_create=True):
        # retrieves bitmask from the resume.dat or creates it#aoeu
        if resume:
            bitmask = self.load_quick_resume()
            if bitmask:
                self._bitmask_incomplete_count = bitmask.count(0)
                if options.verbose > 5:
                    logging.info('loaded quick resume %s, %s' % (self, bitmask))
                return bitmask
        if force_create:
            return self.create_bitmask()

    def all_files_missing(self):
        return False

    def create_bitmask(self):
        # need to improve this function to detect when files are completely missing that we don't need to return null bytes etc...
        bitmask = []

        if self.all_files_missing():
            for piecenum in range(self.get_num_pieces()):
                bitmask.append(0)
            self._bitmask_incomplete_count = bitmask.count(0)
            return bitmask
        else:
            logging.info('computing piece hashes... (this could take a while)')
            for piecenum in range(self.get_num_pieces()):
                diskpiecehash = self.get_piece_disk_hash(piecenum)
                metahash = self.meta['info']['pieces'][20*piecenum: 20*(piecenum+1)]
                #logging.info('hash on disk/meta: %s' % [diskpiecehash, metahash])
                if diskpiecehash == metahash:
                    bitmask.append(1)
                else:
                    bitmask.append(0)
            self._bitmask_incomplete_count = bitmask.count(0)
            logging.info('missing pieces: %s' % self._bitmask_incomplete_count)
            return bitmask

    def get_piece_disk_hash(self, piecenum):
        s = sha1()
        #logging.info('getting data for piece %s' % piecenum)
        data = self.get_data(piecenum)
        #logging.info('data has len %s' % len(data))
        s.update(data)
        return s.digest()

    @classmethod
    def instantiate(cls, infohash):
        assert(len(infohash) == 20)
        #logging.info('instantiate torrent with hash %s' % infohash)
        if infohash in cls.instances:
            instance = cls.instances[infohash]
        else:
            instance = cls(infohash)
            cls.instances[infohash] = instance
        return instance

    def is_multifile(self):
        return 'files' in self.meta['info']

    def get_metadata_piece_payload(self, piece):
        piecedata = self.meta_info[Piece.std_size * piece : Piece.std_size * (piece + 1)]
        toreturn = ''.join( ( bencode.bencode( { 'total_size': len(self.meta_info),
                                                 'piece': piece,
                                                 'msg_type': tor_meta_codes_r['data'] } ),
                          piecedata ) )
        return toreturn

    def ensure_stream_id(self):
        try:
            self.sid = Settings.get(['torrents',self.hash,'sid'])
        except:
            chars = map(str,range(10)) + list('abcdef')
            sid = ''.join( [random.choice( chars ) for _ in range(5)] )
            Settings.set(['torrents',self.hash,'sid'], sid)
            self.sid = sid

    def update_meta(self, meta, update=False):
        #logging.info('update meta!')
        self.meta = meta
        self.meta_info = bencode.bencode(self.meta['info'])
        if self.is_multifile():
            b = 0
            self._file_byte_accum = []
            for i,filedata in enumerate(self.meta['info']['files']):
                self._file_byte_accum.append(b)
                b += filedata['length']
        else:
            self._file_byte_accum = [0]
        self.bitmask = self.get_bitmask()
        if options.verbose > 2:
            logging.info('bitmask is %s' % ''.join(map(str,self.bitmask)))
        for i in range(self.get_num_pieces()):
            self.get_piece(i) # force populate (for Piece spanning file progress computation)
        Torrent.Connection.notify_torrent_has_bitmask(self)

    def set_attribute(self, key, value):
        if key == 'status':
            self._attributes[key] = value
        else:
            logging.error('unsupported set attribute on %s' % key)

    def get_attribute(self, key):
        if key == 'down_speed':
            return self.bitcounter.recent()
        elif key == 'progress':
            if self.bitmask:
                return (1000 * self.bitmask.count(1)) / len(self.bitmask)
            else:
                return 0
        elif key == 'message':
            return ''
        elif key == 'status':
            return self._attributes[key]
        elif key == 'name':
            if self.meta:
                return self.meta['info']['name']
            else:
                import pdb; pdb.set_trace()
                return hexlify(self.hash)
        elif key == 'size':
            return self.get_size() if self.meta else None
        elif key == 'downloaded':
            if self.bitmask:
                return self.bitmask.count(1) * self.get_piece_len()
            else:
                return 0
        elif key == 'peers':
            return len(self.connections)
        else:
            logging.error('unsupported attribute %s' % key)

    def update_attributes(self, existing):
        # update attributes that get pushed to sessions

        add,remove = {},{}

        for key in self.attribute_keys:

            newval = self.get_attribute(key)
            oldval = existing['properties']['all'][key]
            existing['properties']['all'][key] = newval

            if newval != oldval:
                if 'properties' not in add: # or remove(redundant)
                    add['properties'] = {'all':{}}
                    remove['properties'] = {'all':{}}
                add['properties']['all'][key] = newval
                remove['properties']['all'][key] = oldval

        return add, remove

    def __init__(self, infohash):
        self.connections = []
        self.trackers = {}
        self.bitcounter = BitCounter()
        self.hash = infohash
        assert(len(self.hash) == 20)
        self.piece_consumers = []
        self.pieces = {} # lazy populate on get_piece
        self.files = {} # lazy populate on get_file
        self.bitmask = None
        self._attributes = self._default_attributes.copy()
        self.meta = None
        self.meta_info = None
        self._file_byte_accum = None
        self.load_attributes()
        self.load_metadata()
        # also creates a stream id for settings, if none created yet.
        self.ensure_stream_id()
        if self.meta:
            self.update_meta(self.meta)

    def started(self):
        return self._attributes['status'] & 1

    def get_size(self, i=None):
        if 'files' in self.meta['info']:
            return sum( [f['length'] for f in self.meta['info']['files']] )
        else:
            return self.meta['info']['length']

    def get_piece_hash(self, piecenum):
        return self.meta['info']['pieces'][20*piecenum:20*(piecenum+1)]

    def get_piece_len(self, piecenum=None):
        if piecenum is None:
            return self.meta['info']['piece length']
        else:
            if piecenum == self.get_num_pieces() - 1:
                return self.get_size() - self.get_piece_len() * piecenum
            else:
                return self.meta['info']['piece length']

    def get_data(self, piecenum=0, offset=0, size=None):
        if size is None: size = self.get_piece_len(piecenum)
        piece = self.get_piece(piecenum)
        return piece.get_data(offset, size)

Tracker.Torrent = Torrent
