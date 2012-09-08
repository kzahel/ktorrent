# example of how to use miniupnp

import miniupnpc
u=miniupnpc.UPnP()
u.discoverdelay=2000
i = u.discover()
print 'found',i
if i>0:
    url = u.selectigd()
    external = 39342
    internal = 22
    result=u.addportmapping(external, 'TCP', u.lanaddr, internal,'kyle port %u' % internal,'')
else:
    print 'no devices discovered'
