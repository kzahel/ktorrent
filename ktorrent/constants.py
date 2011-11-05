protocol_name = 'BitTorrent protocol'
handshake_length = 1 + len(protocol_name) + 8 + 20 + 20
MESSAGES = [
    'CHOKE',
    'UNCHOKE',
    'INTERESTED',
    'NOT_INTERESTED',
    'HAVE',
    'BITFIELD',
    'REQUEST',
    'PIECE',
    'CANCEL',
    'PORT',
    'WANT_METAINFO',
    'METAINFO',
    'SUSPECT_PIECE',
    'SUGGEST_PIECE',
    'HAVE_ALL',
    'HAVE_NONE',
    'REJECT_REQUEST',
    'ALLOWED_FAST',
    'HOLE_PUNCH',
    '--',
    'UTORRENT_MSG'
]
message_dict = dict( (n,v) for n,v in enumerate(MESSAGES) )
message_dict.update( dict( (v,chr(k)) for k,v in message_dict.iteritems() ) )

HANDSHAKE_CODE = 0
UTORRENT_MSG_INFO = chr(0)
# in reality this could be variable
UTORRENT_MSG_PEX = chr(1)

# reserved flags:
#  reserved[0]
#   0x80 Azureus Messaging Protocol
AZUREUS = 0x80
#  reserved[5]
#   0x10 uTorrent extensions: peer exchange, encrypted connections,
#       broadcast listen port.
UTORRENT = 0x10
#  reserved[7]
DHT = 0x01
FAST_EXTENSION = 0x04   # suggest, haveall, havenone, reject request,
                        # and allow fast extensions.
NAT_TRAVERSAL = 0x08 # holepunch

LAST_BYTE = DHT
LAST_BYTE |= NAT_TRAVERSAL
FLAGS = ['\0'] * 8
#FLAGS[0] = chr( AZUREUS )
FLAGS[5] = chr( UTORRENT )
FLAGS[7] = chr( LAST_BYTE )
handshake_flags = FLAGS
#handshake_flags = ['\0'] * 8

tor_meta_codes = { 0: 'request',
                   1: 'data',
                   2: 'reject' }

tor_meta_codes_r = dict( (v,k) for k,v in tor_meta_codes.iteritems() )
