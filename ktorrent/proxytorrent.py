import mimetypes
import logging
import os
from os.path import abspath
import functools

class ProxyTorrent(object):
    instances = {}
    #bufsize = 4096 * 16
    bufsize = 4096 * 16 * 16

    def write_headers(self):
        mime_type, encoding = mimetypes.guess_type(self.filepath)
        if mime_type:
            self.handler.set_header("Content-Type", mime_type)
        else:
            logging.error('could not guess mime type')

    def get_diskfile(self):
        if not self.diskfile:
            self.diskfile = open(self.file.get_path())
        return self.diskfile

    def __init__(self, file, handler):
        self.file = file
        self.filepath = file.get_path()
        self.handler = handler
        self.diskfile = None

        if file.completed():
            self.write_headers()
            self.handle_completed_file()
        else:
            self.parse_range()

            clenheader = 'bytes %s-%s/%s' % (self.bytes_start, self.bytes_end, self.file.get_size())
            self.handler.set_header('Content-Range', clenheader)
            self.handler.set_header('Content-Length', self.bytes_end-self.bytes_start+1)
            logging.info('set content range header %s' % clenheader)
            self.bytes_remaining = self.bytes_end - self.bytes_start + 1
            self.bytes_advanced = 0
            self.write_headers()
            #logging.info('writing to frontend: %s' % self._generate_headers())
            self.handler.flush() # flush out the headers

            # ask file if it has this interval to serve...
            info = self.file.wants_interval( self.bytes_start, self.bytes_end )
            if info['missing_pieces']:
                logging.info('missing pieces for this range %s to %s' % (info['missing_pieces'][0], info['missing_pieces'][-1]))
                request_data = dict(pieces = info['missing_pieces'],
                                    reason = 'range request',
                                    handler = self)
                self.file.torrent.register_pieces_requested( request_data )
                self.handler.request.connection.stream.set_close_callback( functools.partial( self.connection_closed_that_requested_pieces, request_data ) )
                self.stream_as_much_as_available()
            else:
                self.bytes_remaining = self.bytes_end - self.bytes_start + 1
                self.stream_one()

    def connection_closed_that_requested_pieces(self, request_data):
        #logging.warn('special connection closed that was requesting pieces %s' % request_data)
        logging.warn('%s special piece requesting connection close' % self)
        self.file.torrent.unregister_pieces_requested(request_data)

    def handle_piece_complete(self, piece):
        # a piece relevant to this request has completed
        self.stream_as_much_as_available() # attempt to stream, if possible

    def notify_all_pieces_complete(self):
        logging.warn('%s notified all pieces complete' % self)
        # range request is fully satisfied :-D

    def parse_range(self):
        # determine what byte ranges the request expects, based on the headers
        if 'Range' in self.handler.request.headers:
            logging.info('got range string %s' % self.handler.request.headers['Range'])
            self.handler.set_status(206)
            rangestr = self.handler.request.headers['Range'].split('=')[1]
            start, end = rangestr.split('-')
            self.bytes_start = int(start)
            #stat_result = os.stat(self.filepath)
            if not end:
                self.bytes_end = self.file.get_size() - 1
            else:
                self.bytes_end = int(end)
        else:
            self.bytes_start = 0
            self.bytes_end = self.file.get_size() - 1

    @classmethod
    def register(cls, file, handler):
        pt = ProxyTorrent(file, handler)
        key = file.torrent.hash
        if key not in cls.instances:
            cls.instances[key] = []
        cls.instances[key].append( pt )
        return pt

    def stream_as_much_as_available(self):
        # when a piece is completed, it calls this... perhaps filling up the write buffer too fast.
        # put in some logic to simply return when the write buffer is pretty full.

        if self.handler.request.connection.stream.closed():
            self.get_diskfile().close()
            return
        if self.bytes_remaining == 0:
            self.get_diskfile().close()
            self.handler.finish()
        else:
            hole = self.file.hole_in_bytes( self.bytes_start )
            if hole is None:
                self.stream_one() # simply start streaming because the whole file is done
            else:
                readat = self.bytes_start + self.bytes_advanced

                furthest_read_possible = hole - readat
                #logging.info('readat %s, hole %s, frp %s' % (readat, hole, furthest_read_possible))
                if furthest_read_possible <= 0:
                    pass
                    #logging.warn('cannot read -- no data yet!')
                else:
                    #logging.info('furthest read %s' % furthest_read_possible)
                    self.get_diskfile().seek( readat )
                    #logging.info('seek to %s' % readat)
                    data = self.get_diskfile().read( min(self.bufsize, self.bytes_remaining, furthest_read_possible) )
                    self.bytes_advanced += len(data)
                    #logging.info('bytes advanced %s' % self.bytes_advanced)
                    self.bytes_remaining -= len(data)
                    #logging.info('stream as much as available wrote %s' % len(data))
                    self.handler.request.connection.stream.write( data, self.stream_as_much_as_available )

    def stream_one(self):
        if self.handler.request.connection.stream.closed():
            self.get_diskfile().close()
            return
        if self.bytes_remaining == 0:
            self.get_diskfile().close()
            self.handler.finish()
        else:
            readat = self.bytes_start + self.bytes_advanced
            self.get_diskfile().seek(readat)
            data = self.get_diskfile().read(min(self.bytes_remaining, self.bufsize)) # read from torrent object
            self.bytes_remaining -= len(data)
            self.bytes_advanced += len(data)
            #logging.info('read from disk %s, remaining %s' % (len(data), self.bytes_remaining))
            self.handler.request.connection.stream.write( data, self.stream_one )


    def handle_completed_file(self):
        if 'If-Range' in self.handler.request.headers:
            # not sure how to handle this
            logging.warn('staticfilehandler had if-range header %s' % self.handler.request.headers['If-Range'])

        self.bytes_advanced = 0
        if 'Range' in self.handler.request.headers:
            logging.info('got range string %s' % self.handler.request.headers['Range'])
            self.handler.set_status(206)
            rangestr = self.handler.request.headers['Range'].split('=')[1]
            start, end = rangestr.split('-')
            logging.info('seeking to start %s' % start)
            self.bytes_start = int(start)
            self.get_diskfile().seek(self.bytes_start)
            stat_result = os.stat(self.filepath)
            if not end:
                # if range request does not say end bytes, then we determine it ourselves
                # warning... cannot rely on this for incomplete torrents
                self.bytes_end = stat_result.st_size - 1
            else:
                self.bytes_end = int(end)

            clenheader = 'bytes %s-%s/%s' % (self.bytes_start, self.bytes_end, stat_result.st_size)
            self.handler.set_header('Content-Range', clenheader)
            self.handler.set_header('Content-Length', self.bytes_end-self.bytes_start+1)
            logging.info('set content range header %s' % clenheader)
            self.bytes_remaining = self.bytes_end - self.bytes_start + 1
            self.handler.set_header('Content-Length', str(self.bytes_remaining))
            #logging.info('writing to frontend: %s' % self._generate_headers())
            self.handler.flush() # flush out the headers
            self.stream_one()
        else:
            # improve this to stream the large file instead...
            self.handler.write( self.get_diskfile().read() )
            self.get_diskfile().close()
            self.handler.finish()
