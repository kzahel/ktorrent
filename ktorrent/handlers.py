import logging
import struct
import pdb
import bencode
import constants
import torrent
from tornado.options import options
from connection import Connection
import math
from util import parse_bitmask

class BTMessageHandler(object):
    def __init__(self, application, request):
        self.application = application
        self.request = request
        self._finished = False

    def write(self, data, callback=None):
        self.request.connection.write(data, callback)

    def finish(self):
        self._finished = True
        self.request.finish()
        self._log()

    def _log(self):
        self.application.log_request(self)

    def _request_summary(self):
        if self.request.connection.torrent and self.request.connection.torrent.hash:
            hashstr = '(' + self.request.connection.torrent.hash[:6] + '..)'
        else:
            hashstr = '--'
        return hashstr + ' ' + self.request.type + " " + str(len(self.request.payload)) + ' ' +\
            " (" + self.request.remote_ip + ")"

    def send_message(self, type, payload=None, log=True):
        self.request.connection.send_message(type, payload, log)
                
    def enqueue_message(self, type, payload):
        self.request.connection.enqueue_message( (type, payload) )

    def send_some_shit(self):
        if self.request.connection._remote_bitmask:
            logging.info('remote is interested and we have their bitfield... %s' % self.request.connection._remote_bitmask)
            count = 0

            for index,have in enumerate(self.request.connection._remote_bitmask):
                if not have:
                    count += 1
                    t = torrent.Torrent.instantiate( self.request.connection.handshake['infohash'] )

                    offset = 0
                    logging.info('selected piece %s and offset %s' % (index, offset))

                    sz = 2**14

                    offset = 0

                    if self.request.connection._remote_choked:
                        return

                    while offset < t.get_piece_len():
                        data = t.get_piece_data(index, offset, sz)
                        payload = ''.join((
                            struct.pack('>I',index),
                            struct.pack('>I',offset),
                            data))
                        self.send_message('PIECE', payload, log=False)
                        offset += sz
                    

                    if count > 10:
                        break
            return True
        else:
            logging.error('dont have remote bitfield')
            self.finish()


class NullHandler(BTMessageHandler):
    def handle(self):
        logging.info('nullhandler handle message %s' % [self.request, self.request.type, self.request.payload])
        self.finish()

class BitmaskHandler(BTMessageHandler):

    def handle(self):
        if not self.request.connection.torrent.meta:
            logging.warn('bitfield not useful unless we know number of pieces')
            self.request.connection._stored_bitmask = self.request.payload
            self.finish()
            return
        pieces_len = self.request.len
        self.request.connection._remote_bitmask = parse_bitmask(self.request.connection.torrent, self.request.payload)
        self.request.connection._remote_bitmask_incomplete = self.request.connection._remote_bitmask.count(0)

        logging.info('remo.bitmask is %s' % ''.join(map(str,self.request.connection._remote_bitmask)))

        bytes = []

        bitmask = self.request.connection.torrent.bitmask
        if bitmask:
            for byte in range(int(math.ceil(len(bitmask)/8.0))):

                for bit in range(8):
                    bits = []
                    i = byte * 8 + bit
                    if i < len(bitmask):
                        bits.append(bitmask[i])
                    else:
                        bits.append(0)

                piecesstr = ''.join( map(str,bits) )
                val = int(piecesstr,2)
                encoded = chr(val)

                bytes.append( encoded )

            payload = ''.join(bytes)
            self.send_message('BITFIELD',
                              payload)
        self.finish()

class UTHandler(BTMessageHandler):
    def handle(self):
        ext_msg_type = ord(self.request.payload[0])

        if ext_msg_type == 0:
            info = bencode.bdecode(self.request.payload[1:])
            logging.info('got extension data %s' % info)
            # handshake

            self.request.connection._remote_extension_handshake = info
            self.request.connection._remote_extension_handshake_r = dict( (v,k) for k,v in info['m'].items() )
            resp = {'v': 'ktorrent 0.01',
                    'm': {'ut_metadata': 1},
                    'p': options.port}
            if self.request.connection.torrent.meta:
                resp['metadata_size'] = len(self.request.connection.torrent.meta_info)
            self.request.connection._my_extension_handshake = resp
            logging.info('sending ext msg %s' % resp)
            # send handshake message
            self.send_message('UTORRENT_MSG', chr(0) + bencode.bencode(resp), log=False)
        elif self.request.connection._remote_extension_handshake and ext_msg_type in self.request.connection._remote_extension_handshake_r:
            self.request.connection._remote_extension_handshake
            i = self.request.payload.find('total_size')
            if i != -1:
                j = self.request.payload.find('ee',i)
                if j != -1:
                    data = self.request.payload[1:j+2]
                    meta = bencode.bdecode(data)
                    rest = self.request.payload[j+2:]
                    self.request.connection.insert_meta_piece(meta['piece'],rest)

        else:
            logging.error('do not recognize extension message type')
            pdb.set_trace()

        self.finish()

class ChokeHandler(BTMessageHandler):
    def handle(self):
        logging.info('got choke message :-(')
        self.request.connection._am_choked = True
        self.finish()

class UnChokeHandler(BTMessageHandler):
    def handle(self):
        logging.info('got unchoke message')
        self.request.connection._am_choked = False
        self.finish()

class HaveHandler(BTMessageHandler):
    def handle(self):
        index = struct.unpack('>I', self.request.payload)[0]

        if not self.request.connection._remote_bitmask:
            self.request.connection._stored_haves.append(index)
            logging.info('storing have message for later when we get torrent meta')
            self.finish()
            return

        #logging.info('have index: %s' % index)
        slot = self.request.connection._remote_bitmask[index]
        self.request.connection._remote_bitmask[index] = 1
        self.request.connection._remote_bitmask_incomplete = self.request.connection._remote_bitmask.count(0)
        logging.info('remote now has %s incomplete pieces' % self.request.connection._remote_bitmask_incomplete)
        #logging.info('changing slot from %s to %s' % (slot, 1))
        self.finish()

class PortHandler(BTMessageHandler):
    def handle(self):
        logging.info('got DHT port message: %s' % struct.unpack('>H', self.request.payload)[0])
        self.finish()

class NotInterestedHandler(BTMessageHandler):
    def handle(self):
        self.request.connection._remote_interested = False
        self.finish()

class RequestHandler(BTMessageHandler):
    def handle(self):
        index = struct.unpack('>I', self.request.payload[0:4])[0]
        offset = struct.unpack('>I', self.request.payload[4:8])[0]
        sz = struct.unpack('>I', self.request.payload[8:12])[0]
        logging.info('request %s %s %s' % (index, offset, sz))

        if self.request.connection.torrent.bitmask[index] == 1:
            data = self.request.connection.torrent.get_piece_data(index, offset, sz)
            payload = ''.join((
                    struct.pack('>I',index),
                    struct.pack('>I',offset),
                    data))
            self.send_message('PIECE', payload, log=True)
            self.finish()
        else:
            self.finish()

class InterestedHandler(BTMessageHandler):
    def handle(self):
        self.request.connection._remote_interested = True
        self.finish()
        
            
class CancelHandler(BTMessageHandler):
    def handle(self):
        self.finish()

class PieceHandler(BTMessageHandler):
    def handle(self):
        self.request.connection._piece_request_outbound -= 1

        index = struct.unpack('>I', self.request.payload[0:4])[0]
        offset = struct.unpack('>I', self.request.payload[4:8])[0]
        data = self.request.payload[8:]
        tor_finished, piece_finished = self.request.connection.torrent.get_piece(index).handle_peer_response(self, offset, data)
        conn = self.request.connection

        #if conn._piece_request_outbound == 0:
        #    Connection.make_piece_request(conn)

        if tor_finished:
            logging.info('torrent finished! :-)')
            # don't send the last have piece just to force the connection to stay open, for fun
        elif piece_finished:
            # finished this piece
            #self.enqueue_message('HAVE', struct.pack('>I', index))
            self.send_message('HAVE', struct.pack('>I', index))
        if False:
            logging.info('got piece %s %s %s (q: %s, o: %s)' % (index, offset, len(data),
                                                                self.request.connection._piece_request_queued,
                                                                self.request.connection._piece_request_outbound,
                                                                ))
        self.finish()
