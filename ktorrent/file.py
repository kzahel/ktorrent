import os
import logging
from tornado.options import options

def intersect(i1, i2):
    if i1[1] < i2[0] or i2[1] < i1[0]:
        return None
    else:
        return max(i1[0],i2[0]), \
            min(i1[1],i2[1])

def ensure_exist(path):
    parentdir = os.path.sep.join( path.split(os.path.sep)[:-1] )
    if not os.path.exists(parentdir):
        os.makedirs(parentdir)

    if not os.path.exists(path):
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
            #logging.info('writing to %s' % self.get_path())
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

