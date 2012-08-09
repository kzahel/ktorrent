import math
import time
from hashlib import sha1
from tornado.options import options
import logging

class Piece(object):
    std_size = 2**14

    @classmethod
    def get_spanning(cls, torrent, start_byte, end_byte):
        # gets all pieces that contain start_byte, end_byte
        torrent.populate_pieces()

        pieces = []
        for n,piece in torrent.pieces.iteritems():
            # better yet, do two ended binary search ...
            if piece.end_byte < start_byte:
                continue
            elif piece.start_byte > end_byte:
                break
            else:
                pieces.append(piece)
        return pieces

    def add_listening_handler(self, handler):
        # registers that a handler is waiting for this piece to finish
        self.listeners.append(handler)

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

    def complete(self):
        return self.torrent.bitmask[self.num] == 1

    def on_complete(self):
        # called when piece is complete
        #logging.info('%s complete!' % self)
        for listener in self.listeners:
            listener.handle_piece_complete(self)
        self.listeners = []

    def __repr__(self):
        return '<Piece %s/%s>' % (self.num+1,self.torrent.get_num_pieces())

    def __init__(self, torrent, num):
        self.torrent = torrent
        self.listeners = []
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

