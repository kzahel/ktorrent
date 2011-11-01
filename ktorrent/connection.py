import socket
import logging
import struct
import time
import constants
import math
import bencode
import pdb
import random
from hashlib import sha1
from torrent import Torrent, base16_hash
from util import MetaStorage, parse_bitmask
from tornado import stack_context
from tornado.options import options

def parse_handshake(data):
    protocol_str_len = ord(data[0])
    protocol_str = data[1:protocol_str_len+1]
    
    i = 1 + protocol_str_len

    reserved = data[i:i+8]
    i += 8
    infohash = data[i:i+20]
    i += 20
    peerid = data[i:i+20]
    
    if len(data) != 1 + protocol_str_len + 8 + 20 + 20:
        logging.error('error in handshake -- data wrong length')

    return dict( protocol = protocol_str,
                 reserved = reserved,
                 infohash = infohash,
                 peerid = peerid )

class Request(object):
    def __init__(self, type, len, data, connection, remote_ip):
        self.type = type
        self.len = len
        self.payload = data
        self.args = None # parsed payload
        self.remote_ip = remote_ip
        self.connection = connection
        self.no_keep_alive = False
        self._finish_time = None
        self._start_time = time.time()

    def finish(self):
        self.connection.finish()
        self._finish_time = time.time()

    def request_time(self):
        if self._finish_time is None:
            return time.time() - self._start_time
        else:
            return self._finish_time - self._start_time

class Connection(object):
    instances = []

    @classmethod
    def get_by_hash(cls, hash):
        # todo -- speed up by storing this ahead of time
        toreturn = []
        for conn in cls.instances:
            if conn.torrent and conn.torrent.hash == hash:
                toreturn.append(conn)
        return toreturn

    @classmethod
    def cleanup_old_requests(cls):
        for conn in cls.instances:
            if conn.torrent:
                conn.torrent.cleanup_old_requests(conn)

    @classmethod
    def get_metainfo(cls):
        for conn in cls.instances:
            if conn.torrent:
                if not conn.torrent.meta and not conn._meta_requested and conn._remote_extension_handshake:
                    if 'm' in conn._remote_extension_handshake:
                        if 'ut_metadata' in conn._remote_extension_handshake['m']:
                            if 'metadata_size' in conn._remote_extension_handshake:
                                conn.request_metadata()

    @classmethod
    def make_piece_request(cls, instance=None):
        #picks in-order

        piece_queue_limit = options.outbound_piece_limit
        piece_outbound_limit = options.outbound_piece_limit

        if not instance:
            iter = cls.instances
        else:
            iter = [instance]

        for conn in iter:
            if not conn.torrent or not conn.torrent.meta:
                break
            
            if conn.torrent._bitmask_incomplete_count == 0:
                logging.debug('this torrent is finished. not making requests')
                break

            #if conn._remote_bitmask_incomplete == 0:
            #    break

            if conn.torrent.meta and conn._remote_bitmask:

                cur_piece = None

                while conn._active:

                    if conn._piece_request_queued >= piece_queue_limit:
                        logging.info('not making more piece request -- piece queue limit reached')
                        break
                    elif conn._piece_request_outbound >= piece_outbound_limit:
                        logging.debug('not making more piece request -- piece outbound limit reached')
                        break

                    if not cur_piece:
                        cur_piece = conn.torrent.get_lowest_piece_can_that_can_make_request(conn)
                        if cur_piece:
                            logging.info('selected cur piece %s' % cur_piece)

                    if cur_piece:
                        if not conn._am_interested and conn._am_choked:
                            conn.send_message('INTERESTED')
                            break
                        else:
                            data = cur_piece.make_request(conn)
                            if data:
                                conn.send_message('REQUEST',
                                              ''.join( (
                                            struct.pack('>I',data[0]),
                                            struct.pack('>I',data[1]),
                                            struct.pack('>I',data[2]),
                                            )))
                                #conn.enqueue_message( queue_data )
                                #conn.send_message( *queue_data )
                            else:
                                cur_piece = None

                    else:
                        logging.error("no piece that can make requests!")
                        break
                        #conn._active = False
                        #conn.flushout_send_queue_and_say_not_interested()

                #if not conn._request:
                #conn.send_queue()

    def enqueue_message(self, data):
        if data[0] == 'REQUEST':
            self._piece_request_queued += 1
            logging.info('enqueue piece req (q: %s, o: %s)' % (self._piece_request_queued, self._piece_request_outbound))
        self._send_request_queue.insert(0, data)
        if len(self._send_request_queue) > 10:
            self.send_queue()

    def flushout_send_queue_and_say_not_interested(self):
        #self.send_message('HAVE_ALL')
        if self._am_interested:
            self.send_message('NOT_INTERESTED')

    def request_metadata(self):
        msgcode = self._remote_extension_handshake['m']['ut_metadata']
        self._meta_requested = True
        sz = self._remote_extension_handshake['metadata_size']

        chunksz = 2**14
        #request blocks...
        msg_types = { 'REQUEST': 0,
                      'DATA': 1,
                      'REJECT': 2 }

        for chunk in range(int( math.ceil(float(sz) / chunksz) )):
            offset = chunk * chunksz
            msg = {'msg_type': msg_types['REQUEST'],
                   'piece': chunk}
            self.send_message('UTORRENT_MSG', chr(self._remote_extension_handshake['m']['ut_metadata']) + bencode.bencode(msg))

    def insert_meta_piece(self, piece, data):
        logging.info('insert meta piece %s!' % len(data))
        self._meta_pieces[piece] = data
        sz = self._remote_extension_handshake['metadata_size']
        chunksz = 2**14
        numpieces = int( math.ceil(float(sz) / chunksz) )
        if sorted(self._meta_pieces.keys()) == range(numpieces):
            logging.info('got all the metadata!')
            alldata = []
            for i in range(numpieces):
                alldata.append( self._meta_pieces[i] )
            torrent_data = ''.join(alldata)
            infohash = sha1(torrent_data).digest()
            logging.info('received infohash is %s' % [infohash])
            torrent_meta = bencode.bdecode(torrent_data)
            self.torrent.update_meta( { 'info': torrent_meta } )
            MetaStorage.insert( self.torrent )

            self.post_metadata_received()

    def post_metadata_received(self):
        # when we get all the metadata then process the bitmask and haves
        if self._stored_bitmask:
            self._remote_bitmask = parse_bitmask(self.torrent, self._stored_bitmask)
            self._stored_bitmask = None

        # process stored haves
        for index in self._stored_haves:
            self._remote_bitmask[index] = 1

        self._stored_haves = None
        self._remote_bitmask_incomplete = self._remote_bitmask.count(0)

    def send_message(self, type, payload=None, log=True):

        if type == 'INTERESTED':
            self._am_interested = True
        elif type == 'NOT_INTERESTED':
            self._am_interested = False
        elif type == 'CHOKE':
            self._remote_choked = True
        elif type == 'UNCHOKE':
            self._remote_choked = False
        elif type == 'REQUEST':
            #self._piece_request_queued -= 1
            self._piece_request_outbound += 1
        elif type == 'BITFIELD':
            self._sent_bitmask = True

        if payload == None:
            payload = ''
        if log:
            logging.info('Sending %s with len %s (o: %s)' % (type, len(payload), self._piece_request_outbound))


        towrite = ''.join( (
                struct.pack('>I', len(payload)+1),
                constants.message_dict[type],
                payload) )
        self.write(towrite)

    def send_queue(self):
        logging.info('send queue choked: %s' % self._am_choked)
        while self._send_request_queue and not self._am_choked:
            if self._piece_request_outbound > options.outbound_piece_limit:
                #logging.info('breaking send_queue -- too many outbound requests')
                break
            message, payload = self._send_request_queue.pop()
            #logging.warn('SENDING PIECE REQ! %s' % [data])
            self.send_message(message, payload)

    def __init__(self, stream, address, request_callback):
        Connection.instances.append( self )
        self._active = True


        logging.info('initialized connection %s' % self)
        self.request_callback = request_callback
        self._my_peerid = '-KY1111-' + '3'*12
        self._request = None

        self._stored_bitmask = None # in case we dont have torrent meta yet, store this for processing later
        self._stored_haves = [] # in case we aresent have messages before we get the torrent meta, store them for processing later

        self._meta_requested = False
        self._meta_pieces = {}
        self.torrent = None
        self._sent_bitmask = False
        self._piece_request_queued = 0
        self._piece_request_outbound = 0

        self._remote_interested = False
        self._remote_choked = True
        self._remote_bitmask = None
        self._remote_bitmask_incomplete = None
        self._am_choked = True
        self._am_interested = False

        self._remote_extension_handshake = None

        self._my_extension_handshake = None

        self._send_request_queue = []

        self._request_finished = False
        self.stream = stream
        self.stream.set_close_callback(self.on_connection_close)
        if self.stream.socket.family not in (socket.AF_INET, socket.AF_INET6):
            # Unix (or other) socket; fake the remote address
            address = ('0.0.0.0', 0)
        self.address = address
        self.stream.read_bytes(constants.handshake_length, self.got_handshake)


    def on_connection_close(self):
        # remove piece timeouts...
        self.torrent.cleanup_old_requests(self, -1)
        self._active = False
        Connection.instances.remove(self)
        logging.error('closed peer connection %s' % [self.address, self.torrent.hash[:6] + '..' if self.torrent else None])

    def get_more_messages(self):
        if not self.stream.closed():
            #logging.info('%s getting more messages' % self)
            self.stream.read_bytes(5, self.new_message)

    def send_handshake(self):
        towrite = ''.join((chr(len(constants.protocol_name)),
                           constants.protocol_name,
                           ''.join(constants.handshake_flags),
                           self.handshake['infohash'],
                           self._my_peerid
                           ))
        self.stream.write(towrite)

    def got_handshake(self, data):
        logging.info('got handshake %s' % [data])
        self.handshake = parse_handshake(data)
        self.torrent = Torrent.instantiate( base16_hash(self.handshake['infohash']) )
        logging.info('connection has torrent %s with hash %s%s' % (self.torrent, self.torrent.hash, ' (with metadata)' if self.torrent.meta else ''))
        self.send_handshake()
        if self.torrent and self.torrent.meta:
            self.send_bitmask()
        self.get_more_messages()

    def _any_new_data(self):
        #logging.info('new data to buffer %s' % len(self.stream._read_buffer))
        pass

    def new_message(self, data):
        self.message_len = struct.unpack('>I', data[:4])[0] - 1
        self.stream._buffer_grown_callback = self._any_new_data
        msgval = ord(data[4])
        if msgval not in constants.message_dict:
            logging.error('message type not recognized')
            pdb.set_trace()
        self.msgtype = constants.message_dict[ msgval ]
        #logging.info('new message %s' % [data, self.message_len, self.msgtype])
        if self.message_len > 0:
            self.stream.read_bytes(self.message_len, self.on_message_body)
        else:
            self.on_message_body('')

    def on_message_body(self, data):
        #logging.info('got message body')
        self._request = Request(self.msgtype, self.message_len, data, self, self.address[0])
        self.request_callback( self._request )

    def write(self, chunk, callback=None):
        """Writes a chunk of output to the stream."""
        #assert self._request, "Request closed"
        if not self.stream.closed():
            self._write_callback = stack_context.wrap(callback)
            self.stream.write(chunk, self._on_write_complete)

    def _on_write_complete(self):
        if self._write_callback is not None:
            callback = self._write_callback
            self._write_callback = None
            callback()            
        # XXX?
        if self._request_finished and not self.stream.writing():
            self._finish_request()

    def finish(self):
        """Finishes the request."""
        if not self._request:
            logging.error('req already closed')
            pdb.set_trace()
        assert self._request, "Request closed"
        self._request_finished = True
        if not self.stream.writing():
            self._finish_request()

    def send_bitmask(self):
        if self.torrent._bitmask_incomplete_count == 0:
            self.send_message("HAVE_ALL")
            return

        removed = [] # randomly remove some for fun (ut seems to do this???)

        bytes = []
        bitmask = self.torrent.bitmask
        for byte in range(int(math.ceil(len(bitmask)/8.0))):
            bits = []
            for bit in range(8):
                i = byte * 8 + bit
                if i < len(bitmask):
                    have = bitmask[i]
                    if have:
                        if random.random() < .1:
                            removed.append(i)
                            bits.append(0)
                        else:
                            bits.append(1)
                    else:
                        bits.append(have)
                else:
                    # pad the response
                    bits.append(0)

            piecesstr = ''.join( map(str,bits) )
            val = int(piecesstr,2)

            encoded = chr(val)

            bytes.append( encoded )

        payload = ''.join(bytes)
        self.send_message('BITFIELD',
                          payload)
        for r in removed:
            self.send_message('HAVE', struct.pack('>I',r))


    def _finish_request(self):
        req = self._request
        self._request = None
        self._request_finished = False

        #logging.info('FINISH REQ')

        if req.no_keep_alive:
            logging.info('closing stream')
            req.connection.stream.close()
        else:
            if self._am_interested and not self._am_choked and self._piece_request_outbound == 0:
                Connection.make_piece_request(self)

            #if self.torrent and self.torrent.meta and not self._sent_bitmask:
            #    self.send_bitmask()

            self.get_more_messages()
