import sys; sys.path.insert(0,'/tmp/claude-0/-home-user/d281676a-9e0b-58dd-a185-3f1dadb4791e/scratchpad/sumo/lib/python3.13/site-packages/sumo/tools')
import sumolib,sys
n=sumolib.net.readNet('cs.net.xml')
def near(lon,lat):
    x,y=n.convertLonLat2XY(lon,lat)
    c=[(d,e) for e,d in n.getNeighboringEdges(x,y,6000) if e.allows('passenger') and e.getSpeed()>15]
    return min(c,key=lambda t:t[0])[1]
a=near(31.43,30.03); b=near(32.30,29.60)
path,cost=n.getShortestPath(a,b,vClass='passenger')
L=sum(e.getLength() for e in path)
print('end lonlat',n.convertXY2LonLat(*path[-1].getShape()[-1]));print('from',a.getID(),'to',b.getID(),'edges',len(path),'length km',round(L/1000,1),'freeflow min',round(sum(e.getLength()/e.getSpeed() for e in path)/60,1))
print('speeds km/h used',sorted(set(round(e.getSpeed()*3.6) for e in path)))
open('route_edges.txt','w').write(' '.join(e.getID() for e in path))
