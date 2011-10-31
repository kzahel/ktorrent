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
from util import MetaStorage

def intersect(i1, i2):
    if i1[1] < i2[0] or i2[1] < i1[0]:
        return None
    else:
        return max(i1[0],i2[0]), \
            min(i1[1],i2[1])

def intersect_broken(i1, i2):
    b1, e1 = i1
    b2, e2 = i2

    if b1 <= e2:
        #    11...
        #          2...
        if e1 >= b2:
            # 1111111...
            #    222222...
            if e1 <= e2:
                # 1111111
                #   222222222
                return (b2, e1)
            else:
                # 111111111
                #   2222
                return (b2, e2)
    else:
        return intersect(i2, i1)

def ensure_exist(path):
    if not os.path.isfile(path):
        fo = open(path, 'w')
        fo.write('')
        fo.close()


class File(object):
    def __init__(self, torrent, num):
        self.num = num
        self.torrent = torrent
        self.size = self.get_size()
        self.start_byte = self.torrent._file_byte_accum[self.num]
        self.end_byte = self.start_byte + self.size - 1
        self.path = self.get_path()

    def get_data_in_interval(self, pinterval):
        interval = intersect( pinterval,
                              (self.start_byte, self.end_byte) )
        if False:
            logging.info('file %s get data intersecting interval %s --> %s' % ( (self.start_byte, self.end_byte),
                                                                                pinterval,
                                                                                interval ))
        if interval:
            readsz = interval[1] - interval[0] + 1
            if os.path.isfile( self.get_path() ):
                fo = open(self.get_path())
                if self.start_byte >= interval[0]:
                    # iiiiii
                    #    fffff
                    # minimum of...
                    data = fo.read( readsz )
                else:
                    # ffff
                    #   iiiiiii
                    #logging.info('seeking to file byte offset')
                    #pdb.set_trace()
                    fo.seek( interval[0] - self.start_byte )
                    data = fo.read( readsz )
                if len(data) != readsz:
                    #logging.warn('filling in with null bytes')
                    data = data + '\0' * (readsz - len(data))

                return data
            else:
                return '\0' * readsz

    def write_data_from_piece(self, piece, data):
        # given a complete piece, write it to disk if it intersects us...
        interval = intersect( (piece.start_byte, piece.end_byte),
                              (self.start_byte, self.end_byte) )
        if interval:
            dataoffset = interval[0] - piece.start_byte
            towrite = data[dataoffset:dataoffset + (interval[1] - interval[0]) + 1]
            ensure_exist( self.get_path() )
            fo = open( self.get_path(), 'r+b' )
            if self.start_byte <= piece.start_byte:
                # fff...
                #    ppp..
                fo.seek(piece.start_byte - self.start_byte)
            fo.write(towrite)
            fo.close()

    def get_size(self):
        if self.torrent.is_multifile():
            return self.torrent.meta['info']['files'][self.num]['length']
        else:
            return self.torrent.get_size()

    def is_last(self):
        return self.num == self.torrent.get_num_files() - 1

    def byte_range(self):
        return (self.torrent._file_byte_accum[i], self.torrent._file_byte_accum[i] + self.size - 1)

    def get_path(self):
        if self.torrent.is_multifile():
            path = self.torrent.meta['info']['files'][self.num]['path']
            if len(path) > 1:
                filesitsin = os.path.join( options.datapath, self.torrent.meta['info']['name'], os.path.sep.join(path[:-1]) )
                if not os.path.isdir( filesitsin ):
                    os.makedirs( filesitsin )
            relfilepath = os.path.sep.join( path )
            return os.path.join( options.datapath, self.torrent.meta['info']['name'], relfilepath )
        else:
            return os.path.join( options.datapath, self.torrent.meta['info']['name'] )

class Piece(object):
    std_size = 2**14

    def cleanup_old_requests(self, conn, t):
        # purges old piece requests that never got responses
        todelete = []
        for k,data in self.queue_data.iteritems():
            reqtime, reqconn = data
            if conn == reqconn:
                if t - reqtime > options.piece_request_timeout:
                    logging.error('piece request %s timeout!' % [k])
                    todelete.append(k)
        for data in todelete:
            del self.queue_data[data]
            self.queue.remove(data)

    def __init__(self, torrent, num):
        self.torrent = torrent
        self.num = num
        self.sz = self.torrent.get_piece_len(self.num)
        self.start_byte = self.torrent.get_piece_len() * self.num
        self.end_byte = self.start_byte + self.sz - 1
        #self.data = None
        self.chunks = None
        self.numchunks = int(math.ceil( self.sz / float(Piece.std_size) ))
        self.queue = []
        self.queue_data = {}
        self.outbound = None # todo: fast peer extension cancel queued

    def is_last(self):
        return self.num == self.torrent.get_num_pieces() - 1

    def init_data(self):
        self.chunks = [None] * self.numchunks
        #self.data = [None] * self.sz

    def get_data(self, offset, size):
        interval = (self.start_byte + offset, self.start_byte + offset + size - 1)
        chunks = []
        for i in range(self.torrent.get_num_files()):
            chunk = self.torrent.get_file(i).get_data_in_interval(interval)
            if chunk:
                chunks.append(chunk)
        retdata = ''.join(chunks)
        #logging.info('got data got sz %s, wanted %s' % (len(retdata), size))
        if len(retdata) != size:
            pdb.set_trace()
        return retdata

    def write_data(self, data):
        ''' writes to all spanning files '''
        for i in range(self.torrent.get_num_files()):
            self.torrent.get_file(i).write_data_from_piece(self, data)

    def get_file_spans(self):
        files = []
        for i,v in enumerate(self.torrent._file_byte_accum):
            if v >= self.end_byte: # minus one?
                break
            if self.start_byte >= v:
                files.append(i)
        return files

    def make_request(self, conn, peek=False):
        t = time.time()
        #logging.info('piece make request!')
        i = 0

        while i < self.numchunks:

            offset = Piece.std_size * i

            if offset + Piece.std_size >= self.sz:
                sz = self.sz - offset
            else:
                sz = Piece.std_size
            
            data = (self.num, offset, sz)

            if (not self.chunks or not self.chunks[i]) and data not in self.queue:
                if not peek:
                    self.queue.append(data) # todo: piece request timeouts
                    self.queue_data[data] = (t, conn)
                return data

            i += 1

    def handle_peer_response(self, conn, offset, data):
        reqdata = (self.num, offset, len(data))

        if self.chunks is None: 
            self.init_data()
        if reqdata in self.queue:
            self.queue.remove(reqdata)
            del self.queue_data[reqdata]

        # TODO: improve this to reduce copying

        self.chunks[offset/Piece.std_size] = data
        if None not in self.chunks:
            #logging.info('piece complete')

            metahash = self.torrent.meta['info']['pieces'][20*self.num: 20*(self.num+1)]

            data = ''.join(self.chunks)
            self.chunks = None

            if sha1(data).digest() == metahash:
                #logging.info('success got piece %s' % self.num)
                torrent_finished = self.torrent.handle_good_piece(self, data)
                piece_finished = True
                return torrent_finished, piece_finished
            else:
                self.torrent.handle_bad_piece(self)
        return False, False

def base16_hash(raw):
    return ''.join([s[2:] for s in map(hex,struct.unpack('>IIIII', raw))]).upper()

class Torrent(object):
    instances = {}

    def cleanup_old_requests(self, conn, t=None):
        if t is None: t = time.time()

        for k,piece in self.pieces.iteritems():
            piece.cleanup_old_requests(conn, t)

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
                piece = self.get_piece( i )
                if piece.make_request(conn, peek=True):
                    return piece
                else:
                    start = i+1
        except:
            pass

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

    def create_bitmask(self):
        bitmask = []
        logging.info('computing piece hashes...')
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
        if infohash in cls.instances:
            instance = cls.instances[infohash]
        else:
            instance = cls(infohash)
            cls.instances[infohash] = instance
        return instance

    def is_multifile(self):
        return 'files' in self.meta['info']

    def update_meta(self, meta):
        logging.info('update meta!')
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
        self.bitmask = self.create_bitmask()
        logging.info('self.bitmask is %s' % ''.join(map(str,self.bitmask)))

    def __init__(self, infohash):
        self.hash = infohash
        self.pieces = {}
        self.files = {}
        filename = MetaStorage.get(self.hash)
        if filename:
            meta = bencode.bdecode( open( os.path.join(options.datapath, filename) ).read() )
            self.update_meta( meta )
        else:
            self.meta = None
            self.meta_info = None
            self.bitmask = None
            self._file_byte_accum = None

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

