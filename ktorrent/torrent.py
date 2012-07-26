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
from bitcounter import BitCounter
import bencode
from settings import Settings
from constants import tor_meta_codes, tor_meta_codes_r

from file import File
from piece import Piece

class Torrent(object):
    instances = {}

    attribute_keys = ['down_speed','progress','downloaded','size', 'peers', 'name', 'status', 'message']
    persist_keys = ['upload_limit','status','queue_position'] # store in the settings
    #bits: ['started', 'checking', 'start after check', 'checked', 'error', 'paused', 'queued', 'loaded']

    _default_attributes = {'status':0, 'queue_position':None, 'upload_limit':0} # persist this...

    def __repr__(self):
        return '<Torrent %s (meta:%s, %s)>' % (self.hash, True if self.meta else False, self.get_summary())

    def throttled(self):
        return self.bitcounter.recent() > self.max_dl_rate()

    def max_dl_rate(self):
        return 16384 * 2

    def recheck(self):
        # re-checks all pieces
        pass

    def quick_recheck(self):
        # just checks files existing and file sizes
        pass

    def dump_state(self):
        data =  {'stop': "[nf]()",
                 'start': "[nf]()",
                 'remove': "[nf](number)()",
                 'recheck': "[nf]()",
                 'add_peer':"[nf](string)(dispatch)",
                 'hash':self.hash,
                 'properties':{'all':self.get_attributes()}}
        #if self.meta:
        #    data['file'] = self.dump_file_state()
        return data

    def dump_file_state(self):
        # never stored off files?
        d = {}
        for filenum in self.files:
            pass
        return d

    def get_attributes(self):
        return dict( (k, self.get_attribute(k)) for k in self.attribute_keys )

    def get_summary(self):
        if self.bitmask:
            return 'zeropieces:%s/%s' % (self.bitmask.count(0),
                                     len(self.bitmask))
        else:
            return 'no bitmask'

    def load_quick_resume(self):
        resume_data = Settings.get()
        if resume_data and self.hash in resume_data:
            if 'bitmask' in resume_data[self.hash]:
                #logging.info('restored bitmask to %s' % self)
                bitmask = resume_data[self.hash]['bitmask']
                self._bitmask_incomplete_count = bitmask.count(0)
                return bitmask
    
    @classmethod
    def save_quick_resume(cls):
        #saves computed infohashes on shutdown
        if os.path.exists( options.resume_file ):
            fo = open(options.resume_file)
            data = bencode.bdecode( fo.read() )
            fo.close()
        else:
            data = {}
        logging.warn('save quick resume race condition with filename')
        for k,torrent in cls.instances.iteritems():
            if torrent.bitmask:
                newdata = { 'bitmask' : torrent.bitmask }
                if torrent.hash in data:
                    curdata = data[torrent.hash]
                    data[torrent.hash].update(newdata)
                else:
                    data[torrent.hash] = newdata

        fo = open(options.resume_file,'w')
        fo.write( bencode.bencode( data ) )
        if options.verbose > 3:
            logging.info('write settings %s' % data)
        fo.close()

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
        del self.torrent.pieces[piece.num]

    def handle_good_piece(self, piece, data):
        #logging.info('handle good piece!')
        del self.pieces[piece.num]
        self.bitmask[piece.num] = 1
        piece.write_data(data)

        if self.bitmask.count(0) == 0:
            logging.info('torrent is finished!')
            torrent_finished = True
            return torrent_finished

    def get_lowest_piece_can_that_can_make_request(self, conn):
        start = 0
        try:
            while start < len(self.bitmask):
                i = self.bitmask.index(0, start)
                if conn._remote_bitmask[i] == 1:
                    piece = self.get_piece( i )
                    if piece.make_request(conn, peek=True):
                        return piece
                
                start = i+1
        except:
            logging.error('error selecting piece (bad try block...)')

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

    def get_bitmask(self, resume=True):
        # retrieves bitmask from the resume.dat or creates it
        if resume:
            bitmask = self.load_quick_resume()
            if bitmask:
                if options.verbose > 5:
                    logging.info('loaded quick resume %s, %s' % (self, bitmask))
                return bitmask
        return self.create_bitmask()

    def create_bitmask(self):
        bitmask = []
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

    def update_meta(self, meta):
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
            logging.info('self.bitmask is %s' % ''.join(map(str,self.bitmask)))
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
                return self.hash
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
        self.bitcounter = BitCounter()
        self.hash = infohash
        self.pieces = {}
        self.files = {}
        self.bitmask = None
        self._attributes = self._default_attributes.copy()

        torrent_data = Settings.get(self.hash.upper())
        if torrent_data:
            if 'attributes' in torrent_data:
                self._attributes.update( torrent_data['attributes'] )
            filename = torrent_data['filename']
        else:
            filename = None
        if filename:
            meta = bencode.bdecode( open( os.path.join(options.datapath, filename) ).read() )
            self.update_meta( meta )
        else:
            #logging.warn('instantiated torrent that has no torrent registered in meta storage')
            self.meta = None
            self.meta_info = None
            self.bitmask = None
            self._file_byte_accum = None

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

