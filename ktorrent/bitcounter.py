import time
from collections import deque

class BitCounter(object):

    @classmethod
    def tick(cls):
        # humm...
        pass

    def __init__(self):
        #records a moving window

        self.sz = 10

        self.buf = deque([0]*self.sz, maxlen=self.sz)
        self.lastfill = 0
        self.rel_t = 0 # time relative to buckets
        self.abs_t = time.time()

    def record(self, num):
        now = time.time()

        # records "num" bits at time t.
        which_bucket = int( (now - self.abs_t) % self.sz )
        
        delta_lastfill = now - self.lastfill
        if delta_lastfill > self.sz:
            # looong time. everything else should be zeroed out
            self.buf = deque([0]*self.sz, maxlen=self.sz)
            #import pdb; pdb.set_trace()
        elif delta_lastfill > 1:
            for i in range(int(delta_lastfill)):
                self.buf[ which_bucket - i ] = 0 # fill in inbetween nums

        self.buf[which_bucket] += num
        self.buf[(which_bucket+1)%self.sz] = 0
        #print self.buf
        self.lastfill = now

    def recent(self, num=3):
        now = time.time()
        if now - self.lastfill > num:
            # xxx -- cleanup
            return 0
        which_bucket = int((time.time() - self.abs_t) % self.sz)
        return sum( ( self.buf[(which_bucket+i)%self.sz] for i in range(num) ) ) / float(num)
